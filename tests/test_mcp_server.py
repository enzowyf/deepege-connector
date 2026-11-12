"""End-to-end MCP tool tests against the in-repo mock Open API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from deepege_connector.api import OpenAPIClient, result_links_expired
from deepege_connector.config import Settings
from deepege_connector.models import Result
from deepege_connector.server import create_server
from tests.conftest import ALICE, BOB, BROKE
from tests.mock_core.app import create_app
from tests.mock_core.store import Store

LIMITED = "sk-test-limited"


def _settings(api_key: str | None) -> Settings:
    return Settings(
        api_base_url="http://mock.local",
        mcp_host="127.0.0.1",
        mcp_port=8080,
        client_id=None,
        client_secret=None,
        api_key=api_key,
    )


@pytest.fixture
async def api_client(store: Store) -> AsyncIterator[OpenAPIClient]:
    transport = httpx.ASGITransport(app=create_app(store))
    async with httpx.AsyncClient(transport=transport, base_url="http://mock.local") as http:
        yield OpenAPIClient("http://mock.local", http_client=http)


def _tool_text(result: Any) -> str:
    parts: list[str] = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def tool_payload(result: Any) -> dict[str, Any]:
    if result.structured_content is not None and isinstance(result.structured_content, dict):
        return result.structured_content
    text = _tool_text(result)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end >= start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise AssertionError(f"tool result is not an object: {text}")


def assert_ok(result: Any) -> dict[str, Any]:
    payload = tool_payload(result)
    assert result.is_error is not True, payload
    return payload


def assert_error(result: Any) -> dict[str, Any]:
    assert result.is_error is True
    payload = tool_payload(result)
    assert "error" in payload
    return payload


async def poll_until(
    client: Client,
    job_id: str,
    status: str,
    *,
    attempts: int = 6,
) -> dict[str, Any]:
    last: dict[str, Any] | None = None
    for _ in range(attempts):
        result = await client.call_tool("deepege_get_job", {"job_id": job_id})
        last = assert_ok(result)
        if last["status"] == status:
            return last
    raise AssertionError(f"job {job_id} did not reach {status}: {last}")


@pytest.fixture
def server(api_client: OpenAPIClient) -> MCPServer:
    return create_server(_settings(ALICE), api_client=api_client)


async def test_lists_the_five_tools(server: MCPServer) -> None:
    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {
            "deepege_create_video_request",
            "deepege_get_job",
            "deepege_confirm_plan",
            "deepege_answer_question",
            "deepege_cancel_job",
        }


async def test_happy_path_create_confirm_succeeds(server: MCPServer) -> None:
    async with Client(server) as client:
        created = assert_ok(
            await client.call_tool(
                "deepege_create_video_request",
                {
                    "prompt": "A sunrise over the sea",
                    "aspect_ratio": "16:9",
                    "duration_seconds": 15,
                    "idempotency_key": "demo-happy-1",
                },
            )
        )
        assert created["status"] == "planning"
        assert created["job_id"]
        assert created["poll_after_ms"] == 3000

        job = await poll_until(client, created["job_id"], "awaiting_confirmation")
        assert job["poll_after_ms"] == 10000
        plan = job["plan"]
        assert plan["plan_id"]
        assert plan["estimated_credits"] == 100
        assert plan["max_credits"] == 150
        assert "charges_before_confirm" in plan

        confirmed = assert_ok(
            await client.call_tool(
                "deepege_confirm_plan",
                {
                    "job_id": job["job_id"],
                    "plan_id": plan["plan_id"],
                    "action": "confirm",
                },
            )
        )
        assert confirmed["status"] in {"producing", "succeeded"}

        done = await poll_until(client, job["job_id"], "succeeded")
        result = done["result"]
        assert result["play_url"]
        assert result["play_url_expires_at"]
        assert result["web_url"]
        assert result["actual_credits"] is not None
        assert "cover_url" in result
        assert "duration_seconds" in result


async def test_ask_question_then_answer(server: MCPServer) -> None:
    async with Client(server) as client:
        created = assert_ok(
            await client.call_tool(
                "deepege_create_video_request",
                {"prompt": "A quiet forest [ask]"},
            )
        )
        job = await poll_until(client, created["job_id"], "awaiting_confirmation")
        assert_ok(
            await client.call_tool(
                "deepege_confirm_plan",
                {
                    "job_id": job["job_id"],
                    "plan_id": job["plan"]["plan_id"],
                    "action": "confirm",
                },
            )
        )
        waiting = await poll_until(client, job["job_id"], "awaiting_input")
        question = waiting["question"]
        assert question["question_id"]
        assert question["kind"] in {"choice", "text"}

        answer_args: dict[str, Any] = {
            "job_id": job["job_id"],
            "question_id": question["question_id"],
        }
        if question["kind"] == "choice":
            answer_args["option_id"] = question["options"][0]["id"]
        else:
            answer_args["text"] = "A mossy path at dusk"
        assert_ok(await client.call_tool("deepege_answer_question", answer_args))
        done = await poll_until(client, job["job_id"], "succeeded")
        assert done["result"]["play_url"]


async def test_quote_stale_on_non_current_plan(server: MCPServer) -> None:
    async with Client(server) as client:
        created = assert_ok(
            await client.call_tool(
                "deepege_create_video_request",
                {"prompt": "A city at night [quote-stale]"},
            )
        )
        job = await poll_until(client, created["job_id"], "awaiting_confirmation")
        failed = assert_error(
            await client.call_tool(
                "deepege_confirm_plan",
                {
                    "job_id": job["job_id"],
                    "plan_id": job["plan"]["plan_id"],
                    "action": "confirm",
                },
            )
        )
        assert failed["error"]["code"] == "quote_stale"
        assert failed["error"]["retryable"] is True
        assert failed["http_status"] == 409


async def test_credits_insufficient_on_confirm(api_client: OpenAPIClient) -> None:
    server = create_server(_settings(BROKE), api_client=api_client)
    async with Client(server) as client:
        created = assert_ok(
            await client.call_tool(
                "deepege_create_video_request",
                {"prompt": "A mountain lake"},
            )
        )
        job = await poll_until(client, created["job_id"], "awaiting_confirmation")
        failed = assert_error(
            await client.call_tool(
                "deepege_confirm_plan",
                {
                    "job_id": job["job_id"],
                    "plan_id": job["plan"]["plan_id"],
                    "action": "confirm",
                },
            )
        )
        assert failed["error"]["code"] == "credits_insufficient"
        assert failed["error"]["retryable"] is False
        assert failed["http_status"] == 402
        assert failed["error"]["recharge_url"]


async def test_cross_tenant_job_is_not_found(api_client: OpenAPIClient) -> None:
    alice = create_server(_settings(ALICE), api_client=api_client)
    bob = create_server(_settings(BOB), api_client=api_client)
    async with Client(alice) as alice_client:
        created = assert_ok(
            await alice_client.call_tool(
                "deepege_create_video_request",
                {"prompt": "A desert road"},
            )
        )
        job_id = created["job_id"]
    async with Client(bob) as bob_client:
        failed = assert_error(await bob_client.call_tool("deepege_get_job", {"job_id": job_id}))
        assert failed["error"]["code"] == "not_found"
        assert failed["http_status"] == 404


async def test_rate_limit_maps_retry_after(api_client: OpenAPIClient) -> None:
    server = create_server(_settings(LIMITED), api_client=api_client)
    async with Client(server) as client:
        failed = assert_error(
            await client.call_tool(
                "deepege_create_video_request",
                {"prompt": "Anything"},
            )
        )
        assert failed["error"]["code"] == "rate_limited"
        assert failed["error"]["retryable"] is True
        assert failed["http_status"] == 429
        assert failed["retry_after"] == 12


async def test_get_job_renews_result_links(server: MCPServer, store: Store) -> None:
    async with Client(server) as client:
        created = assert_ok(
            await client.call_tool(
                "deepege_create_video_request",
                {"prompt": "A harbour at dawn"},
            )
        )
        job = await poll_until(client, created["job_id"], "awaiting_confirmation")
        assert_ok(
            await client.call_tool(
                "deepege_confirm_plan",
                {
                    "job_id": job["job_id"],
                    "plan_id": job["plan"]["plan_id"],
                    "action": "confirm",
                },
            )
        )
        done = await poll_until(client, job["job_id"], "succeeded")
        original = done["result"]["play_url"]

        forced = assert_ok(
            await client.call_tool(
                "deepege_get_job",
                {"job_id": job["job_id"], "renew_result_links": True},
            )
        )
        assert forced["result"]["play_url"] != original

        record = store.jobs[job["job_id"]]
        assert record.result is not None
        record.result.play_url_expires_at = "2020-01-01T00:00:00Z"
        before_expiry_renewal = forced["result"]["play_url"]
        renewed = assert_ok(await client.call_tool("deepege_get_job", {"job_id": job["job_id"]}))
        assert renewed["result"]["play_url"] != before_expiry_renewal


async def test_cancel_job(server: MCPServer) -> None:
    async with Client(server) as client:
        created = assert_ok(
            await client.call_tool(
                "deepege_create_video_request",
                {"prompt": "A cancelled draft"},
            )
        )
        cancelled = assert_ok(
            await client.call_tool(
                "deepege_cancel_job",
                {"job_id": created["job_id"]},
            )
        )
        assert cancelled["status"] == "cancelled"
        assert cancelled["refund"]["status"] in {"none", "full", "partial"}


async def test_missing_api_key_is_unauthorized(api_client: OpenAPIClient) -> None:
    server = create_server(_settings(None), api_client=api_client)
    async with Client(server) as client:
        failed = assert_error(
            await client.call_tool(
                "deepege_create_video_request",
                {"prompt": "No credentials"},
            )
        )
        assert failed["error"]["code"] == "unauthorized"


def test_result_links_expired_unit() -> None:
    result = Result(
        play_url="https://media.example.com/play/j?sig=abc",
        play_url_expires_at="2020-01-01T00:00:00Z",
        cover_url=None,
        cover_url_expires_at=None,
        web_url="https://www.deepege.com/works/j",
        duration_seconds=15,
        actual_credits=100,
    )
    assert result_links_expired(result) is True
