"""Runtime settings loaded from environment variables.

Addresses and credentials are never hardcoded; official and self-hosted
deployments inject them at process start.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Process configuration.

    ``api_base_url`` is the public Deepege Open API origin used by the
    connector to call the main service. ``api_key`` is an optional default
    user API key for self-hosted deployments (the MCP request
    ``Authorization`` header, when present, takes precedence).

    ``client_id`` / ``client_secret`` are the official hosted connector's
    service credentials, used in hosted mode for introspection and token
    exchange. ``mcp_resource`` is the MCP resource identifier (RFC 8707 /
    RFC 9728). Self-hosted passthrough is the default.
    """

    api_base_url: str | None
    mcp_host: str
    mcp_port: int
    client_id: str | None
    client_secret: str | None
    api_key: str | None = None
    auth_mode: str = "self_hosted"
    mcp_resource: str | None = None
    authorization_server: str | None = None

    @property
    def hosted(self) -> bool:
        return self.auth_mode == "hosted"

    def validate(self) -> None:
        if self.auth_mode not in {"self_hosted", "hosted"}:
            raise ValueError("DEEPEGE_AUTH_MODE must be self_hosted or hosted")
        if not self.hosted:
            return
        missing: list[str] = []
        if not self.api_base_url:
            missing.append("DEEPEGE_API_BASE_URL")
        if not self.client_id:
            missing.append("DEEPEGE_CLIENT_ID")
        if not self.client_secret:
            missing.append("DEEPEGE_CLIENT_SECRET")
        if not self.mcp_resource:
            missing.append("DEEPEGE_MCP_RESOURCE")
        if missing:
            raise ValueError("hosted mode requires " + ", ".join(missing))

    @classmethod
    def from_env(cls) -> Settings:
        port_raw = _env("DEEPEGE_MCP_PORT", "8080") or "8080"
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError("DEEPEGE_MCP_PORT must be an integer") from exc
        settings = cls(
            api_base_url=_env("DEEPEGE_API_BASE_URL"),
            mcp_host=_env("DEEPEGE_MCP_HOST", "127.0.0.1") or "127.0.0.1",
            mcp_port=port,
            client_id=_env("DEEPEGE_CLIENT_ID"),
            client_secret=_env("DEEPEGE_CLIENT_SECRET"),
            api_key=_env("DEEPEGE_API_KEY"),
            auth_mode=(_env("DEEPEGE_AUTH_MODE", "self_hosted") or "self_hosted"),
            mcp_resource=_env("DEEPEGE_MCP_RESOURCE"),
            authorization_server=_env("DEEPEGE_AUTHORIZATION_SERVER"),
        )
        settings.validate()
        return settings
