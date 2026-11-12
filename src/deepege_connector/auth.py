"""Resolve the outbound credential used to call the Deepege Open API.

Self-hosted mode (default)
    The MCP client sends a user API key as ``Authorization: Bearer …`` on
    the Streamable HTTP request, or the process is started with
    ``DEEPEGE_API_KEY``. The connector forwards that key unchanged to
    ``/open/v1``.

Hosted mode
    The official hosted connector acts as an MCP resource server. The
    main service issues OAuth access tokens bound to the MCP resource
    (RFC 8707). The connector then:

    1. Accepts that access token on the MCP transport.
    2. Introspects it at ``POST /oauth/introspect`` (RFC 7662) using the
       service ``client_id`` / ``client_secret``.
    3. Requires the token to be active, to have an ``aud`` / ``resource``
       equal to the configured MCP resource URL, and to include the
       scopes this connector needs.
    4. Exchanges it at ``POST /oauth/token`` (RFC 8693 token-exchange) for
       a short-lived downstream token, cached until shortly before it
       expires.
    5. Calls ``/open/v1`` with the downstream token. The user-facing OAuth
       access token is never passed through to the Open API.

    Service credentials come from ``DEEPEGE_CLIENT_ID`` and
    ``DEEPEGE_CLIENT_SECRET``. The resource identifier is
    ``DEEPEGE_MCP_RESOURCE``. Tokens are never written to logs.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from mcp.server.auth.provider import AccessToken

from deepege_connector.api import OpenAPIClient, OpenAPIError
from deepege_connector.config import Settings
from deepege_connector.models import Scope

logger = logging.getLogger("deepege_connector.auth")

HOSTED_SCOPES: tuple[str, ...] = Scope.ALL
TOKEN_TYPE_ACCESS = "urn:ietf:params:oauth:token-type:access_token"
TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
CACHE_SKEW_SECONDS = 30


class MissingCredentialsError(Exception):
    """No user API key was provided on the request or in the environment."""


class HostedAuthError(Exception):
    """The presented OAuth access token was rejected."""


@dataclass(frozen=True, slots=True)
class CachedDownstream:
    access_token: str
    scopes: tuple[str, ...]
    expires_at: float
    resource: str | None
    subject: str | None
    client_id: str


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


def normalize_resource(value: str) -> str:
    """Compare resource URLs ignoring a trailing slash on the path."""
    text = value.strip()
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return text.removesuffix("/")
    path = parsed.path.removesuffix("/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def resource_indicators(payload: Mapping[str, object]) -> list[str]:
    values: list[str] = []
    for key in ("aud", "resource"):
        raw = payload.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            if raw:
                values.append(raw)
        elif isinstance(raw, (list, tuple)):
            values.extend(str(item) for item in raw if item)
    return values


def audience_matches(payload: Mapping[str, object], expected: str) -> bool:
    expected_n = normalize_resource(expected)
    found = {normalize_resource(item) for item in resource_indicators(payload)}
    return expected_n in found


def _scopes_from(payload: Mapping[str, object]) -> tuple[str, ...]:
    raw_list = payload.get("scopes")
    if isinstance(raw_list, list) and raw_list:
        return tuple(str(item) for item in raw_list)
    raw = payload.get("scope")
    if isinstance(raw, str) and raw.strip():
        return tuple(raw.split())
    return ()


def _cache_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DownstreamTokenCache:
    """In-memory cache of exchanged downstream tokens.

    Entries expire before the issued ``expires_in`` so a cached token is
    not used at the moment it would be rejected downstream.
    """

    def __init__(
        self,
        *,
        skew_seconds: int = CACHE_SKEW_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._skew = max(1, skew_seconds)
        self._clock = clock
        self._items: dict[str, CachedDownstream] = {}
        self._lock = asyncio.Lock()

    def get(self, user_token: str) -> CachedDownstream | None:
        item = self._items.get(_cache_key(user_token))
        if item is None or item.expires_at <= self._clock():
            return None
        return item

    def put(
        self,
        user_token: str,
        *,
        access_token: str,
        expires_in: int,
        scopes: tuple[str, ...],
        resource: str | None,
        subject: str | None,
        client_id: str,
    ) -> CachedDownstream:
        ttl = expires_in - self._skew
        if ttl < 1:
            ttl = 1 if expires_in > 1 else max(expires_in, 0)
        item = CachedDownstream(
            access_token=access_token,
            scopes=scopes,
            expires_at=self._clock() + ttl,
            resource=resource,
            subject=subject,
            client_id=client_id,
        )
        self._items[_cache_key(user_token)] = item
        return item

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock


class HostedTokenVerifier:
    """Introspect, validate, exchange, and cache hosted-mode tokens."""

    def __init__(
        self,
        api_client: OpenAPIClient,
        settings: Settings,
        *,
        cache: DownstreamTokenCache | None = None,
    ) -> None:
        if not settings.client_id or not settings.client_secret or not settings.mcp_resource:
            raise ValueError("hosted mode requires client credentials and DEEPEGE_MCP_RESOURCE")
        self._api = api_client
        self._client_id = settings.client_id
        self._client_secret = settings.client_secret
        self._resource = settings.mcp_resource
        self._downstream_audience = settings.downstream_audience
        self._cache = cache or DownstreamTokenCache()

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            cached = await self._ensure(token)
        except HostedAuthError:
            return None
        except OpenAPIError:
            logger.warning("Hosted token introspection or exchange failed")
            return None
        return AccessToken(
            token="",
            client_id=cached.client_id,
            scopes=list(cached.scopes),
            expires_at=int(cached.expires_at),
            resource=cached.resource or self._resource,
            subject=cached.subject,
        )

    async def outbound_token(self, user_token: str) -> str:
        cached = await self._ensure(user_token)
        if not cached.access_token:
            raise HostedAuthError("insufficient scope")
        return cached.access_token

    def _clock_from_payload(self, payload: Mapping[str, object]) -> float:
        exp = payload.get("exp")
        if isinstance(exp, int) and exp > 0:
            return float(exp)
        return time.time() + 60

    async def _ensure(self, user_token: str) -> CachedDownstream:
        cached = self._cache.get(user_token)
        if cached is not None:
            return cached
        async with self._cache.lock:
            cached = self._cache.get(user_token)
            if cached is not None:
                return cached
            return await self._introspect_and_exchange(user_token)

    async def _introspect_and_exchange(self, user_token: str) -> CachedDownstream:
        payload = await self._api.introspect(
            user_token,
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        if not payload.get("active"):
            raise HostedAuthError("inactive token")
        if not audience_matches(payload, self._resource):
            raise HostedAuthError("audience mismatch")
        scopes = _scopes_from(payload)
        # Tokens that are active and bound to this resource but missing a
        # required scope are still returned so the HTTP layer can send 403
        # insufficient_scope. They are not exchanged.
        if any(scope not in scopes for scope in HOSTED_SCOPES):
            subject = payload.get("sub") or payload.get("account_id")
            client_id = payload.get("client_id")
            return CachedDownstream(
                access_token="",
                scopes=scopes,
                expires_at=self._clock_from_payload(payload),
                resource=self._resource,
                subject=str(subject) if subject else None,
                client_id=str(client_id) if client_id else "unknown",
            )
        issued = await self._api.exchange_token(
            user_token,
            client_id=self._client_id,
            client_secret=self._client_secret,
            audience=self._downstream_audience,
        )
        access_token = issued.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise HostedAuthError("exchange returned no token")
        expires_in = issued.get("expires_in")
        if not isinstance(expires_in, int) or expires_in < 1:
            expires_in = 60
        exchanged_scopes = _scopes_from(issued) or scopes
        subject = payload.get("sub") or payload.get("account_id")
        client_id = payload.get("client_id")
        return self._cache.put(
            user_token,
            access_token=access_token,
            expires_in=expires_in,
            scopes=exchanged_scopes,
            resource=self._resource,
            subject=str(subject) if subject else None,
            client_id=str(client_id) if client_id else "unknown",
        )
