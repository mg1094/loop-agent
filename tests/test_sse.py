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
    """_run_agent_streaming pushes tool_result events onto the supplied queue."""
    from loop_agent.api.sse import _run_agent_streaming

    def fake_loop_run(self, user_message, history=None, session_id=""):
        # Simulate the loop calling event_callback once with tool_result
        self._emit("tool_result", {"name": "echo", "result": "hi"})
        return {"status": "success", "content": "hi", "run_id": "fake-rid", "run_dir": "/tmp/x"}

    # Patch AgentLoop.run so we don't need a real LLM
    monkeypatch.setattr("loop_agent.api.sse.AgentLoop.run", fake_loop_run)

    # Stub collaborators — we never call AgentLoop.run for real.
    monkeypatch.setattr(
        "loop_agent.api.sse._build_streaming_components",
        lambda: (None, None, None, None),
    )

    import queue as _q
    my_queue = _q.Queue()
    result = _run_agent_streaming("hello", session_id="", event_queue=my_queue)
    assert result["status"] == "success"

    drained = []
    while not my_queue.empty():
        drained.append(my_queue.get_nowait())
    types = [t for (_rid, t, _data) in drained if _rid == result["run_id"]]
    assert "tool_result" in types


def test_streaming_runner_emits_iteration_start(monkeypatch):
    """AgentLoop iteration_start events are forwarded through the streaming runner."""
    from loop_agent.api.sse import _run_agent_streaming

    def fake_loop_run(self, user_message, history=None, session_id=""):
        self._emit("iteration_start", {"iteration": 1})
        return {"status": "success", "content": "done", "run_id": "fake-rid", "run_dir": "/tmp/x"}

    monkeypatch.setattr("loop_agent.api.sse.AgentLoop.run", fake_loop_run)
    monkeypatch.setattr(
        "loop_agent.api.sse._build_streaming_components",
        lambda: (None, None, None, None),
    )

    import queue as _q
    my_queue = _q.Queue()
    result = _run_agent_streaming("hello", session_id="", event_queue=my_queue)
    assert result["status"] == "success"

    drained = []
    while not my_queue.empty():
        drained.append(my_queue.get_nowait())
    iter_events = [d for (_rid, t, d) in drained if t == "iteration_start" and _rid == result["run_id"]]
    assert iter_events == [{"iteration": 1}]


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
    from loop_agent.api import sse as sse_mod

    def fake_streaming(prompt, session_id="", run_id=None, event_queue=None, **kwargs):
        event_queue.put((run_id, "tool_result", {"name": "echo", "result": "hi"}))
        event_queue.put((run_id, "__done__", {"status": "success", "content": "hi", "run_id": run_id, "run_dir": "/tmp"}))
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
    from loop_agent.api import sse as sse_mod

    def fake_streaming(prompt, session_id="", run_id=None, event_queue=None, **kwargs):
        event_queue.put((run_id, "__done__", {"status": "success", "content": "x", "run_id": run_id, "run_dir": "/tmp"}))
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
    from loop_agent.api import sse as sse_mod

    def fake_streaming(prompt, session_id="", run_id=None, event_queue=None, **kwargs):
        event_queue.put((run_id, "__done__", {"status": "error", "content": "boom", "run_id": run_id, "run_dir": ""}))
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


# ---------------------------------------------------------------------------
# Task 4: POST /chat/stream route
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from loop_agent.api.app import create_app  # noqa: E402


