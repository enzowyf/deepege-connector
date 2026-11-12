from openapi_spec_validator import validate as validate_spec
from openapi_spec_validator.versions.shortcuts import get_spec_version

from tests.helpers import load_spec

REQUIRED_PATHS = {
    "/open/v1/video-requests",
    "/open/v1/video-requests/{job_id}/plan-decisions",
    "/open/v1/video-requests/{job_id}/answers",
    "/open/v1/jobs/{job_id}",
    "/open/v1/jobs/{job_id}/cancel",
    "/open/v1/jobs/{job_id}/result-links",
    "/open/v1/me",
    "/oauth/introspect",
    "/oauth/token",
}


def test_open_v1_is_valid_openapi_31() -> None:
    spec = load_spec()
    version = get_spec_version(spec)
    assert (version.major, version.minor) == ("3", "1")
    validate_spec(spec)


def test_contract_covers_the_nine_endpoints() -> None:
    spec = load_spec()
    assert REQUIRED_PATHS <= set(spec["paths"])


def test_contract_has_no_internal_terms() -> None:
    text = (
        __import__("pathlib")
        .Path(__file__)
        .resolve()
        .parents[1]
        .joinpath("openapi", "open-v1.yaml")
        .read_text(encoding="utf-8")
        .lower()
    )
    forbidden = [
        "skill",
        "prompt word",
        "openai",
        "anthropic",
        "replicate",
        "runway",
        "elevenlabs",
        "gitee",
        "engine_frontend",
        "agent_service",
        "start_plan",
        "quote_expired",
    ]
    hits = [term for term in forbidden if term in text]
    assert hits == []


def test_oauth_paths_document_internal_error() -> None:
    spec = load_spec()
    for path in ("/oauth/introspect", "/oauth/token"):
        assert "500" in spec["paths"][path]["post"]["responses"]


def test_rate_limit_section_covers_oauth_clients() -> None:
    description = load_spec()["info"]["description"]
    assert "/oauth/*" in description
    assert "client_id" in description
