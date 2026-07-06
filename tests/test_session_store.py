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