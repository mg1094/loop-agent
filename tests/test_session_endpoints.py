from pathlib import Path

from fastapi.testclient import TestClient

from loop_agent.api.app import create_app
from loop_agent.storage.session_store import SessionStore


def test_list_sessions_empty(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    client = TestClient(create_app())
    resp = client.get("/sessions")
    assert resp.status_code == 200
    assert resp.json() == {"sessions": []}


def test_list_sessions_returns_meta(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    store = SessionStore(db)
    store.save_turn("alpha", [{"role": "user", "content": "hello"}])
    store.save_turn("alpha", [{"role": "assistant", "content": "world"}])
    store.save_turn("beta", [{"role": "user", "content": "goodbye"}])

    client = TestClient(create_app())
    resp = client.get("/sessions")
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    ids = [s["session_id"] for s in sessions]
    assert "alpha" in ids
    assert "beta" in ids
    by_id = {s["session_id"]: s for s in sessions}
    assert by_id["alpha"]["message_count"] == 2
    assert by_id["beta"]["message_count"] == 1
    assert by_id["alpha"]["created_at"]
    assert by_id["alpha"]["updated_at"]


def test_search_returns_matching_sessions(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    store = SessionStore(db)
    store.save_turn("alpha", [{"role": "user", "content": "we need serverless on AWS"}])
    store.save_turn(
        "beta",
        [
            {"role": "user", "content": "tell me about serverless architecture"},
            {"role": "assistant", "content": "serverless shines for low-traffic APIs"},
        ],
    )
    store.save_turn("gamma", [{"role": "user", "content": "no matches here"}])

    client = TestClient(create_app())
    resp = client.get("/sessions/search", params={"q": "serverless"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "serverless"
    ids = [h["session_id"] for h in body["hits"]]
    assert ids == ["beta", "alpha"]  # beta has 2 hits, alpha has 1
    by_id = {h["session_id"]: h for h in body["hits"]}
    assert by_id["beta"]["match_count"] == 2
    assert by_id["alpha"]["match_count"] == 1
    assert "gamma" not in ids


def test_search_blank_query_returns_empty(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    store = SessionStore(db)
    store.save_turn("alpha", [{"role": "user", "content": "anything"}])

    client = TestClient(create_app())
    resp = client.get("/sessions/search", params={"q": "   "})
    assert resp.status_code == 200
    assert resp.json()["hits"] == []


def test_search_caps_limit(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    store = SessionStore(db)
    for i in range(5):
        store.save_turn(f"sess-{i}", [{"role": "user", "content": f"foo {i}"}])

    client = TestClient(create_app())
    resp = client.get("/sessions/search", params={"q": "foo", "limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()["hits"]) == 2


def test_search_limit_out_of_range_falls_back_to_default(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    store = SessionStore(db)
    store.save_turn("alpha", [{"role": "user", "content": "serverless"}])

    client = TestClient(create_app())
    resp = client.get("/sessions/search", params={"q": "serverless", "limit": 500})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["hits"]) == 1
