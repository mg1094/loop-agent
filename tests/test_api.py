from fastapi.testclient import TestClient

from loop_agent.api.app import create_app
from loop_agent import __version__


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
