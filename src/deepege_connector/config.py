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
    connector to call the main service. ``client_id`` / ``client_secret`` are
    the official hosted connector's service credentials; a self-hosted
    instance leaves them unset and uses a user API key instead.
    """

    api_base_url: str | None
    mcp_host: str
    mcp_port: int
    client_id: str | None
    client_secret: str | None

    @classmethod
    def from_env(cls) -> Settings:
        port_raw = _env("DEEPEGE_MCP_PORT", "8080") or "8080"
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError("DEEPEGE_MCP_PORT must be an integer") from exc
        return cls(
            api_base_url=_env("DEEPEGE_API_BASE_URL"),
            mcp_host=_env("DEEPEGE_MCP_HOST", "127.0.0.1") or "127.0.0.1",
            mcp_port=port,
            client_id=_env("DEEPEGE_CLIENT_ID"),
            client_secret=_env("DEEPEGE_CLIENT_SECRET"),
        )
