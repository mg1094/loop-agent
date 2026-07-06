import json
from pathlib import Path

from loop_agent.storage.session_store import SessionStore


def test_save_and_load_round_trip(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
        {"role": "tool", "tool_call_id": "t1", "name": "echo", "content": "ok"},
    ]
    store.save_turn("s1", msgs)
    loaded = store.load_messages("s1")
    assert loaded == msgs


def test_load_unknown_session_returns_empty(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    assert store.load_messages("nonexistent") == []


def test_save_turn_appends(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    store.save_turn("s1", [{"role": "user", "content": "first"}])
    store.save_turn("s1", [{"role": "user", "content": "second"}])
    loaded = store.load_messages("s1")
    assert [m["content"] for m in loaded] == ["first", "second"]


def test_delete_session_removes_messages(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    store.save_turn("s1", [{"role": "user", "content": "hi"}])
    assert store.delete_session("s1") is True
    assert store.load_messages("s1") == []
    # second delete returns False
    assert store.delete_session("s1") is False


def test_list_sessions(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    store.save_turn("a", [{"role": "user", "content": "1"}])
    store.save_turn("b", [{"role": "user", "content": "2"}])
    sessions = store.list_sessions()
    assert "a" in sessions
    assert "b" in sessions


def test_save_turn_skips_system_role(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    store.save_turn("s1", [
        {"role": "system", "content": "should not persist"},
        {"role": "user", "content": "kept"},
    ])
    loaded = store.load_messages("s1")
    assert loaded == [{"role": "user", "content": "kept"}]