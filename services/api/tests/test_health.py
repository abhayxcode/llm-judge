from fastapi.testclient import TestClient

from judge_api.config import Settings
from judge_api.main import create_app


def _client() -> TestClient:
    app = create_app(Settings(env="test"))
    return TestClient(app)


def test_health_returns_ok() -> None:
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["env"] == "test"
    assert "version" in body
    assert "time" in body


def test_ready_returns_true() -> None:
    with _client() as client:
        resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"ready": True}


def test_unknown_route_404() -> None:
    with _client() as client:
        resp = client.get("/nope")
    assert resp.status_code == 404
