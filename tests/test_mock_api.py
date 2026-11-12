"""Behavioural tests for the in-memory mock Open API."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import ALICE, BOB, BROKE, READONLY, auth, idem
from tests.mock_core.app import create_app
from tests.mock_core.store import Clock, Store


def _err(response) -> dict:
    body = response.json()
    assert "error" in body, body
    return body["error"]


def _poll_until(
    client: TestClient, job_id: str, status: str, token: str = ALICE, attempts: int = 8
) -> dict:
    body = {}
    for _ in range(attempts):
        response = client.get(f"/open/v1/jobs/{job_id}", headers=auth(token))
        assert response.status_code == 200, response.text
        body = response.json()
        if body["status"] == status:
            return body
    raise AssertionError(f"did not reach {status}: {body}")


def _create(client: TestClient, prompt: str = "A sunrise over the sea", token: str = ALICE) -> dict:
    response = client.post(
        "/open/v1/video-requests",
        headers=idem(f"create-{uuid.uuid4()}", token),
        json={"prompt": prompt, "preferences": {"aspect_ratio": "16:9", "duration_seconds": 15}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] in {"planning", "awaiting_confirmation"}
    assert "job_id" in body
    return body


def test_happy_path_create_confirm_succeed(client: TestClient) -> None:
    created = _create(client)
    job_id = created["job_id"]
    assert created["status"] == "planning"
    assert created["poll_after_ms"] == 3000

    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    plan = snapshot["plan"]
    assert plan["plan_id"].startswith("plan_")
    assert plan["plan_id"] != job_id
    assert plan["title"]
    assert plan["duration_seconds"] == 15
    assert plan["style"]
    assert plan["estimated_credits"] == 100
    assert plan["max_credits"] == 150
    assert plan["charges_before_confirm"] == 0
    assert plan["credit_balance"] == 1000
    assert "quote_expires_at" not in plan
    assert "expires_at" not in plan
    assert snapshot["poll_after_ms"] == 10000

    confirmed = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": plan["plan_id"], "action": "confirm"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "producing"
    assert confirmed.json()["poll_after_ms"] == 15000
    assert "credits_charged" not in confirmed.json()
    # Confirm authorizes; settlement happens when the job succeeds.
    assert client.get("/open/v1/me", headers=auth(ALICE)).json()["credit_balance"] == 1000

    done = _poll_until(client, job_id, "succeeded")
    result = done["result"]
    assert result["play_url"].startswith("https://")
    assert result["cover_url"].startswith("https://")
    assert result["web_url"].startswith("https://")
    assert result["play_url_expires_at"]
    assert result["cover_url_expires_at"]
    assert result["duration_seconds"] == 15
    assert result["actual_credits"] == 100
    assert "poll_after_ms" not in done

    me = client.get("/open/v1/me", headers=auth(ALICE))
    assert me.status_code == 200
    assert me.json()["credit_balance"] == 900


def test_actual_credits_may_differ_from_estimate(client: TestClient) -> None:
    job_id = _create(client, prompt="A city at dusk [actual-round]")["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    assert snapshot["plan"]["estimated_credits"] == 100
    client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    done = _poll_until(client, job_id, "succeeded")
    assert done["result"]["actual_credits"] == 80
    assert done["result"]["actual_credits"] != snapshot["plan"]["estimated_credits"]
    assert client.get("/open/v1/me", headers=auth(ALICE)).json()["credit_balance"] == 920


def test_charges_before_confirm_listed_on_plan(client: TestClient) -> None:
    job_id = _create(client, prompt="A still lake [planning-charge]")["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    assert snapshot["plan"]["charges_before_confirm"] == 5


def test_revise_issues_new_plan_and_stales_the_old_one(client: TestClient) -> None:
    job_id = _create(client)["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    old_plan = snapshot["plan"]["plan_id"]
    revised = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"revise-{job_id}"),
        json={"plan_id": old_plan, "action": "revise", "comment": "Make it shorter."},
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["status"] == "planning"
    new_snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    new_plan = new_snapshot["plan"]["plan_id"]
    assert new_plan != old_plan

    stale = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"stale-{job_id}"),
        json={"plan_id": old_plan, "action": "confirm"},
    )
    assert stale.status_code == 409
    assert _err(stale)["code"] == "quote_stale"
    assert _err(stale)["retryable"] is True


def test_quote_stale_on_price_or_manuscript_change(client: TestClient) -> None:
    job_id = _create(client, prompt="A windy ridge [quote-stale]")["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    confirmed = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    assert confirmed.status_code == 409
    assert _err(confirmed)["code"] == "quote_stale"


def test_reject_cancels_without_charge(client: TestClient) -> None:
    job_id = _create(client)["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    rejected = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"reject-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "reject"},
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["status"] == "cancelled"
    assert body["refund"]["status"] == "none"
    me = client.get("/open/v1/me", headers=auth(ALICE)).json()
    assert me["credit_balance"] == 1000


def test_cancel_during_producing_refunds(client: TestClient) -> None:
    job_id = _create(client)["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    cancelled = client.post(f"/open/v1/jobs/{job_id}/cancel", headers=auth(ALICE))
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["refund"]["status"] == "full"
    assert client.get("/open/v1/me", headers=auth(ALICE)).json()["credit_balance"] == 1000


def test_cancel_after_success_rejected(client: TestClient) -> None:
    job_id = _create(client)["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    _poll_until(client, job_id, "succeeded")
    cancelled = client.post(f"/open/v1/jobs/{job_id}/cancel", headers=auth(ALICE))
    assert cancelled.status_code == 409
    assert _err(cancelled)["code"] == "job_not_cancellable"


def test_idempotent_create_replay_and_conflict(client: TestClient) -> None:
    key = f"idem-{uuid.uuid4()}"
    first = client.post(
        "/open/v1/video-requests",
        headers=idem(key),
        json={"prompt": "A quiet forest"},
    )
    replay = client.post(
        "/open/v1/video-requests",
        headers=idem(key),
        json={"prompt": "A quiet forest"},
    )
    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json()["job_id"] == replay.json()["job_id"]

    conflict = client.post(
        "/open/v1/video-requests",
        headers=idem(key),
        json={"prompt": "A busy city"},
    )
    assert conflict.status_code == 409
    assert _err(conflict)["code"] == "idempotency_conflict"


def test_confirm_is_idempotent_and_authorizes_once(client: TestClient) -> None:
    job_id = _create(client)["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    payload = {"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"}
    headers = idem(f"confirm-once-{job_id}")
    first = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions", headers=headers, json=payload
    )
    second = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions", headers=headers, json=payload
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "producing"
    _poll_until(client, job_id, "succeeded")
    assert client.get("/open/v1/me", headers=auth(ALICE)).json()["credit_balance"] == 900


def test_insufficient_credits(client: TestClient) -> None:
    job_id = _create(client, token=BROKE)["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation", token=BROKE)
    confirmed = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}", BROKE),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    assert confirmed.status_code == 402
    body = _err(confirmed)
    assert body["code"] == "credits_insufficient"
    assert body["recharge_url"].startswith("https://")
    assert body["retryable"] is False
    assert client.get("/open/v1/me", headers=auth(BROKE)).json()["credit_balance"] == 10


def test_cross_tenant_is_not_found(client: TestClient) -> None:
    job_id = _create(client, token=ALICE)["job_id"]
    response = client.get(f"/open/v1/jobs/{job_id}", headers=auth(BOB))
    assert response.status_code == 404
    assert _err(response)["code"] == "not_found"
    missing = client.get("/open/v1/jobs/job_does_not_exist", headers=auth(ALICE))
    assert missing.status_code == 404


def test_insufficient_scope(client: TestClient) -> None:
    response = client.post(
        "/open/v1/video-requests",
        headers=idem("readonly-create", READONLY),
        json={"prompt": "Should be rejected"},
    )
    assert response.status_code == 403
    assert _err(response)["code"] == "insufficient_scope"
    assert _err(response)["required_scope"] == "generate:video"


def test_mid_job_question_and_invalid_answer(client: TestClient) -> None:
    job_id = _create(client, prompt="A dancer on a rooftop [ask]")["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    waiting = _poll_until(client, job_id, "awaiting_input")
    assert waiting["poll_after_ms"] == 10000
    question = waiting["question"]
    assert question["text"]
    assert question["kind"] == "choice"
    assert question["options"]
    assert question["question_id"].startswith("q_")

    bad = client.post(
        f"/open/v1/video-requests/{job_id}/answers",
        headers=auth(ALICE),
        json={"question_id": question["question_id"], "option_id": "not-a-real-option"},
    )
    assert bad.status_code == 400
    assert _err(bad)["code"] == "invalid_input"
    assert _err(bad)["question"]["question_id"] == question["question_id"]

    ok = client.post(
        f"/open/v1/video-requests/{job_id}/answers",
        headers=auth(ALICE),
        json={"question_id": question["question_id"], "option_id": question["options"][0]["id"]},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "producing"
    done = _poll_until(client, job_id, "succeeded")
    assert done["result"]["actual_credits"] == 100


def test_failed_production_refunds(client: TestClient) -> None:
    job_id = _create(client, prompt="A storm at sea [fail]")["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    failed = _poll_until(client, job_id, "failed")
    assert failed["error"]["refund"]["status"] == "full"
    assert failed["error"]["retryable"] is True
    assert client.get("/open/v1/me", headers=auth(ALICE)).json()["credit_balance"] == 1000


def test_unrecoverable_interruption_is_failed_and_retryable(client: TestClient) -> None:
    job_id = _create(client, prompt="A long take [unrecoverable]")["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    failed = _poll_until(client, job_id, "failed")
    assert failed["error"]["retryable"] is True
    assert failed["error"]["code"] == "interrupted_unrecoverable"


def test_renew_result_links(client: TestClient) -> None:
    job_id = _create(client)["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    done = _poll_until(client, job_id, "succeeded")
    renewed = client.post(f"/open/v1/jobs/{job_id}/result-links", headers=auth(ALICE))
    assert renewed.status_code == 200
    assert renewed.json()["result"]["play_url"] != done["result"]["play_url"]
    assert renewed.json()["result"]["cover_url"] != done["result"]["cover_url"]
    assert renewed.json()["result"]["actual_credits"] == done["result"]["actual_credits"]


def test_oauth_introspect_and_token_exchange(client: TestClient) -> None:
    basic = ("test-mcp-client", "test-mcp-secret")
    unknown = client.post("/oauth/introspect", auth=basic, data={"token": "no-such-token"})
    assert unknown.status_code == 200
    assert unknown.json() == {"active": False}

    active = client.post("/oauth/introspect", auth=basic, data={"token": "atok_alice"})
    assert active.status_code == 200
    body = active.json()
    assert body["active"] is True
    assert body["account_id"] == "acc_alice_oauth"
    assert "generate:video" in body["scopes"]

    revoked = client.post("/oauth/introspect", auth=basic, data={"token": "atok_revoked"})
    assert revoked.json()["active"] is False
    assert revoked.json()["revoked"] is True

    banned = client.post("/oauth/introspect", auth=basic, data={"token": "atok_banned"})
    assert banned.json()["active"] is False
    assert banned.json()["banned"] is True

    exchanged = client.post(
        "/oauth/token",
        auth=basic,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": "atok_alice",
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        },
    )
    assert exchanged.status_code == 200, exchanged.text
    token = exchanged.json()["access_token"]
    assert exchanged.json()["token_type"] == "Bearer"
    me = client.get("/open/v1/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["account_id"] == "acc_alice_oauth"


def test_missing_auth_and_rate_limit(client: TestClient) -> None:
    missing = client.get("/open/v1/me")
    assert missing.status_code == 401
    assert _err(missing)["code"] == "unauthorized"
    limited = client.get("/open/v1/me", headers=auth("sk-test-limited"))
    assert limited.status_code == 429
    assert _err(limited)["code"] == "rate_limited"
    assert _err(limited)["retryable"] is True


def test_disabled_key_returns_unauthorized(client: TestClient) -> None:
    response = client.get("/open/v1/me", headers=auth("sk-test-disabled"))
    assert response.status_code == 401
    assert _err(response)["code"] == "unauthorized"


def test_result_cover_and_duration_may_be_null(client: TestClient) -> None:
    job_id = _create(client, prompt="A quiet room [no-cover] [unknown-duration]")["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    done = _poll_until(client, job_id, "succeeded")
    result = done["result"]
    assert "cover_url" in result
    assert result["cover_url"] is None
    assert result["cover_url_expires_at"] is None
    assert "duration_seconds" in result
    assert result["duration_seconds"] is None
    assert result["play_url"].startswith("https://")


def test_max_credits_null_means_no_cap(client: TestClient) -> None:
    job_id = _create(client, prompt="An open-ended film [no-max]", token=BROKE)["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation", token=BROKE)
    assert "max_credits" in snapshot["plan"]
    assert snapshot["plan"]["max_credits"] is None
    confirmed = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}", BROKE),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "producing"


def test_failed_job_is_not_recoverable(client: TestClient) -> None:
    job_id = _create(client, prompt="A long take [unrecoverable]")["job_id"]
    snapshot = _poll_until(client, job_id, "awaiting_confirmation")
    client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"confirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    failed = _poll_until(client, job_id, "failed")
    assert failed["error"]["retryable"] is True
    cancelled = client.post(f"/open/v1/jobs/{job_id}/cancel", headers=auth(ALICE))
    assert cancelled.status_code == 409
    assert _err(cancelled)["code"] == "job_not_cancellable"
    replay = client.post(
        f"/open/v1/video-requests/{job_id}/plan-decisions",
        headers=idem(f"reconfirm-{job_id}"),
        json={"plan_id": snapshot["plan"]["plan_id"], "action": "confirm"},
    )
    assert replay.status_code == 400
    assert _err(replay)["code"] == "invalid_input"


def test_time_based_advance(store: Store, clock: Clock) -> None:
    client = TestClient(create_app(store))
    created = _create(client)
    job_id = created["job_id"]
    first = client.get(f"/open/v1/jobs/{job_id}", headers=auth(ALICE)).json()
    assert first["status"] == "planning"
    clock.advance(0.25)
    second = client.get(f"/open/v1/jobs/{job_id}", headers=auth(ALICE)).json()
    assert second["status"] == "awaiting_confirmation"
