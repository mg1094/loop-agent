import pytest
from fastapi.testclient import TestClient

from loop_agent.api.app import create_app


def test_preflight_request_returns_200_with_cors_headers():
    client = TestClient(create_app())
    resp = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in resp.headers["access-control-allow-methods"]
    assert "content-type" in resp.headers["access-control-allow-headers"].lower()


def test_cross_origin_post_gets_allow_origin_header(monkeypatch):
    monkeypatch.setattr(
        "loop_agent.api.routes._run_agent",
        lambda prompt, session_id="": {
            "status": "success",
            "content": "ok",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
        },
    )
    client = TestClient(create_app())
    resp = client.post(
        "/chat",
        json={"prompt": "hi"},
        headers={"Origin": "http://127.0.0.1:3000"},
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_unknown_origin_is_not_allowed(monkeypatch):
    client = TestClient(create_app())
    resp = client.options(
        "/chat",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # FastAPI CORS returns 400 when origin is not allowed
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers


def test_custom_origin_via_env(monkeypatch):
    monkeypatch.setenv("LOOP_AGENT_CORS_ORIGINS", "https://app.example.com")
    # create_app is module-level; reimport to pick up new env
    from loop_agent.api import app as app_mod

    app_mod.app = app_mod.create_app()
    client = TestClient(app_mod.app)
    resp = client.options(
        "/chat",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "https://app.example.com"


def test_stream_endpoint_exposes_sse_headers_for_cross_origin():
    from loop_agent.api import sse as sse_mod

    async def tiny_gen(prompt, session_id=""):
        yield sse_mod.format_sse_event(
            "final",
            1,
            "2026-07-07T00:00:00Z",
            "rid",
            {"status": "success", "content": "x", "run_id": "rid", "run_dir": "/tmp", "session_id": session_id},
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("loop_agent.api.routes.stream_chat_events", tiny_gen)

    client = TestClient(create_app())
    resp = client.post(
        "/chat/stream",
        json={"prompt": "hi"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    monkeypatch.undo()
