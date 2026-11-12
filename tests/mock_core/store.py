"""In-memory state for the mock Open API service."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from deepege_connector.models import (
    POLL_AFTER_MS,
    TERMINAL_STATUSES,
    AuthMethod,
    ErrorCode,
    Job,
    JobFailure,
    JobStatus,
    Plan,
    Principal,
    Progress,
    Question,
    QuestionKind,
    QuestionOption,
    Refund,
    RefundStatus,
    Result,
    Scope,
    error_envelope,
)

DEFAULT_ADVANCE_AFTER_MS = 200
DEFAULT_ADVANCE_AFTER_POLLS = 2
DEFAULT_ESTIMATED_CREDITS = 100
DEFAULT_MAX_CREDITS = 150
DEFAULT_LINK_TTL = timedelta(seconds=3600)
RECHARGE_URL = "https://www.deepege.com/account/credits"

FLAG_ASK = "[ask]"
FLAG_FAIL = "[fail]"
FLAG_QUOTE_STALE = "[quote-stale]"
FLAG_PLANNING_CHARGE = "[planning-charge]"
FLAG_ACTUAL_ROUND = "[actual-round]"
FLAG_UNRECOVERABLE = "[unrecoverable]"
FLAG_NO_COVER = "[no-cover]"
FLAG_UNKNOWN_DURATION = "[unknown-duration]"
FLAG_NO_MAX = "[no-max]"


class ApiError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool | None = None,
        refund: Refund | None = None,
        recharge_url: str | None = None,
        required_scope: str | None = None,
        question: Question | None = None,
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
        self.retry_after = retry_after

    def to_body(self) -> dict[str, Any]:
        return error_envelope(
            self.code,
            self.message,
            retryable=self.retryable,
            refund=self.refund,
            recharge_url=self.recharge_url,
            required_scope=self.required_scope,
            question=self.question,
        )


@dataclass
class Account:
    principal: Principal
    balance: int
    token: str
    banned: bool = False
    revoked: bool = False


@dataclass
class JobRecord:
    job_id: str
    account_id: str
    tenant_id: str
    prompt: str
    aspect_ratio: str | None
    duration_seconds: int | None
    status: JobStatus
    created_at: float
    status_entered_at: float
    polls_in_status: int = 0
    plan: Plan | None = None
    superseded_plan_ids: list[str] = field(default_factory=list)
    question: Question | None = None
    progress: Progress | None = None
    result: Result | None = None
    error: JobFailure | None = None
    refund: Refund | None = None
    reserved_credits: int | None = None
    scenario_ask: bool = False
    scenario_fail: bool = False
    scenario_quote_stale: bool = False
    scenario_planning_charge: bool = False
    scenario_actual_round: bool = False
    scenario_unrecoverable: bool = False
    scenario_no_cover: bool = False
    scenario_unknown_duration: bool = False
    scenario_no_max: bool = False
    asked: bool = False
    link_generation: int = 0


@dataclass
class IdempotencyRecord:
    fingerprint: str
    status_code: int
    body: dict[str, Any]


@dataclass
class Clock:
    """Optional frozen clock so tests can advance time without sleeping."""

    frozen: bool = False
    _now: float = field(default_factory=time.time)

    def time(self) -> float:
        return self._now if self.frozen else time.time()

    def advance(self, seconds: float) -> None:
        if not self.frozen:
            raise RuntimeError("advance() requires a frozen clock")
        self._now += seconds


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _rfc3339(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat().replace("+00:00", "Z")


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.scopes:
        raise ApiError(
            ErrorCode.INSUFFICIENT_SCOPE,
            f"This action requires the {scope} scope.",
            required_scope=scope,
        )


class Store:
    def __init__(
        self,
        *,
        clock: Clock | None = None,
        advance_after_ms: int = DEFAULT_ADVANCE_AFTER_MS,
        advance_after_polls: int = DEFAULT_ADVANCE_AFTER_POLLS,
    ) -> None:
        self.clock = clock or Clock()
        self.advance_after_ms = advance_after_ms
        self.advance_after_polls = advance_after_polls
        self.accounts: dict[str, Account] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.idempotency: dict[tuple[str, str, str], IdempotencyRecord] = {}
        self.service_clients: dict[str, str] = {"test-mcp-client": "test-mcp-secret"}
        self._seed()

    def now(self) -> float:
        return self.clock.time()

    def _seed(self) -> None:
        all_scopes = list(Scope.ALL)
        self._add_account(
            token="sk-test-alice",
            account_id="acc_alice",
            auth_method=AuthMethod.API_KEY,
            key_id="key_alice",
            balance=1000,
            scopes=all_scopes,
        )
        self._add_account(
            token="sk-test-bob",
            account_id="acc_bob",
            auth_method=AuthMethod.API_KEY,
            key_id="key_bob",
            balance=1000,
            scopes=all_scopes,
        )
        self._add_account(
            token="sk-test-broke",
            account_id="acc_broke",
            auth_method=AuthMethod.API_KEY,
            key_id="key_broke",
            balance=10,
            scopes=all_scopes,
        )
        self._add_account(
            token="sk-test-readonly",
            account_id="acc_readonly",
            auth_method=AuthMethod.API_KEY,
            key_id="key_readonly",
            balance=1000,
            scopes=[Scope.ACCOUNT_READ, Scope.JOBS_READ],
        )
        self._add_account(
            token="atok_alice",
            account_id="acc_alice_oauth",
            auth_method=AuthMethod.OAUTH,
            client_id="client_demo",
            grant_id="grant_alice",
            balance=1000,
            scopes=all_scopes,
        )
        self._add_account(
            token="dtok_alice",
            account_id="acc_alice_oauth",
            auth_method=AuthMethod.OAUTH,
            client_id="client_demo",
            grant_id="grant_alice",
            balance=1000,
            scopes=all_scopes,
        )
        self._add_account(
            token="atok_revoked",
            account_id="acc_revoked",
            auth_method=AuthMethod.OAUTH,
            client_id="client_demo",
            grant_id="grant_revoked",
            balance=1000,
            scopes=all_scopes,
            revoked=True,
        )
        self._add_account(
            token="atok_banned",
            account_id="acc_banned",
            auth_method=AuthMethod.OAUTH,
            client_id="client_demo",
            grant_id="grant_banned",
            balance=1000,
            scopes=all_scopes,
            banned=True,
        )
        self._add_account(
            token="sk-test-limited",
            account_id="acc_limited",
            auth_method=AuthMethod.API_KEY,
            key_id="key_limited",
            balance=1000,
            scopes=all_scopes,
        )

    def _add_account(
        self,
        *,
        token: str,
        account_id: str,
        auth_method: AuthMethod,
        balance: int,
        scopes: list[str],
        key_id: str | None = None,
        client_id: str | None = None,
        grant_id: str | None = None,
        banned: bool = False,
        revoked: bool = False,
    ) -> None:
        principal = Principal(
            account_id=account_id,
            tenant_id=account_id,
            auth_method=auth_method,
            client_id=client_id,
            key_id=key_id,
            grant_id=grant_id,
            scopes=list(scopes),
        )
        self.accounts[token] = Account(
            principal=principal,
            balance=balance,
            token=token,
            banned=banned,
            revoked=revoked,
        )

    def authenticate(self, token: str | None) -> Account:
        if not token:
            raise ApiError(ErrorCode.UNAUTHORIZED, "Missing bearer token.")
        if token == "sk-test-disabled":
            raise ApiError(ErrorCode.UNAUTHORIZED, "This API key has been disabled.")
        if token == "sk-test-limited":
            raise ApiError(
                ErrorCode.RATE_LIMITED,
                "Too many requests.",
                retry_after=12,
            )
        account = self.accounts.get(token)
        if account is None:
            raise ApiError(ErrorCode.UNAUTHORIZED, "Invalid bearer token.")
        if account.revoked:
            raise ApiError(ErrorCode.UNAUTHORIZED, "The token has been revoked.")
        if account.banned:
            raise ApiError(ErrorCode.ACCOUNT_SUSPENDED, "This account has been suspended.")
        return account

    def authenticate_service(self, client_id: str | None, client_secret: str | None) -> None:
        if not client_id or not client_secret:
            raise ApiError(ErrorCode.UNAUTHORIZED, "Missing service credentials.")
        expected = self.service_clients.get(client_id)
        if expected is None or expected != client_secret:
            raise ApiError(ErrorCode.UNAUTHORIZED, "Invalid service credentials.")

    def lookup_token(self, token: str) -> Account | None:
        return self.accounts.get(token)

    def check_idempotency(
        self, account_id: str, slot: str, key: str, payload: Any
    ) -> IdempotencyRecord | None:
        record = self.idempotency.get((account_id, slot, key))
        if record is None:
            return None
        if record.fingerprint != _fingerprint(payload):
            raise ApiError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "This Idempotency-Key was already used with different parameters.",
            )
        return record

    def remember_idempotency(
        self,
        account_id: str,
        slot: str,
        key: str,
        payload: Any,
        status_code: int,
        body: dict[str, Any],
    ) -> None:
        self.idempotency[(account_id, slot, key)] = IdempotencyRecord(
            fingerprint=_fingerprint(payload),
            status_code=status_code,
            body=body,
        )

    def create_video_request(
        self,
        account: Account,
        *,
        prompt: str,
        aspect_ratio: str | None,
        duration_seconds: int | None,
    ) -> Job:
        _require_scope(account.principal, Scope.GENERATE_VIDEO)
        now = self.now()
        job = JobRecord(
            job_id=_new_id("job"),
            account_id=account.principal.account_id,
            tenant_id=account.principal.tenant_id,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            status=JobStatus.PLANNING,
            created_at=now,
            status_entered_at=now,
            scenario_ask=FLAG_ASK in prompt,
            scenario_fail=FLAG_FAIL in prompt,
            scenario_quote_stale=FLAG_QUOTE_STALE in prompt,
            scenario_planning_charge=FLAG_PLANNING_CHARGE in prompt,
            scenario_actual_round=FLAG_ACTUAL_ROUND in prompt,
            scenario_unrecoverable=FLAG_UNRECOVERABLE in prompt,
            scenario_no_cover=FLAG_NO_COVER in prompt,
            scenario_unknown_duration=FLAG_UNKNOWN_DURATION in prompt,
            scenario_no_max=FLAG_NO_MAX in prompt,
        )
        self.jobs[job.job_id] = job
        return self._to_job(job)

    def get_job(self, account: Account, job_id: str) -> Job:
        _require_scope(account.principal, Scope.JOBS_READ)
        job = self._owned_job(account, job_id)
        job.polls_in_status += 1
        self._maybe_advance(account, job)
        return self._to_job(job)

    def decide_plan(
        self,
        account: Account,
        job_id: str,
        *,
        plan_id: str,
        action: str,
        comment: str | None,
    ) -> Job:
        _require_scope(account.principal, Scope.GENERATE_VIDEO)
        job = self._owned_job(account, job_id)

        if action == "confirm" and job.plan is not None and job.plan.plan_id == plan_id:
            if job.status in {JobStatus.PRODUCING, JobStatus.SUCCEEDED, JobStatus.AWAITING_INPUT}:
                return self._to_job(job)

        if plan_id in job.superseded_plan_ids:
            raise ApiError(
                ErrorCode.QUOTE_STALE,
                "This plan is no longer valid. Check the job for a new plan.",
            )

        if job.status != JobStatus.AWAITING_CONFIRMATION or job.plan is None:
            raise ApiError(
                ErrorCode.INVALID_INPUT,
                "This job has no plan waiting for a decision.",
            )
        if job.plan.plan_id != plan_id:
            raise ApiError(
                ErrorCode.QUOTE_STALE,
                "plan_id is not the current plan. Check the job for the current plan.",
            )

        if action == "reject":
            self._set_status(job, JobStatus.CANCELLED)
            job.refund = Refund(status=RefundStatus.NONE)
            return self._to_job(job)

        if action == "revise":
            if not comment or not comment.strip():
                raise ApiError(
                    ErrorCode.INVALID_INPUT, "comment is required when action is revise."
                )
            job.prompt = f"{job.prompt}\nRevision: {comment.strip()}"
            job.superseded_plan_ids.append(job.plan.plan_id)
            job.plan = None
            self._set_status(job, JobStatus.PLANNING)
            return self._to_job(job)

        if action != "confirm":
            raise ApiError(ErrorCode.INVALID_INPUT, "action must be confirm, revise, or reject.")

        if job.scenario_quote_stale:
            raise ApiError(
                ErrorCode.QUOTE_STALE,
                "This quote is no longer valid because the price list or manuscript changed.",
            )

        if job.plan.max_credits is not None and account.balance < job.plan.max_credits:
            raise ApiError(
                ErrorCode.CREDITS_INSUFFICIENT,
                "The credit balance is too low to confirm this plan.",
                recharge_url=RECHARGE_URL,
            )

        # Confirm authorizes production; the mock reserves max_credits so later
        # settlement can land at or below the cap. This is a stand-in, not a
        # claim that the real service holds credits at confirm time.
        job.reserved_credits = job.plan.max_credits or job.plan.estimated_credits
        self._set_status(job, JobStatus.PRODUCING)
        job.progress = Progress(message="Starting production", percent=10)
        return self._to_job(job)

    def answer(
        self,
        account: Account,
        job_id: str,
        *,
        question_id: str,
        option_id: str | None,
        text: str | None,
    ) -> Job:
        _require_scope(account.principal, Scope.GENERATE_VIDEO)
        job = self._owned_job(account, job_id)
        if job.status != JobStatus.AWAITING_INPUT or job.question is None:
            raise ApiError(ErrorCode.INVALID_INPUT, "This job is not waiting for an answer.")
        if job.question.question_id != question_id:
            raise ApiError(
                ErrorCode.INVALID_INPUT,
                "question_id does not match the current question.",
                question=job.question,
            )
        if job.question.kind is QuestionKind.CHOICE:
            allowed = {option.id for option in job.question.options}
            if option_id:
                if option_id not in allowed:
                    raise ApiError(
                        ErrorCode.INVALID_INPUT,
                        "option_id is not one of the available options.",
                        question=job.question,
                    )
            elif not (text and text.strip()):
                raise ApiError(
                    ErrorCode.INVALID_INPUT,
                    "A text answer or option_id is required.",
                    question=job.question,
                )
        elif not (text and text.strip()):
            raise ApiError(
                ErrorCode.INVALID_INPUT,
                "A text answer is required.",
                question=job.question,
            )
        job.asked = True
        job.question = None
        self._set_status(job, JobStatus.PRODUCING)
        job.progress = Progress(message="Resuming production", percent=50)
        return self._to_job(job)

    def cancel(self, account: Account, job_id: str) -> Job:
        _require_scope(account.principal, Scope.GENERATE_VIDEO)
        job = self._owned_job(account, job_id)
        if job.status is JobStatus.CANCELLED:
            return self._to_job(job)
        if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
            raise ApiError(
                ErrorCode.JOB_NOT_CANCELLABLE,
                "A finished job cannot be cancelled.",
            )
        if job.reserved_credits and job.status is JobStatus.PRODUCING:
            job.refund = Refund(status=RefundStatus.FULL)
            job.reserved_credits = None
        else:
            job.refund = Refund(status=RefundStatus.NONE)
        self._set_status(job, JobStatus.CANCELLED)
        job.progress = None
        job.question = None
        return self._to_job(job)

    def renew_result_links(self, account: Account, job_id: str) -> Job:
        _require_scope(account.principal, Scope.JOBS_READ)
        job = self._owned_job(account, job_id)
        if job.status is not JobStatus.SUCCEEDED or job.result is None:
            raise ApiError(
                ErrorCode.RESULT_NOT_AVAILABLE,
                "Result links can only be renewed for a succeeded job.",
            )
        job.link_generation += 1
        actual = job.result.actual_credits
        job.result = self._build_result(job, actual_credits=actual)
        return self._to_job(job)

    def me(self, account: Account) -> dict[str, Any]:
        _require_scope(account.principal, Scope.ACCOUNT_READ)
        data = account.principal.model_dump(mode="json")
        data["credit_balance"] = account.balance
        return data

    def introspect(self, token: str) -> dict[str, Any]:
        account = self.lookup_token(token)
        if account is None:
            return {"active": False}
        if account.revoked:
            return {
                "active": False,
                "revoked": True,
                "banned": False,
                "account_id": account.principal.account_id,
            }
        if account.banned:
            return {
                "active": False,
                "revoked": False,
                "banned": True,
                "account_id": account.principal.account_id,
            }
        principal = account.principal
        now = int(self.now())
        return {
            "active": True,
            "scope": " ".join(principal.scopes),
            "scopes": list(principal.scopes),
            "client_id": principal.client_id or principal.key_id,
            "token_type": "Bearer",
            "exp": now + 3600,
            "iat": now,
            "sub": principal.account_id,
            "account_id": principal.account_id,
            "tenant_id": principal.tenant_id,
            "grant_id": principal.grant_id,
            "revoked": False,
            "banned": False,
        }

    def exchange(self, subject_token: str) -> dict[str, Any]:
        account = self.lookup_token(subject_token)
        if account is None or account.revoked or account.banned:
            raise ApiError(ErrorCode.INVALID_INPUT, "The subject token is not exchangeable.")
        downstream = None
        for token, other in self.accounts.items():
            if (
                token.startswith("dtok_")
                and other.principal.account_id == account.principal.account_id
            ):
                downstream = token
                break
        if downstream is None:
            downstream = "dtok_" + account.principal.account_id.removeprefix("acc_")
            self.accounts[downstream] = Account(
                principal=account.principal.model_copy(),
                balance=account.balance,
                token=downstream,
            )
        return {
            "access_token": downstream,
            "token_type": "Bearer",
            "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "expires_in": 300,
            "scope": " ".join(account.principal.scopes),
        }

    def _owned_job(self, account: Account, job_id: str) -> JobRecord:
        job = self.jobs.get(job_id)
        if job is None or job.tenant_id != account.principal.tenant_id:
            raise ApiError(ErrorCode.NOT_FOUND, "The requested job was not found.")
        return job

    def _set_status(self, job: JobRecord, status: JobStatus) -> None:
        job.status = status
        job.status_entered_at = self.now()
        job.polls_in_status = 0

    def _ready_to_advance(self, job: JobRecord) -> bool:
        elapsed_ms = (self.now() - job.status_entered_at) * 1000
        return (
            elapsed_ms >= self.advance_after_ms or job.polls_in_status >= self.advance_after_polls
        )

    def _maybe_advance(self, account: Account, job: JobRecord) -> None:
        if job.status in TERMINAL_STATUSES:
            return
        if not self._ready_to_advance(job):
            if job.status is JobStatus.PRODUCING:
                self._update_progress(job)
            return
        if job.status is JobStatus.PLANNING:
            job.plan = self._build_plan(account, job)
            self._set_status(job, JobStatus.AWAITING_CONFIRMATION)
            return
        if job.status is JobStatus.PRODUCING:
            if job.scenario_ask and not job.asked:
                job.question = Question(
                    question_id=_new_id("q"),
                    kind=QuestionKind.CHOICE,
                    text="Which visual tone should this video use?",
                    options=[
                        QuestionOption(id="warm", label="Warm"),
                        QuestionOption(id="cool", label="Cool"),
                    ],
                )
                job.progress = None
                self._set_status(job, JobStatus.AWAITING_INPUT)
                return
            if job.scenario_fail or job.scenario_unrecoverable:
                job.error = JobFailure(
                    code="interrupted_unrecoverable"
                    if job.scenario_unrecoverable
                    else "production_failed",
                    message=(
                        "Production was interrupted and cannot be resumed by the user."
                        if job.scenario_unrecoverable
                        else "Production could not be completed."
                    ),
                    retryable=True,
                    refund=Refund(
                        status=RefundStatus.FULL if job.reserved_credits else RefundStatus.NONE
                    ),
                )
                job.refund = job.error.refund
                job.reserved_credits = None
                job.progress = None
                self._set_status(job, JobStatus.FAILED)
                return
            estimated = job.plan.estimated_credits if job.plan else DEFAULT_ESTIMATED_CREDITS
            actual = 80 if job.scenario_actual_round else estimated
            if job.reserved_credits is not None:
                account.balance -= actual
                job.reserved_credits = None
            job.result = self._build_result(job, actual_credits=actual)
            job.progress = None
            self._set_status(job, JobStatus.SUCCEEDED)

    def _update_progress(self, job: JobRecord) -> None:
        ratio = min(job.polls_in_status / max(self.advance_after_polls, 1), 0.9)
        percent = max(10, min(int(ratio * 100), 90))
        job.progress = Progress(message="Producing the video", percent=percent)

    def _build_plan(self, account: Account, job: JobRecord) -> Plan:
        duration = job.duration_seconds or 15
        title = job.prompt
        for flag in (
            FLAG_ASK,
            FLAG_FAIL,
            FLAG_QUOTE_STALE,
            FLAG_PLANNING_CHARGE,
            FLAG_ACTUAL_ROUND,
            FLAG_UNRECOVERABLE,
            FLAG_NO_COVER,
            FLAG_UNKNOWN_DURATION,
            FLAG_NO_MAX,
        ):
            title = title.replace(flag, "")
        title = title.strip()
        if len(title) > 60:
            title = title[:57] + "..."
        if not title:
            title = "Untitled video"
        return Plan(
            plan_id=_new_id("plan"),
            title=title,
            duration_seconds=duration,
            style="cinematic",
            estimated_credits=DEFAULT_ESTIMATED_CREDITS,
            max_credits=None if job.scenario_no_max else DEFAULT_MAX_CREDITS,
            credit_balance=account.balance,
            charges_before_confirm=5 if job.scenario_planning_charge else 0,
        )

    def _build_result(self, job: JobRecord, *, actual_credits: int) -> Result:
        now = self.now()
        expires = now + DEFAULT_LINK_TTL.total_seconds()
        expires_at = _rfc3339(expires)
        generation = job.link_generation
        suffix = f"?v={generation}&exp={int(expires)}"
        cover_url = None
        cover_expires = None
        if not job.scenario_no_cover:
            cover_url = f"https://media.deepege.com/cover/{job.job_id}{suffix}"
            cover_expires = expires_at
        duration = None
        if not job.scenario_unknown_duration:
            duration = job.plan.duration_seconds if job.plan else job.duration_seconds or 15
        return Result(
            play_url=f"https://media.deepege.com/play/{job.job_id}{suffix}",
            play_url_expires_at=expires_at,
            cover_url=cover_url,
            cover_url_expires_at=cover_expires,
            web_url=f"https://www.deepege.com/works/{job.job_id}",
            duration_seconds=duration,
            actual_credits=actual_credits,
        )

    def _to_job(self, job: JobRecord) -> Job:
        in_progress = job.status not in TERMINAL_STATUSES
        show_plan = job.plan is not None and job.status in {
            JobStatus.AWAITING_CONFIRMATION,
            JobStatus.PRODUCING,
            JobStatus.SUCCEEDED,
            JobStatus.AWAITING_INPUT,
        }
        return Job(
            job_id=job.job_id,
            status=job.status,
            poll_after_ms=POLL_AFTER_MS.get(job.status) if in_progress else None,
            plan=job.plan if show_plan else None,
            question=job.question if job.status is JobStatus.AWAITING_INPUT else None,
            progress=job.progress if job.status is JobStatus.PRODUCING else None,
            result=job.result if job.status is JobStatus.SUCCEEDED else None,
            error=job.error if job.status is JobStatus.FAILED else None,
            refund=job.refund if job.status is JobStatus.CANCELLED else None,
        )
