from __future__ import annotations

import logging

from deepege_connector.redact import RedactingFilter, install_leak_filter, redact


def test_redact_strips_keys_and_signed_urls() -> None:
    text = (
        "Authorization: Bearer sk-test-alice "
        "play_url=https://media.deepege.com/play/job?v=1&exp=9 "
        "atok_alice dtok_alice client_secret=test-mcp-secret"
    )
    redacted = redact(text)
    assert "sk-test-alice" not in redacted
    assert "atok_alice" not in redacted
    assert "dtok_alice" not in redacted
    assert "test-mcp-secret" not in redacted
    assert "v=1&exp=9" not in redacted
    assert "[REDACTED]" in redacted
    bare = redact("see https://media.deepege.com/play/job?v=1&exp=9 later")
    assert "[REDACTED_URL]" in bare
    assert "v=1&exp=9" not in bare


def test_filter_redacts_log_records(caplog: logging.LogCaptureFixture) -> None:
    install_leak_filter()
    logger = logging.getLogger("deepege_connector.test_redact")
    with caplog.at_level(logging.INFO, logger="deepege_connector.test_redact"):
        logger.addFilter(RedactingFilter())
        logger.info("token=%s url=%s", "sk-test-alice", "https://cdn.example/p?sig=abc")
    output = caplog.text
    assert "sk-test-alice" not in output
    assert "sig=abc" not in output
