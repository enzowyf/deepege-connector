"""Deepege MCP server (official Python SDK, Streamable HTTP)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from deepege_connector import __version__
from deepege_connector.api import (
    OpenAPIClient,
    OpenAPIError,
    invalid_input,
    job_payload,
    resolve_idempotency_key,
    should_renew_result_links,
)
from deepege_connector.auth import (
    HOSTED_SCOPES,
    HostedAuthError,
    HostedTokenVerifier,
    MissingCredentialsError,
    resolve_bearer_token,
)
from deepege_connector.config import Settings
from deepege_connector.models import (
    AnswerRequest,
    ErrorCode,
    PlanAction,
    PlanDecision,
    Preferences,
    VideoRequestCreate,
)
from deepege_connector.redact import install_leak_filter

logger = logging.getLogger("deepege_connector")

_INSTRUCTIONS = (
    "Use these tools to create and follow a Deepege video job. "
    "Call deepege_create_video_request with the user's prompt, then poll "
    "deepege_get_job, waiting poll_after_ms milliseconds between checks. "
    "When status is awaiting_confirmation, show the plan and quote and call "
    "deepege_confirm_plan (confirm, revise, or reject). "
    "When status is awaiting_input, present the question and call "
    "deepege_answer_question. "
    "A failed job cannot be retried; if error.retryable is true, start a new "
    "request. Result playback URLs expire; deepege_get_job renews them when "
    "they have expired, or when renew_result_links is true."
)


def _error_json(
    code: str,
    message: str,
    *,
    retryable: bool,
    **extra: Any,
) -> str:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
        "refund": None,
    }
    error.update(extra)
    return json.dumps({"error": error}, ensure_ascii=False)


def _headers_from(ctx: Context) -> Mapping[str, str] | None:
    try:
        return ctx.headers
    except ValueError:
        return None


def _raise_validation(exc: ValidationError) -> None:
    messages = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()) if part != "body")
        messages.append(
            f"{loc}: {err.get('msg', 'invalid')}" if loc else str(err.get("msg", "invalid"))
        )
    message = "; ".join(messages) or "The request is invalid."
    raise ToolError(invalid_input(message).to_tool_message()) from exc


def _map_error(exc: OpenAPIError) -> ToolError:
    return ToolError(exc.to_tool_message())


def create_server(
    settings: Settings | None = None,
    *,
    api_client: OpenAPIClient | None = None,
) -> MCPServer:
    """Build an MCP server bound to an Open API client.

    Tools call the Open API with the caller's user API key (self-hosted
    mode, the default) or with a short-lived downstream token obtained
    through hosted-mode introspection and token-exchange.
    """
    settings = settings or Settings.from_env()
    settings.validate()
    if api_client is None:
        if not settings.api_base_url:
            raise ValueError("DEEPEGE_API_BASE_URL is required")
        api_client = OpenAPIClient(settings.api_base_url)
    client = api_client
    verifier: HostedTokenVerifier | None = None
    auth_settings: AuthSettings | None = None
    if settings.hosted:
        issuer = settings.authorization_server or settings.api_base_url
        if not issuer or not settings.mcp_resource:
            raise ValueError("hosted mode requires DEEPEGE_API_BASE_URL and DEEPEGE_MCP_RESOURCE")
        verifier = HostedTokenVerifier(client, settings)
        auth_settings = AuthSettings(
            issuer_url=issuer,
            resource_server_url=settings.mcp_resource,
            required_scopes=list(HOSTED_SCOPES),
            validate_token_resource=True,
        )

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[dict[str, Any]]:
        try:
            yield {}
        finally:
            await client.aclose()

    mcp = MCPServer(
        name="deepege-connector",
        title="Deepege",
        description="MCP server that talks to the Deepege Open API.",
        instructions=_INSTRUCTIONS,
        version=__version__,
        lifespan=lifespan,
        auth=auth_settings,
        token_verifier=verifier,
    )

    async def _outbound_token(ctx: Context) -> str:
        if verifier is not None:
            try:
                token = resolve_bearer_token(_headers_from(ctx), fallback=None)
                return await verifier.outbound_token(token)
            except (MissingCredentialsError, HostedAuthError) as exc:
                raise ToolError(
                    _error_json(ErrorCode.UNAUTHORIZED.value, str(exc), retryable=False)
                ) from exc
        try:
            return resolve_bearer_token(_headers_from(ctx), fallback=settings.api_key)
        except MissingCredentialsError as exc:
            raise ToolError(
                _error_json(
                    ErrorCode.UNAUTHORIZED.value,
                    str(exc),
                    retryable=False,
                )
            ) from exc

    @mcp.tool(
        name="deepege_create_video_request",
        title="Create a video request",
        description=(
            "Start a new video job from a natural-language prompt. "
            "Optional aspect_ratio (for example 16:9, 9:16, or 1:1) and "
            "duration_seconds (1-600) are preferences, not guarantees. "
            "Returns the job, including job_id and poll_after_ms. "
            "Idempotency-Key is generated when idempotency_key is omitted."
        ),
    )
    async def deepege_create_video_request(
        prompt: str,
        ctx: Context,
        aspect_ratio: str | None = None,
        duration_seconds: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        api_key = await _outbound_token(ctx)
        try:
            preferences = None
            if aspect_ratio is not None or duration_seconds is not None:
                preferences = Preferences(
                    aspect_ratio=aspect_ratio,
                    duration_seconds=duration_seconds,
                )
            body = VideoRequestCreate(prompt=prompt, preferences=preferences)
            key = resolve_idempotency_key(idempotency_key)
            job = await client.create_video_request(api_key, body, idempotency_key=key)
        except ValidationError as exc:
            _raise_validation(exc)
        except OpenAPIError as exc:
            raise _map_error(exc) from exc
        return job_payload(job)

    @mcp.tool(
        name="deepege_get_job",
        title="Get a video job",
        description=(
            "Fetch the current state of a job. Use poll_after_ms as the wait "
            "before the next check while the job is in progress. "
            "When the job has succeeded and the play or cover URL has "
            "expired, this tool renews the result links automatically. "
            "Pass renew_result_links=true to renew them even if they have "
            "not yet expired."
        ),
    )
    async def deepege_get_job(
        job_id: str,
        ctx: Context,
        renew_result_links: bool = False,
    ) -> dict[str, Any]:
        api_key = await _outbound_token(ctx)
        try:
            job = await client.get_job(api_key, job_id)
            if should_renew_result_links(job, force=renew_result_links):
                job = await client.renew_result_links(api_key, job_id)
        except OpenAPIError as exc:
            raise _map_error(exc) from exc
        return job_payload(job)

    @mcp.tool(
        name="deepege_confirm_plan",
        title="Confirm, revise, or reject a plan",
        description=(
            "Act on the current plan of a job that is awaiting confirmation. "
            "action must be confirm, revise, or reject. comment is required "
            "when action is revise. A non-current plan_id returns quote_stale; "
            "fetch the job again and use the latest plan_id. "
            "Confirm authorizes production against the quote; it does not "
            "settle credits yet."
        ),
    )
    async def deepege_confirm_plan(
        job_id: str,
        plan_id: str,
        action: PlanAction,
        ctx: Context,
        comment: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        api_key = await _outbound_token(ctx)
        try:
            body = PlanDecision(plan_id=plan_id, action=action, comment=comment)
            key = resolve_idempotency_key(idempotency_key)
            job = await client.decide_plan(api_key, job_id, body, idempotency_key=key)
        except ValidationError as exc:
            _raise_validation(exc)
        except OpenAPIError as exc:
            raise _map_error(exc) from exc
        return job_payload(job)

    @mcp.tool(
        name="deepege_answer_question",
        title="Answer a job question",
        description=(
            "Answer a question on a job that is awaiting input. "
            "Provide option_id for a choice question, or text for a text "
            "question. question_id must match the current question."
        ),
    )
    async def deepege_answer_question(
        job_id: str,
        question_id: str,
        ctx: Context,
        option_id: str | None = None,
        text: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        api_key = await _outbound_token(ctx)
        try:
            body = AnswerRequest(question_id=question_id, option_id=option_id, text=text)
            key = resolve_idempotency_key(idempotency_key)
            job = await client.answer_question(api_key, job_id, body, idempotency_key=key)
        except ValidationError as exc:
            _raise_validation(exc)
        except OpenAPIError as exc:
            raise _map_error(exc) from exc
        return job_payload(job)

    @mcp.tool(
        name="deepege_cancel_job",
        title="Cancel a video job",
        description=(
            "Cancel a job that has not finished. A succeeded or failed job "
            "cannot be cancelled. The response includes a refund status."
        ),
    )
    async def deepege_cancel_job(job_id: str, ctx: Context) -> dict[str, Any]:
        api_key = await _outbound_token(ctx)
        try:
            job = await client.cancel_job(api_key, job_id)
        except OpenAPIError as exc:
            raise _map_error(exc) from exc
        return job_payload(job)

    return mcp


def main() -> None:
    install_leak_filter()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    install_leak_filter()
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not settings.api_base_url:
        raise SystemExit("DEEPEGE_API_BASE_URL is required")
    server = create_server(settings)
    logger.info(
        "Starting Deepege MCP server on %s:%s (Streamable HTTP, /mcp)",
        settings.mcp_host,
        settings.mcp_port,
    )
    server.run(
        "streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path="/mcp",
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
