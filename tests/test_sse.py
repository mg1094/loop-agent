import json
import re

from loop_agent.api.sse import format_sse_event


def test_format_sse_event_includes_envelope_and_blank_line():
    out = format_sse_event(
        event_type="final",
        seq=1,
        ts="2026-07-07T00:00:00Z",
        run_id="r1",
        data={"status": "success"},
    )
    assert out.endswith("\n\n")
    # Single data: line per spec — one JSON object
    lines = out.split("\n")
    data_lines = [ln for ln in lines if ln.startswith("data:")]
    assert len(data_lines) == 1
    payload = json.loads(data_lines[0][len("data:"):].strip())
    assert payload == {
        "type": "final",
        "seq": 1,
        "ts": "2026-07-07T00:00:00Z",
        "run_id": "r1",
        "status": "success",
    }


def test_format_sse_event_does_not_newline_inside_json():
    # SSE forbids embedded newlines in data: lines; ensure we serialize without them.
    out = format_sse_event(
        event_type="tool_result",
        seq=2,
        ts="2026-07-07T00:00:01Z",
        run_id="r1",
        data={"name": "echo", "output": "line1\nline2"},
    )
    data_lines = [ln for ln in out.split("\n") if ln.startswith("data:")]
    assert len(data_lines) == 1
    payload = json.loads(data_lines[0][len("data:"):].strip())
    assert payload["output"] == "line1\nline2"


def test_streaming_runner_emits_tool_result_events(monkeypatch):
    """_run_agent_streaming pushes tool_result events into the shared queue."""
    from loop_agent.api import sse as sse_mod
    from loop_agent.api.sse import _run_agent_streaming

    def fake_loop_run(self, user_message, history=None, session_id=""):
        # Simulate the loop calling event_callback once with tool_result
        self._emit("tool_result", {"name": "echo", "result": "hi"})
        return {"status": "success", "content": "hi", "run_id": "fake-rid", "run_dir": "/tmp/x"}

    # Patch AgentLoop.run so we don't need a real LLM
    monkeypatch.setattr("loop_agent.api.sse.AgentLoop.run", fake_loop_run)

    # Also stub _build_streaming_components so it returns benign objects —
    # but since fake_loop_run replaces AgentLoop.run, the components only
    # need to satisfy AgentLoop.__init__ (which we don't call because run is patched).
    monkeypatch.setattr(
        "loop_agent.api.sse._build_streaming_components",
        lambda: (None, None, None, None),
    )

    result = _run_agent_streaming("hello", session_id="")
    assert result["status"] == "success"

    # Drain the queue, find our run_id's events
    drained = []
    while not sse_mod.event_queue.empty():
        drained.append(sse_mod.event_queue.get_nowait())
    types = [t for (_rid, t, _data) in drained if _rid == result["run_id"]]
    assert "tool_result" in types


def test_streaming_runner_returns_full_dict(monkeypatch):
    from loop_agent.api.sse import _run_agent_streaming

    monkeypatch.setattr(
        "loop_agent.api.sse.AgentLoop.run",
        lambda self, user_message, history=None, session_id="": {
            "status": "max_iterations",
            "content": "partial",
            "run_id": "rid",
            "run_dir": "/tmp/y",
        },
    )
    monkeypatch.setattr(
        "loop_agent.api.sse._build_streaming_components",
        lambda: (None, None, None, None),
    )
    out = _run_agent_streaming("hi", session_id="")
    assert out["status"] == "max_iterations"
    assert out["content"] == "partial"
    # The streaming runner overrides AgentLoop's run_id with its own generated one,
    # so it should match the format YYYYMMDD_HHMMSS_<6hex>, not "rid".
    assert out["run_id"] != "rid"
    assert re.match(r"^\d{8}_\d{6}_[0-9a-f]{6}$", out["run_id"]), (
        f"Expected streaming-generated run_id format, got {out['run_id']!r}"
    )
    assert out["run_dir"] == "/tmp/y"
