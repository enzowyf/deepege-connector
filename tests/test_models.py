from pytest import MonkeyPatch

from deepege_connector.config import Settings
from deepege_connector.models import (
    ERROR_HTTP_STATUS,
    POLL_AFTER_MS,
    ErrorCode,
    JobStatus,
    Principal,
    Scope,
)


def test_job_status_values() -> None:
    assert {status.value for status in JobStatus} == {
        "planning",
        "awaiting_confirmation",
        "awaiting_input",
        "producing",
        "succeeded",
        "failed",
        "cancelled",
    }


def test_required_error_codes_exist() -> None:
    required = {
        "quote_stale",
        "credits_insufficient",
        "invalid_input",
        "idempotency_conflict",
        "not_found",
        "insufficient_scope",
        "rate_limited",
    }
    assert required <= {code.value for code in ErrorCode}
    assert "quote_expired" not in {code.value for code in ErrorCode}
    assert set(ERROR_HTTP_STATUS) == set(ErrorCode)


def test_provisional_poll_after_ms() -> None:
    assert POLL_AFTER_MS[JobStatus.PLANNING] == 3000
    assert POLL_AFTER_MS[JobStatus.AWAITING_CONFIRMATION] == 10000
    assert POLL_AFTER_MS[JobStatus.AWAITING_INPUT] == 10000
    assert POLL_AFTER_MS[JobStatus.PRODUCING] == 15000


def test_principal_roundtrip() -> None:
    principal = Principal(
        account_id="acc_1",
        tenant_id="acc_1",
        auth_method="api_key",
        key_id="key_1",
        scopes=[Scope.ACCOUNT_READ],
    )
    assert principal.model_dump()["auth_method"] == "api_key"


def test_settings_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPEGE_API_BASE_URL", "https://example.com")
    monkeypatch.setenv("DEEPEGE_MCP_PORT", "9090")
    settings = Settings.from_env()
    assert settings.api_base_url == "https://example.com"
    assert settings.mcp_port == 9090
    assert settings.mcp_host == "127.0.0.1"
