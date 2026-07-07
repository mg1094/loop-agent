import asyncio
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


# ---------------------------------------------------------------------------
# Task 3: async SSE event generator
# ---------------------------------------------------------------------------
from loop_agent.api.sse import stream_chat_events  # noqa: E402


def _drain_async(gen):
    """Helper: collect all strings from an async generator."""
    return asyncio.run(_collect(gen))


async def _collect(gen):
    out = []
    async for item in gen:
        out.append(item)
    return out


def test_stream_emits_run_start_then_final_then_done(monkeypatch):
    # Patch _run_agent_streaming to push one tool_result and then done,
    # bypassing the real AgentLoop. Use the run_id passed by the caller so
    # events correlate with stream_chat_events' my_run_id.
    import queue as _q

    from loop_agent.api import sse as sse_mod

    monkeypatch.setattr("loop_agent.api.sse.event_queue", _q.Queue())

    def fake_streaming(prompt, session_id="", run_id="rid1", **kwargs):
        sse_mod.event_queue.put((run_id, "tool_result", {"name": "echo", "result": "hi"}))
        sse_mod.event_queue.put((run_id, "__done__", {"status": "success", "content": "hi", "run_id": run_id, "run_dir": "/tmp"}))
        return {"status": "success", "content": "hi", "run_id": run_id, "run_dir": "/tmp"}

    monkeypatch.setattr("loop_agent.api.sse._run_agent_streaming", fake_streaming)

    events_text = _drain_async(stream_chat_events("hello", session_id=""))

    # Parse events
    parsed = []
    for chunk in events_text:
        for line in chunk.split("\n"):
            if line.startswith("data:"):
                parsed.append(json.loads(line[len("data:"):].strip()))

    types = [e["type"] for e in parsed]
    assert types[0] == "run_start"
    assert "tool_result" in types
    assert types[-1] == "final"
    # final has session_id echoed
    final = parsed[-1]
    assert final["status"] == "success"
    assert final["session_id"] == ""  # no session_id passed


def test_stream_echoes_session_id_in_final(monkeypatch):
    import queue as _q

    from loop_agent.api import sse as sse_mod

    monkeypatch.setattr("loop_agent.api.sse.event_queue", _q.Queue())

    def fake_streaming(prompt, session_id="", run_id="rid2", **kwargs):
        sse_mod.event_queue.put((run_id, "__done__", {"status": "success", "content": "x", "run_id": run_id, "run_dir": "/tmp"}))
        return {"status": "success", "content": "x", "run_id": run_id, "run_dir": "/tmp"}

    monkeypatch.setattr("loop_agent.api.sse._run_agent_streaming", fake_streaming)

    events_text = _drain_async(stream_chat_events("hi", session_id="sess-42"))
    parsed = []
    for chunk in events_text:
        for line in chunk.split("\n"):
            if line.startswith("data:"):
                parsed.append(json.loads(line[len("data:"):].strip()))

    final = parsed[-1]
    assert final["type"] == "final"
    assert final["session_id"] == "sess-42"
    # run_start should also echo session_id
    assert parsed[0]["type"] == "run_start"
    assert parsed[0]["session_id"] == "sess-42"


def test_stream_emits_error_event_when_worker_raises(monkeypatch):
    import queue as _q

    from loop_agent.api import sse as sse_mod

    monkeypatch.setattr("loop_agent.api.sse.event_queue", _q.Queue())

    def fake_streaming(prompt, session_id="", run_id="rid3", **kwargs):
        sse_mod.event_queue.put((run_id, "__done__", {"status": "error", "content": "boom", "run_id": run_id, "run_dir": ""}))
        raise RuntimeError("boom")

    monkeypatch.setattr("loop_agent.api.sse._run_agent_streaming", fake_streaming)

    events_text = _drain_async(stream_chat_events("hi", session_id="err-sess"))
    parsed = []
    for chunk in events_text:
        for line in chunk.split("\n"):
            if line.startswith("data:"):
                parsed.append(json.loads(line[len("data:"):].strip()))

    assert parsed[0]["type"] == "run_start"
    assert parsed[-1]["type"] == "error"
    assert parsed[-1]["status"] == "error"
    assert parsed[-1]["message"] == "boom"
    assert parsed[-1]["session_id"] == "err-sess"
