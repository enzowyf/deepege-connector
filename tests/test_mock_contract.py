"""Prove mock responses conform to openapi/open-v1.yaml."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema.exceptions import ValidationError

from tests.conftest import ALICE, BOB, BROKE, auth, idem
from tests.helpers import SPEC_PATH, load_spec, validate_schema

SPEC = load_spec()


def _create(
    client: TestClient, prompt: str = "A sunrise over the sea", token: str = ALICE
) -> dict[str, Any]:
    response = client.post(
        "/open/v1/video-requests",
        headers=idem(f"contract-{uuid.uuid4()}", token),
        json={"prompt": prompt},
    )
    assert response.status_code == 200, response.text
    validate_schema("Job", response.json())
    return response.json()


def _poll(client: TestClient, job_id: str, status: str, token: str = ALICE) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for _ in range(8):
        response = client.get(f"/open/v1/jobs/{job_id}", headers=auth(token))
        assert response.status_code == 200, response.text
        validate_schema("Job", response.json())
        body = response.json()
        if body["status"] == status:
            return body
    raise AssertionError(f"did not reach {status}: {body}")


def test_happy_path_responses_match_job_schema(client: TestClient) -> None:
    created = _create(client)
    snapshot = _poll(client, created["job_id"], "awaiting_confirmation")
    validate_schema("Plan", snapshot["plan"])
    confirmed = client.post(
        f"/open/v1/video-requests/{created['job_id']}/plan-decisions",
        headers=idem(f"contract-confirm-{created['job_id']}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    assert confirmed.status_code == 200
    validate_schema("Job", confirmed.json())
    done = _poll(client, created["job_id"], "succeeded")
    validate_schema("Result", done["result"])


def test_error_bodies_match_envelope(client: TestClient) -> None:
    cases = [
        client.get("/open/v1/me"),
        client.get("/open/v1/jobs/job_missing", headers=auth(ALICE)),
        client.post(
            "/open/v1/video-requests",
            headers=auth(ALICE),
            json={"prompt": "no idempotency key"},
        ),
        client.get("/open/v1/me", headers=auth("sk-test-limited")),
    ]
    job_id = _create(client, token=BROKE)["job_id"]
    snapshot = _poll(client, job_id, "awaiting_confirmation", token=BROKE)
    cases.append(
        client.post(
            f"/open/v1/video-requests/{job_id}/plan-decisions",
            headers=idem(f"contract-broke-{job_id}", BROKE),
            json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
        )
    )
    other = _create(client)["job_id"]
    cases.append(client.get(f"/open/v1/jobs/{other}", headers=auth(BOB)))

    for response in cases:
        assert response.status_code >= 400
        validate_schema("ErrorEnvelope", response.json())
        assert "code" not in response.json() or "error" in response.json()
        assert isinstance(response.json()["error"]["code"], str)
        assert isinstance(response.json()["error"]["retryable"], bool)


def test_me_and_oauth_responses_match_schema(client: TestClient) -> None:
    me = client.get("/open/v1/me", headers=auth(ALICE))
    assert me.status_code == 200
    validate_schema("Me", me.json())

    basic = ("test-mcp-client", "test-mcp-secret")
    introspect = client.post("/oauth/introspect", auth=basic, data={"token": "atok_alice"})
    assert introspect.status_code == 200
    validate_schema("IntrospectResponse", introspect.json())

    inactive = client.post("/oauth/introspect", auth=basic, data={"token": "unknown"})
    assert inactive.status_code == 200
    validate_schema("IntrospectResponse", inactive.json())

    exchanged = client.post(
        "/oauth/token",
        auth=basic,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": "atok_alice",
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        },
    )
    assert exchanged.status_code == 200
    validate_schema("TokenExchangeResponse", exchanged.json())


def test_schema_rejects_an_invalid_job() -> None:
    with pytest.raises(ValidationError):
        validate_schema("Job", {"job_id": "job_1"})  # missing status


def test_nullable_result_and_plan_fields_match_schema(client: TestClient) -> None:
    created = _create(client, prompt="A sketch [no-cover] [unknown-duration] [no-max]")
    snapshot = _poll(client, created["job_id"], "awaiting_confirmation")
    assert snapshot["plan"]["max_credits"] is None
    validate_schema("Plan", snapshot["plan"])
    confirm = client.post(
        f"/open/v1/video-requests/{created['job_id']}/plan-decisions",
        headers=idem(f"contract-nulls-{created['job_id']}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    assert confirm.status_code == 200
    done = _poll(client, created["job_id"], "succeeded")
    validate_schema("Result", done["result"])
    assert done["result"]["cover_url"] is None
    assert done["result"]["duration_seconds"] is None


def test_contract_marks_open_questions() -> None:
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert "x-open-question" in text
    assert "poll_after_ms" in text
    assert "quote_stale" in text
    assert "actual_credits" in text
    assert "charges_before_confirm" in text
    assert "max_credits" in text
    assert "play_url" in text
    assert "web_url" in text


def test_schemathesis_can_load_the_contract(client: TestClient) -> None:
    """Load the contract with schemathesis and validate a recorded happy path."""
    schemathesis = pytest.importorskip("schemathesis")
    schema = schemathesis.openapi.from_path(str(SPEC_PATH))
    assert schema is not None
    assert "/open/v1/jobs/{job_id}" in list(schema)

    created = _create(client)
    job_id = created["job_id"]
    snapshot = _poll(client, job_id, "awaiting_confirmation")
    confirm = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"schema-confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    assert confirm.status_code == 200
    done = _poll(client, job_id, "succeeded")
    validate_schema("Job", confirm.json())
    validate_schema("Job", done)
    validate_schema("Job", snapshot)
