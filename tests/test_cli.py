import json
from pathlib import Path

from loop_agent.cli.commands import (
    delete_session,
    list_sessions,
    list_tools,
    replay_trace,
    run_command,
    run_tool,
    search_sessions,
)


def test_run_command_with_mock_loop(monkeypatch):
    calls = []

    def fake_run(user_message, history=None, session_id=""):
        calls.append((user_message, session_id))
        return {
            "status": "success",
            "content": f"Echo: {user_message}",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
        }

    monkeypatch.setattr("loop_agent.cli.commands._run_agent", fake_run)
    result = run_command("hello")
    assert result["content"] == "Echo: hello"
    assert calls == [("hello", "")]

def test_run_command_with_session_id(monkeypatch):
    captured = []

    def fake_run(user_message, history=None, session_id=""):
        captured.append((user_message, session_id))
        return {"status": "success", "content": "ok", "run_id": "r", "run_dir": "/tmp"}

    monkeypatch.setattr("loop_agent.cli.commands._run_agent", fake_run)
    result = run_command("hi", session_id="sess-1")
    assert result["content"] == "ok"
    assert captured == [("hi", "sess-1")]


def test_list_tools_returns_names(monkeypatch):
    monkeypatch.setattr(
        "loop_agent.cli.commands.build_registry",
        lambda *a, **kw: _FakeRegistry(["echo", "read_file"]),
    )
    out = list_tools()
    assert out == "echo\nread_file"


def test_run_tool_executes_named_tool(monkeypatch):
    monkeypatch.setattr(
        "loop_agent.cli.commands.build_registry",
        lambda *a, **kw: _FakeRegistry({"echo": lambda **kw: json.dumps(kw)}),
    )
    result = run_tool("echo", {"message": "hi"})
    assert json.loads(result) == {"message": "hi"}


def test_run_tool_missing_tool_raises_keyerror(monkeypatch):
    monkeypatch.setattr(
        "loop_agent.cli.commands.build_registry",
        lambda *a, **kw: _FakeRegistry({}),
    )
    try:
        run_tool("missing", {})
    except KeyError as exc:
        assert "missing" in str(exc)


def test_list_sessions_returns_rows(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    from loop_agent.storage.session_store import SessionStore

    monkeypatch.setattr("loop_agent.cli.commands.SessionStore", lambda: SessionStore(db))
    store = SessionStore(db)
    store.save_turn("s1", [{"role": "user", "content": "hello"}])

    rows = list_sessions()
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s1"
    assert rows[0]["message_count"] == 1


def test_search_sessions_returns_hits(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    from loop_agent.storage.session_store import SessionStore

    monkeypatch.setattr("loop_agent.cli.commands.SessionStore", lambda: SessionStore(db))
    store = SessionStore(db)
    store.save_turn("s1", [{"role": "user", "content": "serverless on AWS"}])
    store.save_turn("s2", [{"role": "user", "content": "python only"}])

    hits = search_sessions("serverless")
    ids = [h["session_id"] for h in hits]
    assert ids == ["s1"]


def test_delete_session_removes(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    from loop_agent.storage.session_store import SessionStore

    monkeypatch.setattr("loop_agent.cli.commands.SessionStore", lambda: SessionStore(db))
    store = SessionStore(db)
    store.save_turn("del-me", [{"role": "user", "content": "x"}])

    assert delete_session("del-me") is True
    assert delete_session("del-me") is False


def test_replay_trace_renders_entries(capsys, tmp_path: Path):
    run_dir = tmp_path / "runs" / "20260709_120000_abcdef"
    run_dir.mkdir(parents=True)
    trace = run_dir / "trace.jsonl"
    trace.write_text(
        json.dumps({"type": "start", "prompt": "hi"}) + "\n"
        + json.dumps(
            {
                "type": "tool_result",
                "iter": 1,
                "name": "echo",
                "content": '{"result": "hi"}',
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "tool_error",
                "iter": 1,
                "name": "echo",
                "exception_type": "RuntimeError",
                "error": "boom",
            }
        )
        + "\n"
        + json.dumps({"type": "final", "status": "success", "content": "done"})
        + "\n",
        encoding="utf-8",
    )
    replay_trace("abcdef", runs_dir=tmp_path / "runs")
    out = capsys.readouterr().out
    assert "Run started: hi" in out
    assert "Tool 'echo'" in out
    assert "FAILED (RuntimeError): boom" in out
    assert "Final (success): done" in out


def test_replay_trace_ambiguous_suffix_raises(tmp_path: Path):
    root = tmp_path / "runs"
    (root / "20260709_120000_abcdef").mkdir(parents=True)
    (root / "20260710_120000_abcdef").mkdir(parents=True)
    try:
        replay_trace("abcdef", runs_dir=root)
    except ValueError as exc:
        assert "Ambiguous" in str(exc)


class _FakeRegistry:
    """Stub registry for CLI tests that only need tool names or execution."""

    def __init__(self, data):
        self._data = data

    @property
    def tool_names(self):
        if isinstance(self._data, list):
            return self._data
        return sorted(self._data.keys())

    def __contains__(self, name: str) -> bool:
        return name in (self._data if isinstance(self._data, dict) else self._data)

    def execute(self, name: str, params: dict) -> str:
        if isinstance(self._data, dict):
            return self._data[name](**params)
        raise KeyError(name)
