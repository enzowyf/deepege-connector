"""Shared types for the Deepege Open API and the connector.

These models describe the public contract only. They must not mention
internal workflows, model vendors, or private service names.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobStatus(StrEnum):
    """Lifecycle of a video-generation job.

    Mapping used by the main service when projecting onto this enum:

    - ``planning``: a plan is still being prepared.
    - ``awaiting_confirmation``: a plan and quote are ready for the user.
    - ``awaiting_input``: planning is stuck, or the assistant has paused
      and needs the user to answer a question.
    - ``producing``: start has been authorized and/or production is in
      progress, including generation of the finished video.
    - ``succeeded``: the video is ready.
    - ``failed``: the job ended unsuccessfully and is not recoverable.
      If ``error.retryable`` is true, the caller may start a new video
      request; it must not retry this job.
    - ``cancelled``: the user rejected the plan or cancelled the job.
    """

    PLANNING = "planning"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AWAITING_INPUT = "awaiting_input"
    PRODUCING = "producing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


IN_PROGRESS_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.PLANNING,
        JobStatus.AWAITING_CONFIRMATION,
        JobStatus.AWAITING_INPUT,
        JobStatus.PRODUCING,
    }
)

TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }
)

# Provisional poll hints (milliseconds). Marked TBD in the OpenAPI contract.
POLL_AFTER_MS: dict[JobStatus, int] = {
    JobStatus.PLANNING: 3000,
    JobStatus.AWAITING_CONFIRMATION: 10000,
    JobStatus.AWAITING_INPUT: 10000,
    JobStatus.PRODUCING: 15000,
}


class AuthMethod(StrEnum):
    API_KEY = "api_key"
    OAUTH = "oauth"


class PlanAction(StrEnum):
    CONFIRM = "confirm"
    REVISE = "revise"
    REJECT = "reject"


class QuestionKind(StrEnum):
    CHOICE = "choice"
    TEXT = "text"


class RefundStatus(StrEnum):
    """How credits were handled after failure or cancellation.

    ``full``: reserved or settled production credits were returned.
    ``partial``: part of those credits were returned.
    ``none``: nothing was reserved, or nothing was returned.
    """

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class ErrorCode(StrEnum):
    """Unified public error codes returned by the new Open API endpoints."""

    QUOTE_STALE = "quote_stale"
    CREDITS_INSUFFICIENT = "credits_insufficient"
    INVALID_INPUT = "invalid_input"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    NOT_FOUND = "not_found"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    RATE_LIMITED = "rate_limited"
    UNAUTHORIZED = "unauthorized"
    ACCOUNT_SUSPENDED = "account_suspended"
    JOB_NOT_CANCELLABLE = "job_not_cancellable"
    RESULT_NOT_AVAILABLE = "result_not_available"
    INTERNAL_ERROR = "internal_error"


ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.QUOTE_STALE: 409,
    ErrorCode.CREDITS_INSUFFICIENT: 402,
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.INSUFFICIENT_SCOPE: 403,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.ACCOUNT_SUSPENDED: 403,
    ErrorCode.JOB_NOT_CANCELLABLE: 409,
    ErrorCode.RESULT_NOT_AVAILABLE: 409,
    ErrorCode.INTERNAL_ERROR: 500,
}

ERROR_RETRYABLE: dict[ErrorCode, bool] = {
    ErrorCode.QUOTE_STALE: True,
    ErrorCode.CREDITS_INSUFFICIENT: False,
    ErrorCode.INVALID_INPUT: False,
    ErrorCode.IDEMPOTENCY_CONFLICT: False,
    ErrorCode.NOT_FOUND: False,
    ErrorCode.INSUFFICIENT_SCOPE: False,
    ErrorCode.RATE_LIMITED: True,
    ErrorCode.UNAUTHORIZED: False,
    ErrorCode.ACCOUNT_SUSPENDED: False,
    ErrorCode.JOB_NOT_CANCELLABLE: False,
    ErrorCode.RESULT_NOT_AVAILABLE: False,
    ErrorCode.INTERNAL_ERROR: True,
}


class Scope:
    """Draft scopes from the public contract."""

    ACCOUNT_READ = "account:read"
    JOBS_READ = "jobs:read"
    GENERATE_VIDEO = "generate:video"

    ALL = (ACCOUNT_READ, JOBS_READ, GENERATE_VIDEO)


class Principal(BaseModel):
    """Authenticated caller, resolved from an API key or an OAuth token."""

    model_config = ConfigDict(extra="forbid")

    account_id: str
    tenant_id: str
    auth_method: AuthMethod
    client_id: str | None = None
    key_id: str | None = None
    grant_id: str | None = None
    scopes: list[str] = Field(default_factory=list)


class Refund(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RefundStatus


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect_ratio: str | None = Field(
        default=None,
        description="Preferred frame aspect ratio, e.g. 16:9, 9:16, or 1:1.",
    )
    duration_seconds: int | None = Field(
        default=None,
        ge=1,
        le=600,
        description="Preferred finished-video duration in seconds.",
    )


class VideoRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=8000)
    preferences: Preferences | None = None


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(description="Opaque identifier of this plan. Distinct from job_id.")
    title: str | None
    duration_seconds: int | None = Field(ge=1)
    style: str | None
    estimated_credits: int = Field(
        ge=0, description="Quoted estimate. Actual settlement may differ."
    )
    max_credits: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Quoted upper bound. Always present. Null means there is no cap. "
            "0 is not used to mean no cap."
        ),
    )
    credit_balance: int = Field(ge=0, description="The caller's spendable balance at quote time.")
    charges_before_confirm: int | None = Field(
        ge=0,
        description=(
            "Credits already consumed during planning, before confirm. May be 0. "
            "Null means not known, not free."
        ),
    )


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(
        description=(
            "Opaque identifier. The server may dispatch it to more than one answering mechanism."
        ),
    )
    kind: QuestionKind
    text: str
    options: list[QuestionOption] = Field(
        default_factory=list,
        description="Selectable options when kind is choice. Empty when kind is text.",
    )


class Progress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    percent: int | None = Field(default=None, ge=0, le=100)


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    play_url: str
    play_url_expires_at: str
    cover_url: str | None = Field(
        default=None,
        description="Time-limited cover URL. Null when the finished video has no cover.",
    )
    cover_url_expires_at: str | None = Field(
        default=None,
        description="UTC instant when cover_url expires. Null when cover_url is null.",
    )
    web_url: str = Field(description="Official site page for this work; may require sign-in.")
    duration_seconds: int | None = Field(
        default=None,
        ge=1,
        description="Finished-video duration in seconds. Null when the duration is unknown.",
    )
    actual_credits: int | None = Field(
        ge=0,
        description=(
            "Credits actually settled for this job. May differ from estimated_credits. "
            "Null means not known, not free."
        ),
    )


class JobFailure(BaseModel):
    """Failure details attached to a job when status is failed."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = Field(
        description=(
            "If true, the caller may start a new POST /open/v1/video-requests. "
            "It does not mean this job can be retried; a failed job is not recoverable."
        ),
    )
    refund: Refund


