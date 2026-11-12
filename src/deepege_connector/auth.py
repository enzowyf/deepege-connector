"""Resolve the outbound credential used to call the Deepege Open API.

Self-hosted mode (implemented)
    The MCP client sends a user API key as ``Authorization: Bearer …`` on
    the Streamable HTTP request, or the process is started with
    ``DEEPEGE_API_KEY``. The connector forwards that key unchanged to
    ``/open/v1``.

Hosted mode (TODO, not implemented)
    The official hosted connector will act as an MCP resource server. The
    main service will issue its own OAuth access tokens bound to the MCP
    resource (RFC 8707). The connector will then:

    1. Accept that access token on the MCP transport.
    2. Introspect it at ``POST /oauth/introspect`` (RFC 7662) using the
       service ``client_id`` / ``client_secret``.
    3. Exchange it at ``POST /oauth/token`` (RFC 8693 token-exchange) for
       a short-lived downstream token.
    4. Call ``/open/v1`` with the downstream token. The user-facing OAuth
       access token is never passed through to the Open API.

    Service credentials come from ``DEEPEGE_CLIENT_ID`` and
    ``DEEPEGE_CLIENT_SECRET``. Until this seam is implemented, a request
    that does not supply an API key is rejected.
"""

from __future__ import annotations

from collections.abc import Mapping


class MissingCredentialsError(Exception):
    """No user API key was provided on the request or in the environment."""


def resolve_bearer_token(
    headers: Mapping[str, str] | None,
    *,
    fallback: str | None = None,
) -> str:
    """Return the Bearer token from ``headers``, or ``fallback``.

    Header lookup is case-insensitive. The returned value is the raw token
    without the ``Bearer `` prefix.
    """
    token = _authorization_token(headers)
    if token:
        return token
    if fallback:
        return fallback
    raise MissingCredentialsError(
        "A user API key is required. Send it as an Authorization: Bearer "
        "header on the MCP request, or set DEEPEGE_API_KEY."
    )


def _authorization_token(headers: Mapping[str, str] | None) -> str | None:
    if not headers:
        return None
    raw: str | None = None
    try:
        getter = getattr(headers, "get", None)
        if callable(getter):
            raw = getter("authorization") or getter("Authorization")
    except Exception:  # noqa: BLE001
        raw = None
    if raw is None:
        for key, value in headers.items():
            if key.lower() == "authorization":
                raw = value
                break
    if not raw:
        return None
    scheme, _, remainder = raw.strip().partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = remainder.strip()
    return token or None
