"""HTTP client for the Deepege Open API (`/open/v1`)."""

from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx

from deepege_connector.models import (
    ERROR_HTTP_STATUS,
    ERROR_RETRYABLE,
    AnswerRequest,
    ErrorCode,
    ErrorEnvelope,
    Job,
    JobStatus,
    PlanDecision,
    Result,
    VideoRequestCreate,
    dump_job,
)

logger = logging.getLogger("deepege_connector.api")

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._~-]{1,255}$")
_OPEN_PREFIX = "/open/v1"


class OpenAPIError(Exception):
    """An Open API error already mapped into the public envelope."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        refund: dict[str, Any] | None = None,
        recharge_url: str | None = None,
        required_scope: str | None = None,
        question: dict[str, Any] | None = None,
        http_status: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.refund = refund
        self.recharge_url = recharge_url
        self.required_scope = required_scope
        self.question = question
        self.http_status = http_status
        self.retry_after = retry_after

    def to_payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "refund": self.refund,
        }
        if self.recharge_url is not None:
            error["recharge_url"] = self.recharge_url
        if self.required_scope is not None:
            error["required_scope"] = self.required_scope
        if self.question is not None:
            error["question"] = self.question
        payload: dict[str, Any] = {"error": error}
        if self.http_status is not None:
            payload["http_status"] = self.http_status
        if self.retry_after is not None:
            payload["retry_after"] = self.retry_after
        return payload

    def to_tool_message(self) -> str:
        return json.dumps(self.to_payload(), ensure_ascii=False)


def invalid_input(message: str) -> OpenAPIError:
    return OpenAPIError(
        code=ErrorCode.INVALID_INPUT.value,
        message=message,
        retryable=False,
        http_status=ERROR_HTTP_STATUS[ErrorCode.INVALID_INPUT],
    )


def resolve_idempotency_key(supplied: str | None) -> str:
    """Return a caller-supplied key, or generate one that matches the contract."""
    if supplied is None or supplied == "":
        return secrets.token_urlsafe(18)
    if not _IDEMPOTENCY_KEY_RE.fullmatch(supplied):
        raise invalid_input(
            "idempotency_key must be 1-255 characters from A-Z, a-z, 0-9, '.', '_', '~', or '-'."
        )
    return supplied


def parse_instant(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def result_links_expired(result: Result, *, now: datetime | None = None) -> bool:
    """Return True when the play or cover link has expired (or the expiry is unreadable)."""
    moment = now or datetime.now(UTC)
    try:
        if parse_instant(result.play_url_expires_at) <= moment:
            return True
    except ValueError:
        return True
    if result.cover_url and result.cover_url_expires_at:
        try:
            if parse_instant(result.cover_url_expires_at) <= moment:
                return True
        except ValueError:
            return True
    return False


def should_renew_result_links(
    job: Job,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> bool:
    if job.status is not JobStatus.SUCCEEDED or job.result is None:
        return False
    return force or result_links_expired(job.result, now=now)


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def error_from_response(response: httpx.Response) -> OpenAPIError:
    """Map an Open API HTTP error into :class:`OpenAPIError`."""
    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
    payload: dict[str, Any] | None = None
    try:
        body = response.json()
        if isinstance(body, dict):
            payload = body
    except ValueError:
        payload = None

    if payload is not None:
        try:
            envelope = ErrorEnvelope.model_validate(payload)
        except Exception:  # noqa: BLE001
            envelope = None
        else:
            detail = envelope.error
            refund = None
            if detail.refund is not None:
                refund = detail.refund.model_dump(mode="json")
            question = None
            if detail.question is not None:
                question = detail.question.model_dump(mode="json")
            return OpenAPIError(
                code=detail.code.value,
                message=detail.message,
                retryable=detail.retryable,
                refund=refund,
                recharge_url=detail.recharge_url,
                required_scope=detail.required_scope,
                question=question,
                http_status=response.status_code,
                retry_after=retry_after,
            )

    # Ambiguous statuses (403, 409) stay internal_error rather than guessing
    # a more specific code when the body is not a valid envelope.
    if response.status_code == 401:
        code = ErrorCode.UNAUTHORIZED
    elif response.status_code == 402:
        code = ErrorCode.CREDITS_INSUFFICIENT
    elif response.status_code == 404:
        code = ErrorCode.NOT_FOUND
    elif response.status_code == 429:
        code = ErrorCode.RATE_LIMITED
    else:
        code = ErrorCode.INTERNAL_ERROR
    return OpenAPIError(
        code=code.value,
        message="The Open API returned an unexpected error.",
        retryable=ERROR_RETRYABLE[code],
        http_status=response.status_code,
        retry_after=retry_after,
    )


class OpenAPIClient:
    """Async client for the conversational video-generation endpoints."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def create_video_request(
        self,
        api_key: str,
        body: VideoRequestCreate,
        *,
        idempotency_key: str,
    ) -> Job:
        payload = body.model_dump(mode="json", exclude_none=True)
        data = await self._request(
            "POST",
            f"{_OPEN_PREFIX}/video-requests",
            api_key=api_key,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return Job.model_validate(data)

    async def get_job(self, api_key: str, job_id: str) -> Job:
        data = await self._request(
            "GET",
            f"{_OPEN_PREFIX}/jobs/{job_id}",
            api_key=api_key,
        )
        return Job.model_validate(data)

    async def decide_plan(
        self,
        api_key: str,
        job_id: str,
        body: PlanDecision,
        *,
        idempotency_key: str,
    ) -> Job:
        payload = body.model_dump(mode="json", exclude_none=True)
        data = await self._request(
            "POST",
            f"{_OPEN_PREFIX}/video-requests/{job_id}/plan-decisions",
            api_key=api_key,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return Job.model_validate(data)

    async def answer_question(
        self,
        api_key: str,
        job_id: str,
        body: AnswerRequest,
        *,
        idempotency_key: str,
    ) -> Job:
        payload = body.model_dump(mode="json", exclude_none=True)
        data = await self._request(
            "POST",
            f"{_OPEN_PREFIX}/video-requests/{job_id}/answers",
            api_key=api_key,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return Job.model_validate(data)

    async def cancel_job(self, api_key: str, job_id: str) -> Job:
        data = await self._request(
            "POST",
            f"{_OPEN_PREFIX}/jobs/{job_id}/cancel",
            api_key=api_key,
        )
        return Job.model_validate(data)

    async def renew_result_links(self, api_key: str, job_id: str) -> Job:
        data = await self._request(
            "POST",
            f"{_OPEN_PREFIX}/jobs/{job_id}/result-links",
            api_key=api_key,
        )
        return Job.model_validate(data)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        api_key: str,
        json_body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        logger.info("Open API %s %s", method, path)
        try:
            response = await self._client.request(
                method,
                path,
                headers=headers,
                json=json_body,
            )
        except httpx.RequestError as exc:
            logger.warning("Open API request failed: %s %s", method, path)
            raise OpenAPIError(
                code=ErrorCode.INTERNAL_ERROR.value,
                message="The Open API is temporarily unavailable.",
                retryable=True,
                http_status=None,
            ) from exc
        logger.info("Open API %s %s -> %s", method, path, response.status_code)
        if response.is_success:
            try:
                data = response.json()
            except ValueError as exc:
                raise OpenAPIError(
                    code=ErrorCode.INTERNAL_ERROR.value,
                    message="The Open API returned an unexpected response.",
                    retryable=True,
                    http_status=response.status_code,
                ) from exc
            if not isinstance(data, dict):
                raise OpenAPIError(
                    code=ErrorCode.INTERNAL_ERROR.value,
                    message="The Open API returned an unexpected response.",
                    retryable=True,
                    http_status=response.status_code,
                )
            return data
        raise error_from_response(response)

    async def introspect(
        self,
        token: str,
        *,
        client_id: str,
        client_secret: str,
    ) -> dict[str, Any]:
        """RFC 7662 token introspection. The token itself is never logged."""
        data = await self._service_form(
            "/oauth/introspect",
            client_id=client_id,
            client_secret=client_secret,
            form={"token": token},
        )
        return data

    async def exchange_token(
        self,
        subject_token: str,
        *,
        client_id: str,
        client_secret: str,
        resource: str | None = None,
        audience: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """RFC 8693 token exchange. The subject token is never logged."""
        form: dict[str, str] = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": subject_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }
        if resource:
            form["resource"] = resource
        if audience:
            form["audience"] = audience
        if scope:
            form["scope"] = scope
        return await self._service_form(
            "/oauth/token",
            client_id=client_id,
            client_secret=client_secret,
            form=form,
        )

    async def _service_form(
        self,
        path: str,
        *,
        client_id: str,
        client_secret: str,
        form: dict[str, str],
    ) -> dict[str, Any]:
        logger.info("Open API POST %s", path)
        try:
            response = await self._client.post(
                path,
                auth=(client_id, client_secret),
                data=form,
                headers={"Accept": "application/json"},
            )
        except httpx.RequestError as exc:
            logger.warning("Open API request failed: POST %s", path)
            raise OpenAPIError(
                code=ErrorCode.INTERNAL_ERROR.value,
                message="The Open API is temporarily unavailable.",
                retryable=True,
                http_status=None,
            ) from exc
        logger.info("Open API POST %s -> %s", path, response.status_code)
        if response.is_success:
            try:
                data = response.json()
            except ValueError as exc:
                raise OpenAPIError(
                    code=ErrorCode.INTERNAL_ERROR.value,
                    message="The Open API returned an unexpected response.",
                    retryable=True,
                    http_status=response.status_code,
                ) from exc
            if not isinstance(data, dict):
                raise OpenAPIError(
                    code=ErrorCode.INTERNAL_ERROR.value,
                    message="The Open API returned an unexpected response.",
                    retryable=True,
                    http_status=response.status_code,
                )
            return data
        raise error_from_response(response)


def job_payload(job: Job) -> dict[str, Any]:
    """Serialize a job for a tool result, keeping required-null fields."""
    return dump_job(job)
