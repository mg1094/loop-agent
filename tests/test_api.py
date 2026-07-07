import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from loop_agent.api.app import create_app
from loop_agent import __version__
from loop_agent.storage.session_store import SessionStore


def test_health():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_list_skills(monkeypatch):
    monkeypatch.setattr(
        "loop_agent.api.routes.list_skills",
        lambda: "### writing\n  - writing: test",
    )
    client = TestClient(create_app())
    resp = client.get("/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert "writing" in body["descriptions"]


def test_list_tools(monkeypatch):
    monkeypatch.setattr(
        "loop_agent.api.routes.list_tool_names",
        lambda: ["echo", "load_skill", "read_file", "write_file"],
    )
    client = TestClient(create_app())
    resp = client.get("/tools")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tools"] == ["echo", "load_skill", "read_file", "write_file"]


def test_chat_success(monkeypatch):
    def fake_run(prompt: str, session_id: str = "") -> dict:
        return {
            "status": "success",
            "content": f"Echo: {prompt}",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
        }

    monkeypatch.setattr("loop_agent.api.routes._run_agent", fake_run)
    client = TestClient(create_app())
    resp = client.post("/chat", json={"prompt": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["content"] == "Echo: hello"
    assert body["run_id"] == "r1"
    assert body["run_dir"] == "/tmp/r1"
    assert body["session_id"] == ""


def test_chat_with_session_id(monkeypatch):
    captured = []

    def fake_run(prompt: str, session_id: str = "") -> dict:
        captured.append((prompt, session_id))
        return {"status": "success", "content": "ok", "run_id": "r1", "run_dir": "/tmp/r1"}

    monkeypatch.setattr("loop_agent.api.routes._run_agent", fake_run)
    client = TestClient(create_app())
    resp = client.post("/chat", json={"prompt": "hi", "session_id": "sess-1"})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "sess-1"
    assert captured == [("hi", "sess-1")]


def test_chat_session_id_too_long_returns_422():
    client = TestClient(create_app())
    resp = client.post("/chat", json={"prompt": "hi", "session_id": "x" * 257})
    assert resp.status_code == 422


def test_chat_blank_prompt_returns_400(monkeypatch):
    called = []
    monkeypatch.setattr(
        "loop_agent.api.routes._run_agent",
        lambda p: called.append(p) or {"status": "success", "content": "", "run_id": "r", "run_dir": "/tmp/r"},
    )
    client = TestClient(create_app())
    resp = client.post("/chat", json={"prompt": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "prompt must not be blank"
    assert called == []  # run_agent NOT called for blank prompt


def test_chat_missing_prompt_returns_422():
    client = TestClient(create_app())
    resp = client.post("/chat", json={})
    assert resp.status_code == 422


def test_get_session_returns_messages(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    store = SessionStore(db)
    store.save_turn("sess-x", [{"role": "user", "content": "remember me"}])
    client = TestClient(create_app())
    resp = client.get("/sessions/sess-x")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "sess-x"
    assert body["messages"][0]["content"] == "remember me"


def test_get_unknown_session_returns_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH",
        tmp_path / "sessions.db",
    )
    client = TestClient(create_app())
    resp = client.get("/sessions/never-existed")
    assert resp.status_code == 200
    assert resp.json() == {"session_id": "never-existed", "messages": []}


def test_delete_session_removes_messages(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    store = SessionStore(db)
    store.save_turn("sess-del", [{"role": "user", "content": "x"}])
    client = TestClient(create_app())
    resp = client.delete("/sessions/sess-del")
    assert resp.status_code == 200
    assert resp.json() == {"session_id": "sess-del", "deleted": True}
    # second delete is False
    resp2 = client.delete("/sessions/sess-del")
    assert resp2.json()["deleted"] is False