class ErrorDetail(BaseModel):
    """Body of the unified error envelope used by this batch of endpoints."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    retryable: bool = Field(
        description=(
            "If true, the caller may start a new POST /open/v1/video-requests. "
            "It does not mean this job can be retried; a failed job is not recoverable."
        ),
    )
    refund: Refund | None = None
    recharge_url: str | None = None
    required_scope: str | None = None
    question: Question | None = None


class ErrorEnvelope(BaseModel):
    """HTTP error envelope for the endpoints described in this contract.

    This is not the `{code: int, message, data}` shape used by pre-existing
    `/open/v1` routes.
    """

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


class Job(BaseModel):
    """Unified job representation returned by job and video-request endpoints."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Opaque job handle. It is not a plan_id or a conversation id.")
    status: JobStatus
    poll_after_ms: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Hint for how long to wait before the next status check. "
            "Present while the job is in progress."
        ),
    )
    plan: Plan | None = None
    question: Question | None = None
    progress: Progress | None = None
    result: Result | None = None
    error: JobFailure | None = None
    refund: Refund | None = Field(
        default=None,
        description="Present when the job was cancelled.",
    )


class PlanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    action: PlanAction
    comment: str | None = Field(
        default=None,
        description="Required when action is revise. Free-text revision only.",
    )

    @model_validator(mode="after")
    def _revise_needs_comment(self) -> PlanDecision:
        if self.action is PlanAction.REVISE and not (self.comment and self.comment.strip()):
            raise ValueError("comment is required when action is revise")
        return self


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    option_id: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _needs_answer(self) -> AnswerRequest:
        if not self.option_id and not (self.text and self.text.strip()):
            raise ValueError("either option_id or text is required")
        return self


class Me(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    tenant_id: str
    auth_method: AuthMethod
    client_id: str | None = None
    key_id: str | None = None
    grant_id: str | None = None
    scopes: list[str]
    credit_balance: int = Field(ge=0)


def error_envelope(
    code: ErrorCode,
    message: str,
    *,
    retryable: bool | None = None,
    refund: Refund | None = None,
    recharge_url: str | None = None,
    required_scope: str | None = None,
    question: Question | None = None,
) -> dict[str, Any]:
    detail = ErrorDetail(
        code=code,
        message=message,
        retryable=ERROR_RETRYABLE[code] if retryable is None else retryable,
        refund=refund or Refund(status=RefundStatus.NONE),
        recharge_url=recharge_url,
        required_scope=required_scope,
        question=question,
    )
    return ErrorEnvelope(error=detail).model_dump(mode="json", exclude_none=True)


def dump_job(job: Job) -> dict[str, Any]:
    """Serialize a job, keeping nullable contract fields present as null."""
    data = job.model_dump(mode="json", exclude_none=True)
    if job.plan is not None and "plan" in data:
        data["plan"]["max_credits"] = job.plan.max_credits
    if job.result is not None and "result" in data:
        data["result"]["cover_url"] = job.result.cover_url
        data["result"]["cover_url_expires_at"] = job.result.cover_url_expires_at
        data["result"]["duration_seconds"] = job.result.duration_seconds
    return data


ErrorDetail.model_rebuild()
ErrorEnvelope.model_rebuild()