def test_stream_route_returns_event_stream_content_type(monkeypatch):
    # Replace stream_chat_events with a tiny async generator that yields two events.
    from loop_agent.api import sse as sse_mod

    async def tiny_gen(prompt, session_id=""):
        yield sse_mod.format_sse_event(
            event_type="run_start",
            seq=1,
            ts="2026-07-07T00:00:00Z",
            run_id="rid",
            data={"prompt": prompt, "session_id": session_id},
        )
        yield sse_mod.format_sse_event(
            event_type="final",
            seq=2,
            ts="2026-07-07T00:00:01Z",
            run_id="rid",
            data={
                "status": "success",
                "content": "x",
                "run_id": "rid",
                "run_dir": "/tmp",
                "session_id": session_id,
            },
        )

    monkeypatch.setattr("loop_agent.api.routes.stream_chat_events", tiny_gen)
    client = TestClient(create_app())
    resp = client.post("/chat/stream", json={"prompt": "hi"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert "data:" in body
    assert '"type": "run_start"' in body
    assert '"type": "final"' in body


def test_stream_route_propagates_session_id(monkeypatch):
    from loop_agent.api import sse as sse_mod

    captured = []

    async def tiny_gen(prompt, session_id=""):
        captured.append((prompt, session_id))
        yield sse_mod.format_sse_event(
            event_type="final",
            seq=1,
            ts="2026-07-07T00:00:00Z",
            run_id="rid",
            data={
                "status": "success",
                "content": "x",
                "run_id": "rid",
                "run_dir": "/tmp",
                "session_id": session_id,
            },
        )

    monkeypatch.setattr("loop_agent.api.routes.stream_chat_events", tiny_gen)
    client = TestClient(create_app())
    resp = client.post(
        "/chat/stream", json={"prompt": "hi", "session_id": "sess-stream"}
    )
    assert resp.status_code == 200
    assert captured == [("hi", "sess-stream")]
    assert '"session_id": "sess-stream"' in resp.text


def test_stream_blank_prompt_returns_400(monkeypatch):
    called = []
    from loop_agent.api import sse as sse_mod

    async def gen(prompt, session_id=""):
        called.append(prompt)
        yield sse_mod.format_sse_event(
            "run_start",
            1,
            "2026-07-07T00:00:00Z",
            "rid",
            {"prompt": prompt, "session_id": session_id},
        )

    monkeypatch.setattr("loop_agent.api.routes.stream_chat_events", gen)
    client = TestClient(create_app())
    resp = client.post("/chat/stream", json={"prompt": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "prompt must not be blank"
    assert called == []  # generator NOT invoked for blank prompt


def test_stream_missing_prompt_returns_422():
    client = TestClient(create_app())
    resp = client.post("/chat/stream", json={})
    assert resp.status_code == 422


def test_stream_oversized_session_id_returns_422():
    client = TestClient(create_app())
    resp = client.post(
        "/chat/stream", json={"prompt": "hi", "session_id": "x" * 257}
    )
    assert resp.status_code == 422
def test_concurrent_streaming_clients_dont_cross_talk(monkeypatch):
    """Two parallel stream() calls must not see each other's events.

    Regression guard for the shared-queue bug: previously the drain loop
    busy-spun while re-queuing foreign events back into the same FIFO, and
    one client could observe another client's tool_result.
    """
    from loop_agent.api import sse as sse_mod

    inboxes: dict[str, list] = {"a": [], "b": []}

    def fake_streaming(prompt, session_id="", run_id=None, event_queue=None, **kwargs):
        tag = prompt  # use prompt as a tag so we can identify the caller
        inbox = inboxes[tag]
        inbox.append(("run_id", run_id))
        event_queue.put((run_id, "tool_result", {"name": "echo", "result": tag}))
        event_queue.put(
            (run_id, "__done__", {"status": "success", "content": tag, "run_id": run_id, "run_dir": "/tmp"})
        )
        return {"status": "success", "content": tag, "run_id": run_id, "run_dir": "/tmp"}

    monkeypatch.setattr("loop_agent.api.sse._run_agent_streaming", fake_streaming)

    async def collect(prompt):
        out = []
        async for chunk in sse_mod.stream_chat_events(prompt, session_id=""):
            for line in chunk.split("\n"):
                if line.startswith("data:"):
                    out.append(json.loads(line[len("data:"):].strip()))
        return out

    async def run_both():
        return await asyncio.gather(collect("a"), collect("b"))

    a_events, b_events = asyncio.run(run_both())

    def tool_results_for(events, tag):
        return [e for e in events if e.get("type") == "tool_result" and e.get("result") == tag]

    assert len(tool_results_for(a_events, "a")) == 1
    assert len(tool_results_for(b_events, "b")) == 1
    # No cross-talk: a's stream never sees a tool_result whose payload belongs to b.
    assert tool_results_for(a_events, "b") == []
    assert tool_results_for(b_events, "a") == []

