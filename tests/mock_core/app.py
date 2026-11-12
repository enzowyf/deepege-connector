"""FastAPI app exposing the mock Deepege Open API."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Form, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)

from deepege_connector.models import (
    ERROR_HTTP_STATUS,
    AnswerRequest,
    ErrorCode,
    PlanDecision,
    VideoRequestCreate,
    dump_job,
    error_envelope,
)
from tests.mock_core.store import ApiError, Store

bearer_scheme = HTTPBearer(auto_error=False)
basic_scheme = HTTPBasic(auto_error=False)


def create_app(store: Store | None = None) -> FastAPI:
    store = store or Store()
    app = FastAPI(
        title="Deepege mock Open API",
        version="0.1.0",
        description=(
            "In-memory stand-in for the Deepege main service, for local connector development."
        ),
    )
    app.state.store = store

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        status = ERROR_HTTP_STATUS[exc.code]
        headers: dict[str, str] = {}
        if exc.retry_after is not None:
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(status_code=status, content=exc.to_body(), headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        messages = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ()) if part != "body")
            messages.append(
                f"{loc}: {err.get('msg', 'invalid')}" if loc else str(err.get("msg", "invalid"))
            )
        message = "; ".join(messages) or "The request is invalid."
        return JSONResponse(
            status_code=ERROR_HTTP_STATUS[ErrorCode.INVALID_INPUT],
            content=error_envelope(ErrorCode.INVALID_INPUT, message),
        )

    def get_store(request: Request) -> Store:
        return request.app.state.store

    def current_account(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> Any:
        token = credentials.credentials if credentials is not None else None
        if token is None:
            header = request.headers.get("authorization") or request.headers.get("Authorization")
            if header and header.lower().startswith("bearer "):
                token = header.split(" ", 1)[1].strip()
        return request.app.state.store.authenticate(token)

    def service_credentials(
        request: Request,
        credentials: HTTPBasicCredentials | None = Depends(basic_scheme),
    ) -> None:
        client_id = credentials.username if credentials is not None else None
        client_secret = credentials.password if credentials is not None else None
        request.app.state.store.authenticate_service(client_id, client_secret)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/open/v1/video-requests")
    def create_video_request(
        body: VideoRequestCreate,
        account: Any = Depends(current_account),
        store: Store = Depends(get_store),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        _require_idempotency_key(idempotency_key)
        payload = body.model_dump(mode="json")
        replay = store.check_idempotency(
            account.principal.account_id, "create", idempotency_key, payload
        )
        if replay is not None:
            return replay.body
        prefs = body.preferences
        job = store.create_video_request(
            account,
            prompt=body.prompt,
            aspect_ratio=prefs.aspect_ratio if prefs else None,
            duration_seconds=prefs.duration_seconds if prefs else None,
        )
        data = dump_job(job)
        store.remember_idempotency(
            account.principal.account_id, "create", idempotency_key, payload, 200, data
        )
        return data

    @app.post("/open/v1/video-requests/{job_id}/plan-decisions")
    def decide_plan(
        job_id: str,
        body: PlanDecision,
        account: Any = Depends(current_account),
        store: Store = Depends(get_store),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        _require_idempotency_key(idempotency_key)
        payload = {"job_id": job_id, **body.model_dump(mode="json")}
        replay = store.check_idempotency(
            account.principal.account_id, "plan-decision", idempotency_key, payload
        )
        if replay is not None:
            return replay.body
        job = store.decide_plan(
            account,
            job_id,
            plan_id=body.plan_id,
            action=body.action.value,
            comment=body.comment,
        )
        data = dump_job(job)
        store.remember_idempotency(
            account.principal.account_id, "plan-decision", idempotency_key, payload, 200, data
        )
        return data

    @app.post("/open/v1/video-requests/{job_id}/answers")
    def answer_question(
        job_id: str,
        body: AnswerRequest,
        account: Any = Depends(current_account),
        store: Store = Depends(get_store),
    ) -> dict[str, Any]:
        job = store.answer(
            account,
            job_id,
            question_id=body.question_id,
            option_id=body.option_id,
            text=body.text,
        )
        return dump_job(job)

    @app.get("/open/v1/jobs/{job_id}")
    def get_job(
        job_id: str,
        account: Any = Depends(current_account),
        store: Store = Depends(get_store),
    ) -> dict[str, Any]:
        return dump_job(store.get_job(account, job_id))

    @app.post("/open/v1/jobs/{job_id}/cancel")
    def cancel_job(
        job_id: str,
        account: Any = Depends(current_account),
        store: Store = Depends(get_store),
    ) -> dict[str, Any]:
        return dump_job(store.cancel(account, job_id))

    @app.post("/open/v1/jobs/{job_id}/result-links")
    def renew_result_links(
        job_id: str,
        account: Any = Depends(current_account),
        store: Store = Depends(get_store),
    ) -> dict[str, Any]:
        return dump_job(store.renew_result_links(account, job_id))

    @app.get("/open/v1/me")
    def get_me(
        account: Any = Depends(current_account),
        store: Store = Depends(get_store),
    ) -> dict[str, Any]:
        return store.me(account)

    @app.post("/oauth/introspect")
    def introspect(
        store: Store = Depends(get_store),
        _: None = Depends(service_credentials),
        token: str = Form(...),
        token_type_hint: str | None = Form(default=None),
    ) -> dict[str, Any]:
        del token_type_hint
        return store.introspect(token)

    @app.post("/oauth/token")
    def token_exchange(
        store: Store = Depends(get_store),
        _: None = Depends(service_credentials),
        grant_type: str = Form(...),
        subject_token: str = Form(...),
        subject_token_type: str = Form(...),
        requested_token_type: str | None = Form(default=None),
        resource: str | None = Form(default=None),
        audience: str | None = Form(default=None),
        scope: str | None = Form(default=None),
    ) -> dict[str, Any]:
        del requested_token_type, scope
        if resource is not None or (audience or "deepege-open-v1") != "deepege-open-v1":
            raise ApiError(
                ErrorCode.INVALID_INPUT,
                "audience must be deepege-open-v1; resource is not accepted here.",
            )
        expected = "urn:ietf:params:oauth:grant-type:token-exchange"
        if grant_type != expected:
            raise ApiError(
                ErrorCode.INVALID_INPUT,
                f"grant_type must be {expected}.",
            )
        if not subject_token_type:
            raise ApiError(ErrorCode.INVALID_INPUT, "subject_token_type is required.")
        return store.exchange(subject_token)

    return app


def _require_idempotency_key(key: str | None) -> str:
    if not key or not key.strip():
        raise ApiError(ErrorCode.INVALID_INPUT, "The Idempotency-Key header is required.")
    if len(key) > 255:
        raise ApiError(ErrorCode.INVALID_INPUT, "The Idempotency-Key header is too long.")
    return key


app = create_app()


def run() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Run the mock Deepege Open API.")
    parser.add_argument(
        "--host",
        default=os.environ.get("DEEPEGE_MOCK_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DEEPEGE_MOCK_PORT", "8080")),
    )
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    run()
