"""Log redaction so API keys and signed URLs never appear in log output."""

from __future__ import annotations

import logging
import re
from typing import Any

_BEARER = re.compile(r"(?i)(bearer\s+)\S+")
_KEY_LIKE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9._~-]+|atok_[A-Za-z0-9._~-]+|dtok_[A-Za-z0-9._~-]+|"
    r"client_secret=[^\s&\"']+)"
)
_SENSITIVE_FIELD = re.compile(
    r"(?i)((?:authorization|api[_-]?key|client_secret|idempotency-key"
    r"|play_url|cover_url)\s*[:=]\s*)(\S+)"
)
_SIGNED_URL = re.compile(r"https?://[^\s\"'<>]+?\?[^\s\"'<>]+")

_SENTINEL = "[REDACTED]"
_URL_SENTINEL = "[REDACTED_URL]"


def redact(text: str) -> str:
    """Return ``text`` with credentials and signed URLs stripped."""
    text = _BEARER.sub(rf"\1{_SENTINEL}", text)
    text = _SENSITIVE_FIELD.sub(rf"\1{_SENTINEL}", text)
    text = _KEY_LIKE.sub(_SENTINEL, text)
    return _SIGNED_URL.sub(_URL_SENTINEL, text)


def _redact_arg(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redact_arg(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(_redact_arg(v) for v in value)
    if isinstance(value, list):
        return [_redact_arg(v) for v in value]
    return value


class RedactingFilter(logging.Filter):
    """Logging filter that redacts secrets on the record before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                record.args = _redact_arg(record.args)
            if record.exc_text:
                record.exc_text = redact(record.exc_text)
        except Exception:  # noqa: BLE001 — never break logging
            return True
        return True


def install_leak_filter() -> None:
    """Attach the redacting filter to the root logger and its handlers."""
    filt = RedactingFilter()
    root = logging.getLogger()
    if not any(isinstance(existing, RedactingFilter) for existing in root.filters):
        root.addFilter(filt)
    for handler in root.handlers:
        if not any(isinstance(existing, RedactingFilter) for existing in handler.filters):
            handler.addFilter(filt)
    logger = logging.getLogger("deepege_connector")
    if not any(isinstance(existing, RedactingFilter) for existing in logger.filters):
        logger.addFilter(filt)
