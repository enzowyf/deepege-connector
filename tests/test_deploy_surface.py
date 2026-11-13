from starlette.testclient import TestClient

from deepege_connector.config import Settings
from deepege_connector.server import create_server, transport_security


def _settings(**kw):
    base = dict(
        api_base_url="http://x",
        mcp_host="127.0.0.1",
        mcp_port=0,
        client_id=None,
        client_secret=None,
    )
    base.update(kw)
    return Settings(**base)


def test_healthz_ok():
    app = create_server(_settings()).streamable_http_app()
    with TestClient(app) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_allowed_hosts_admit_proxy_host():
    sec = transport_security(_settings(allowed_hosts=("stage.deepege.com",)))
    assert sec is not None
    assert "stage.deepege.com" in sec.allowed_hosts
    assert "https://stage.deepege.com" in sec.allowed_origins


def test_no_allowed_hosts_keeps_sdk_default():
    assert transport_security(_settings()) is None
