# Phase 2.3 — Streaming SSE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /chat/stream` returning `text/event-stream` so clients see per-iteration agent progress.

**Architecture:** New `loop_agent/api/sse.py` builds a fresh `AgentLoop` with `event_callback` wired to an `asyncio.Queue`, runs it in a worker thread (existing sync API), and the FastAPI handler streams queue items as SSE events. `POST /chat` and `/sessions/{id}` are untouched. Reuses `SessionStore` from Phase 2.2 and `event_callback` from Phase 1.

**Tech Stack:** FastAPI `StreamingResponse`, stdlib `queue.Queue` (sync, since `AgentLoop.run` is sync and runs in a worker thread), `json` for envelope serialization, `datetime` for ts. No new dependencies.

## Global Constraints

- Python 3.11+, FastAPI already in `pyproject.toml`. No new packages.
- Spec: `docs/superpowers/specs/2026-07-07-loop-agent-phase2-streaming-sse-design.md`. Event envelope, types, ordering, and status mirroring `/chat` are binding.
- Test runner: `.venv/Scripts/python.exe -m pytest tests/test_sse.py -v` (Windows). Use `.venv/bin/python` on POSIX.
- Tests use `fastapi.testclient.TestClient`. No real LLM calls; monkeypatch the streaming runner.
- Final test count must reach **64 passing** (current 57 + 7 new SSE tests).
- Run `git status` before committing — `.env`, `.sessions/`, `.venv/` must not be staged.

## File Structure

| File | Purpose |
|------|---------|
| `loop_agent/api/sse.py` (NEW) | `format_sse_event`, `_run_agent_streaming` (sync thread runner with event_callback → queue), `stream_chat_events` (async generator yielding SSE lines) |
| `loop_agent/api/routes.py` (MODIFY) | New `POST /chat/stream` route returning `StreamingResponse` |
| `loop_agent/api/schemas.py` (MODIFY) | Add `StreamChatRequest` (alias-like of `ChatRequest`) |
| `tests/test_sse.py` (NEW) | 7 tests covering event sequence, validation, errors, session echo |
| `README.md` (MODIFY) | New Streaming section, curl example, test count 64 |

---

### Task 1: SSE envelope formatter + small unit tests

**Files:**
- Create: `loop_agent/api/sse.py`
- Test: `tests/test_sse.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `format_sse_event(event_type: str, seq: int, ts: str, run_id: str, data: dict) -> str` — returns a single SSE chunk (one or more `data:` lines + trailing blank line). Uses `data: <json>\n\n` form per the SSE spec.

**Notes:**
- `seq` and `ts` are caller-supplied; this helper does not manage them.
- `data` is the type-specific payload (e.g. `{"prompt": "...", "session_id": "..."}`). The envelope fields (`type`, `seq`, `ts`, `run_id`) are added by the helper on top of `data` — but the spec says they're at the **top level** of the JSON object, not nested. Read the spec section "Event types" again — yes: envelope fields are top-level keys. Implementation must put them at top level: `{"type": ..., "seq": ..., "ts": ..., "run_id": ..., ...data}`.

- [ ] **Step 1: Write failing tests in `tests/test_sse.py`**

```python
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
```

Also add at top of file: `import json`.

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sse.py::test_format_sse_event_includes_envelope_and_blank_line -v`
Expected: ImportError or AttributeError because `loop_agent.api.sse` does not exist.

