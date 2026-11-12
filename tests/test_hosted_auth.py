"""Hosted-mode resource server: metadata, challenges, introspect, and exchange."""

from __future__ import annotations

import socket
import threading
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import uvicorn
from starlette.testclient import TestClient

from deepege_connector.api import OpenAPIClient
from deepege_connector.auth import DownstreamTokenCache, audience_matches, normalize_resource
from deepege_connector.config import Settings
from deepege_connector.server import create_server
from tests.mock_core.app import create_app
from tests.mock_core.store import Store

RESOURCE = "http://127.0.0.1:8081/mcp"
CLIENT_ID = "test-mcp-client"
CLIENT_SECRET = "test-mcp-secret"
ATOK = "atok_alice"


def _hosted_settings() -> Settings:
    return Settings(
        api_base_url="http://mock.local",
        mcp_host="127.0.0.1",
        mcp_port=8081,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        auth_mode="hosted",
        mcp_resource=RESOURCE,
        authorization_server="http://mock.local",
    )


@pytest.fixture
async def api_client(store: Store) -> AsyncIterator[OpenAPIClient]:
    transport = httpx.ASGITransport(app=create_app(store))
    async with httpx.AsyncClient(transport=transport, base_url="http://mock.local") as http:
        yield OpenAPIClient("http://mock.local", http_client=http)


@pytest.fixture
def hosted_app(api_client: OpenAPIClient) -> Any:
    server = create_server(_hosted_settings(), api_client=api_client)
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        host="127.0.0.1",
    )


def test_audience_comparison_ignores_trailing_slash() -> None:
    assert normalize_resource("http://127.0.0.1:8081/mcp/") == normalize_resource(RESOURCE)
    assert audience_matches({"aud": "http://127.0.0.1:8081/mcp/"}, RESOURCE)
    assert audience_matches({"resource": RESOURCE}, RESOURCE)
    assert not audience_matches({"aud": "https://other.example/mcp"}, RESOURCE)
    assert not audience_matches({"active": True}, RESOURCE)


def test_cache_expires_before_token() -> None:
    clock = {"t": 1000.0}
    cache = DownstreamTokenCache(skew_seconds=30, clock=lambda: clock["t"])
    cache.put(
        "user-token",
        access_token="dtok_cached",
        expires_in=300,
        scopes=("generate:video",),
        resource=RESOURCE,
        subject="acc",
        client_id="client",
    )
    assert cache.get("user-token") is not None
    clock["t"] = 1000.0 + 269
    assert cache.get("user-token") is not None
    clock["t"] = 1000.0 + 270
    assert cache.get("user-token") is None


def test_protected_resource_metadata_and_unauthorized_challenge(hosted_app: Any) -> None:
    with TestClient(hosted_app, base_url="http://127.0.0.1:8081") as client:
        response = client.get("/.well-known/oauth-protected-resource/mcp")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["resource"].rstrip("/") == RESOURCE
        assert "http://mock.local" in [item.rstrip("/") for item in body["authorization_servers"]]
        assert set(body["scopes_supported"]) == {
            "account:read",
            "jobs:read",
            "generate:video",
        }
        assert body["bearer_methods_supported"] == ["header"]

        denied = client.post("/mcp")
        assert denied.status_code == 401
        challenge = denied.headers.get("www-authenticate") or denied.headers.get("WWW-Authenticate")
        assert challenge is not None
        assert challenge.startswith("Bearer ")
        assert 'error="invalid_token"' in challenge
        assert "resource_metadata=" in challenge
        assert "oauth-protected-resource/mcp" in challenge


def test_invalid_and_wrong_audience_tokens_are_unauthorized(hosted_app: Any) -> None:
    with TestClient(hosted_app, base_url="http://127.0.0.1:8081") as client:
        for token in ("unknown-token", "atok_revoked", "atok_wrong_resource", "sk-test-alice"):
            denied = client.post("/mcp", headers={"Authorization": f"Bearer {token}"})
            assert denied.status_code == 401, (token, denied.text)


def test_insufficient_scope_is_forbidden(hosted_app: Any) -> None:
    with TestClient(hosted_app, base_url="http://127.0.0.1:8081") as client:
        denied = client.post(
            "/mcp",
            headers={"Authorization": "Bearer atok_readonly"},
        )
        assert denied.status_code == 403, denied.text
        challenge = denied.headers.get("www-authenticate") or ""
        assert "insufficient_scope" in challenge


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def hosted_http_url(hosted_app: Any) -> Iterator[str]:
    port = _free_port()
    config = uvicorn.Config(
        hosted_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="on",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            if server.started:
                break
            thread.join(0.05)
        if not server.started:
            raise RuntimeError("uvicorn did not start")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_hosted_tools_use_exchanged_downstream_token(hosted_http_url: str) -> None:
    httpx2 = pytest.importorskip("httpx2")
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {ATOK}"}
    http = httpx2.AsyncClient(headers=headers)
    try:
        async with Client(streamable_http_client(hosted_http_url, http_client=http)) as client:
            created = await client.call_tool(
                "deepege_create_video_request",
                {"prompt": "A sunrise over the sea", "aspect_ratio": "16:9"},
            )
            assert created.is_error is not True
            payload = created.structured_content
            if not isinstance(payload, dict):
                text = "".join(getattr(block, "text", "") or "" for block in created.content or [])
                start, end = text.find("{"), text.rfind("}")
                payload = __import__("json").loads(text[start : end + 1])
            assert "job_id" in payload
            assert payload["status"] in {"planning", "awaiting_confirmation"}
    finally:
        await http.aclose()