- [ ] **Step 3: Implement `loop_agent/api/sse.py` (first cut)**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_sse_event(
    event_type: str,
    seq: int,
    ts: str,
    run_id: str,
    data: Dict[str, Any],
) -> str:
    payload = {
        "type": event_type,
        "seq": seq,
        "ts": ts,
        "run_id": run_id,
        **data,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sse.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/api/sse.py tests/test_sse.py
git commit -m "feat(api): add SSE event envelope formatter"
```

---

### Task 2: Sync streaming runner — `AgentLoop` events → thread-safe queue

**Files:**
- Modify: `loop_agent/api/sse.py`
- Test: `tests/test_sse.py`

**Interfaces:**
- Produces:
  - `_run_agent_streaming(prompt: str, session_id: str) -> Dict[str, Any]` — same return shape as `_run_agent` (Phase 2.2 contract: `{"status", "content", "run_id", "run_dir"}`), plus pushes agent events into a module-level `queue.Queue` keyed by `run_id`. Returns the final result dict to the worker thread.
  - Module-level `event_queue: queue.Queue = queue.Queue()` — single queue, items are `(run_id, event_type, data)` tuples.
  - Module-level `register_run(run_id)` — pops events for this run from the queue, used by the async generator.

**Critical design notes:**

- `AgentLoop._emit` already exists from Phase 1. The streaming runner instantiates its own `AgentLoop` (NOT calling `_run_agent` from `cli.commands`) so it can pass `event_callback`.
- The runner builds its own `SkillsLoader`, `ToolRegistry`, `ChatLLM`, `WorkspaceMemory`, `SessionStore` (same composition as `cli.commands._run_agent`). To avoid duplicating that bootstrap, **refactor by importing and reusing** `cli.commands._build_loop()` — but `_build_loop` does not currently exist. **Instead**, extract a tiny helper `_build_streaming_loop()` in `cli/commands.py` that returns `(registry, llm, memory, session_store)` and is called by both `_run_agent` and `_run_agent_streaming`. This is a 5-line refactor.

- [ ] **Step 1: Add a tiny `_build_streaming_components()` helper to `loop_agent/cli/commands.py`**

Replace the body of `_run_agent` so the bootstrap is shared. New version:

```python
def _build_streaming_components() -> tuple:
    """Build the agent's collaborators. Shared by CLI + streaming SSE path."""
    _load_env()
    skills_loader = SkillsLoader()
    registry = build_registry(skills_loader=skills_loader)
    llm = ChatLLM()
    memory = WorkspaceMemory()
    store = SessionStore()
    return registry, llm, memory, store


def _run_agent(user_message: str, session_id: str = "") -> Dict[str, Any]:
    registry, llm, memory, store = _build_streaming_components()
    loop = AgentLoop(registry, llm, memory, session_store=store)
    return loop.run(user_message, session_id=session_id)
```

(Verify by running `.venv/Scripts/python.exe -m pytest tests/test_cli.py -v` — must stay green.)

- [ ] **Step 2: Write failing tests**

Append to `tests/test_sse.py`:

```python
import queue
import threading
import time
from loop_agent.api import sse as sse_mod
from loop_agent.api.sse import _run_agent_streaming


def test_streaming_runner_emits_tool_result_events(monkeypatch):
    """_run_agent_streaming pushes tool_result events into the shared queue."""
    captured = []

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
    assert out["run_id"] == "rid"
```

- [ ] **Step 3: Run tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sse.py::test_streaming_runner_emits_tool_result_events -v`
Expected: ImportError or AttributeError (function doesn't exist yet).

- [ ] **Step 4: Implement `_run_agent_streaming`**

Append to `loop_agent/api/sse.py`:

```python
import queue
import threading
from typing import Any, Dict, Optional, Tuple

from loop_agent.agent.loop import AgentLoop
from loop_agent.cli.commands import _build_streaming_components


# Single shared queue for all streaming runs. Items are (run_id, event_type, data).
event_queue: "queue.Queue[Tuple[str, str, Dict[str, Any]]]" = queue.Queue()


def _run_agent_streaming(prompt: str, session_id: str = "") -> Dict[str, Any]:
    """Run an AgentLoop and forward its events into event_queue.

    Returns the same dict shape as cli.commands._run_agent.
    """
    registry, llm, memory, store = _build_streaming_components()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    # We let AgentLoop assign its own run_id inside .run(); use a placeholder here
    # so consumers can correlate. We patch _emit to stamp run_id.

    def _callback(event_type: str, data: Dict[str, Any]) -> None:
        event_queue.put((run_id, event_type, data))

    loop = AgentLoop(registry, llm, memory, event_callback=_callback, session_store=store)
    result = loop.run(prompt, session_id=session_id)
    # Override AgentLoop's internal run_id with ours so consumers can match events
    result = dict(result)
    result["run_id"] = run_id
    # Push a sentinel so the async generator knows the run is finished
    event_queue.put((run_id, "__done__", result))
    return result
```

Also add at top of file: `import uuid`.

- [ ] **Step 5: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sse.py -v`
Expected: 4 passed (2 from Task 1 + 2 from Task 2).

- [ ] **Step 6: Re-run full suite to confirm no regressions in CLI**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 61 passed (existing 57 + 4 new SSE tests).

- [ ] **Step 7: Commit**

```bash
git add loop_agent/api/sse.py loop_agent/cli/commands.py tests/test_sse.py
git commit -m "feat(api): streaming runner forwards agent events to queue"
```

---

### Task 3: Async generator that yields SSE events

**Files:**
- Modify: `loop_agent/api/sse.py`
- Test: `tests/test_sse.py`

**Interfaces:**
- Produces:
  - `stream_chat_events(prompt: str, session_id: str = "") -> AsyncIterator[str]` — async generator. Spawns a worker thread running `_run_agent_streaming(prompt, session_id)`, yields SSE event lines until the worker's `__done__` sentinel arrives, then yields the `final` event and exits.

**Critical design notes:**

- The generator runs the streaming runner in a `threading.Thread(daemon=True)` because `AgentLoop.run` is synchronous and we must not block the event loop.
- It does **not** call `_run_agent_streaming` directly via `await` — that would block the FastAPI event loop. Threading is required.
- The generator is responsible for assigning `seq` (1, 2, 3, ...) and `ts` for each event.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_sse.py`:

```python
import asyncio
from loop_agent.api.sse import stream_chat_events


def _drain_async(gen):
    """Helper: collect all strings from an async generator."""
    return asyncio.get_event_loop().run_until_complete(_collect(gen))


async def _collect(gen):
    out = []
    async for item in gen:
        out.append(item)
    return out


def test_stream_emits_run_start_then_final_then_done(monkeypatch):
    # Patch _run_agent_streaming to push one tool_result and then done,
    # bypassing the real AgentLoop.
    import queue as _q

    monkeypatch.setattr("loop_agent.api.sse.event_queue", _q.Queue())

    def fake_streaming(prompt, session_id=""):
        sse_mod.event_queue.put(("rid1", "tool_result", {"name": "echo", "result": "hi"}))
        sse_mod.event_queue.put(("rid1", "__done__", {"status": "success", "content": "hi", "run_id": "rid1", "run_dir": "/tmp"}))
        return {"status": "success", "content": "hi", "run_id": "rid1", "run_dir": "/tmp"}

    monkeypatch.setattr("loop_agent.api.sse._run_agent_streaming", fake_streaming)

    events_text = _drain_async(stream_chat_events("hello", session_id=""))

    # Parse events
    parsed = []
    for chunk in events_text:
        for line in chunk.split("\n"):
            if line.startswith("data:"):
                import json as _json
                parsed.append(_json.loads(line[len("data:"):].strip()))

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
    monkeypatch.setattr("loop_agent.api.sse.event_queue", _q.Queue())

    def fake_streaming(prompt, session_id=""):
        sse_mod.event_queue.put(("rid2", "__done__", {"status": "success", "content": "x", "run_id": "rid2", "run_dir": "/tmp"}))
        return {"status": "success", "content": "x", "run_id": "rid2", "run_dir": "/tmp"}

    monkeypatch.setattr("loop_agent.api.sse._run_agent_streaming", fake_streaming)

    events_text = _drain_async(stream_chat_events("hi", session_id="sess-42"))
    parsed = []
    import json as _json
    for chunk in events_text:
        for line in chunk.split("\n"):
            if line.startswith("data:"):
                parsed.append(_json.loads(line[len("data:"):].strip()))

    final = parsed[-1]
    assert final["type"] == "final"
    assert final["session_id"] == "sess-42"
    # run_start should also echo session_id
    assert parsed[0]["type"] == "run_start"
    assert parsed[0]["session_id"] == "sess-42"
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sse.py::test_stream_emits_run_start_then_final_then_done -v`
Expected: ImportError (`stream_chat_events` does not exist).

- [ ] **Step 3: Implement `stream_chat_events`**

Append to `loop_agent/api/sse.py`:

```python
import asyncio
from typing import AsyncIterator


def stream_chat_events(prompt: str, session_id: str = "") -> AsyncIterator[str]:
    """Async generator yielding SSE-formatted event lines for a single run.

    Spawns a worker thread running _run_agent_streaming and forwards its
    queue events to the async side. Yields the run_start event first, then
    forwarded tool events, then a final event, then exits.
    """
    loop = asyncio.get_event_loop()

    async def _drain_queue_until_done(my_run_id: str) -> AsyncIterator[Dict[str, Any]]:
        while True:
            # pull from the synchronous queue without blocking the event loop
            rid, event_type, payload = await loop.run_in_executor(None, event_queue.get)
            if rid != my_run_id:
                # not ours — re-queue and keep waiting
                event_queue.put((rid, event_type, payload))
                continue
            if event_type == "__done__":
                return payload  # type: ignore[return-value]
            yield {"type": event_type, "data": payload}

    async def _run() -> AsyncIterator[str]:
        # Start the worker thread. We need to know run_id BEFORE the first
        # event is queued, so generate it here and pass via a closure.
        my_run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        thread_result: Dict[str, Any] = {}

        def worker() -> None:
            try:
                thread_result["result"] = _run_agent_streaming(prompt, session_id=session_id)
            except Exception as exc:  # noqa: BLE001
                thread_result["error"] = exc

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        seq = 0
        ts = _now_iso()
        seq += 1
        yield format_sse_event(
            event_type="run_start",
            seq=seq,
            ts=ts,
            run_id=my_run_id,
            data={"prompt": prompt, "session_id": session_id},
        )

        # Forward events from the queue until __done__
        async for ev in _drain_queue_until_done(my_run_id):
            seq += 1
            yield format_sse_event(
                event_type=ev["type"],
                seq=seq,
                ts=_now_iso(),
                run_id=my_run_id,
                data=ev["data"],
            )

        # Wait for worker to fully exit
        await loop.run_in_executor(None, t.join)

        # Emit final or error
        seq += 1
        if "error" in thread_result:
            yield format_sse_event(
                event_type="error",
                seq=seq,
                ts=_now_iso(),
                run_id=my_run_id,
                data={
                    "message": str(thread_result["error"]),
                    "status": "error",
                    "session_id": session_id,
                },
            )
            return

        result = thread_result["result"]
        yield format_sse_event(
            event_type="final",
            seq=seq,
            ts=_now_iso(),
            run_id=my_run_id,
            data={
                "status": result["status"],
                "content": result["content"],
                "run_id": result["run_id"],
                "run_dir": result["run_dir"],
                "session_id": session_id,
            },
        )

    return _run()
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sse.py -v`
Expected: 6 passed (4 prior + 2 new).

- [ ] **Step 5: Commit**

```bash
git add loop_agent/api/sse.py tests/test_sse.py
git commit -m "feat(api): async SSE event generator"
```

---

### Task 4: `POST /chat/stream` route + validation tests

**Files:**
- Modify: `loop_agent/api/routes.py`
- Modify: `loop_agent/api/schemas.py` (optional — could just reuse `ChatRequest`)
- Test: `tests/test_sse.py` (extend) OR `tests/test_api.py` (extend)

**Decision:** reuse `ChatRequest` (no new schema). The route signature is identical except for the response type.

**Interfaces:**
- Produces:
  - `POST /chat/stream` — accepts `ChatRequest`, returns `StreamingResponse(stream_chat_events(...), media_type="text/event-stream")`.

- [ ] **Step 1: Write failing tests in `tests/test_sse.py`**

Append:

```python
from fastapi.testclient import TestClient
from loop_agent.api.app import create_app


def test_stream_route_returns_event_stream_content_type(monkeypatch):
    # Replace stream_chat_events with a tiny async generator that yields one event.
    import asyncio as _asyncio
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
            data={"status": "success", "content": "x", "run_id": "rid", "run_dir": "/tmp", "session_id": session_id},
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


def test_stream_blank_prompt_returns_400(monkeypatch):
    called = []
    from loop_agent.api import sse as sse_mod

    async def gen(prompt, session_id=""):
        called.append(prompt)
        yield sse_mod.format_sse_event("run_start", 1, "2026-07-07T00:00:00Z", "rid", {"prompt": prompt, "session_id": session_id})

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
    resp = client.post("/chat/stream", json={"prompt": "hi", "session_id": "x" * 257})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sse.py::test_stream_route_returns_event_stream_content_type -v`
Expected: 404 (route does not exist yet).

- [ ] **Step 3: Add the route in `loop_agent/api/routes.py`**

Append at end of file:

```python
from fastapi.responses import StreamingResponse

from loop_agent.api.sse import stream_chat_events


@router.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be blank")
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream_chat_events(req.prompt, session_id=req.session_id),
        media_type="text/event-stream",
        headers=headers,
    )
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sse.py -v`
Expected: 10 passed.

- [ ] **Step 5: Run full suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 67 passed (57 prior + 10 new SSE). Wait — task brief said 64. Recount:
- Task 1: 2 tests
- Task 2: 2 tests (4 cumulative)
- Task 3: 2 tests (6 cumulative)
- Task 4: 4 tests (10 cumulative)

Actual is **67 = 57 + 10**. Update task brief from 64 to 67. **NOTE TO REVIEWER**: I (the planner) miscounted in the original spec doc's "Testing" section — actual count is 10 new tests, not 7. Update README in Task 6.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/api/routes.py tests/test_sse.py
git commit -m "feat(api): POST /chat/stream SSE endpoint"
```

---

### Task 5: README — Streaming section + test count + roadmap flip

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the test-count badge and paragraph**

In `README.md`:
- Line 6 badge: change `tests-22%20passed` → `tests-67%20passed`.
- Bottom paragraph (currently says "55 tests cover …"): change "55 tests" → "67 tests". Add "and streaming SSE" to the listed coverage.

- [ ] **Step 2: Add Streaming section after `## Sessions`**

Insert after the `## Sessions` section, before `## Test`:

```markdown
## Streaming

`/chat/stream` returns `text/event-stream` so clients see per-iteration progress instead of waiting for the full run.

```bash
curl -N -X POST http://localhost:8000/chat/stream \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Use the echo tool to say hello", "session_id": "demo"}'
```

Events emitted (one `data: <json>\n\n` line each, envelope fields at top level):

| `type`            | When                                |
|-------------------|-------------------------------------|
| `run_start`       | First event                         |
| `tool_result`     | Each tool call finishes             |
| `final`           | Run finished — mirrors `/chat`      |
| `error`           | Only on unrecoverable exception     |

`final` always carries `status`, `content`, `run_id`, `run_dir`, and `session_id` — same shape as `POST /chat`'s JSON response. Session persistence behavior matches `/chat`: pass `session_id`, prior messages are loaded and the new turn is saved.
```

- [ ] **Step 3: Flip the Streaming roadmap item**

In the `## Roadmap` section, change `- [ ] Streaming responses with proper SSE` → `- [x] Streaming responses with proper SSE`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: streaming SSE section + test count 67"
```

---

### Task 6: Final verification + whole-branch review

- [ ] **Step 1: Run full test suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 67 passed.

- [ ] **Step 2: Quick smoke test against running server**

Boot uvicorn in background:
```bash
.venv/Scripts/python.exe -m uvicorn loop_agent.api.app:app --port 8765
```

Then in another terminal:
```bash
curl -N -X POST http://localhost:8765/chat/stream \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Use the echo tool to say hello"}'
```

Expect: SSE event stream starting with `data: {"type": "run_start", ...}` and ending with `data: {"type": "final", ...}`. Stop the uvicorn process.

- [ ] **Step 3: Dispatch whole-branch review**

Use the `superpowers:requesting-code-review` skill with `BASE_SHA=412c582` (spec commit) and `HEAD_SHA=<this branch's HEAD>`. The reviewer will check:
- SSE envelope format matches spec
- Async generator correctness (no missed events, no infinite loops)
- Threading model safety
- Test coverage (10 new tests cover all spec requirements)
- Backward compatibility of `/chat`

Apply review fixes if any, then push.

- [ ] **Step 4: Push to GitHub**

```bash
git push origin main
```

Expected: `https://github.com/mg1094/loop-agent.git` updated, commit count grows by 6 from Phase 2.2.