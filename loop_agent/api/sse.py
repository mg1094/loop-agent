from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional

from loop_agent.agent.loop import AgentLoop
from loop_agent.cli.commands import _build_streaming_components

logger = logging.getLogger(__name__)


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


# Module-level queue kept only as a default fallback when neither the
# streaming entry point nor its caller supply one. ``stream_chat_events``
# creates a per-request queue, which is the path used in production.
event_queue: "queue.Queue" = queue.Queue()


def _run_agent_streaming(
    prompt: str,
    session_id: str = "",
    run_id: Optional[str] = None,
    event_queue: Optional["queue.Queue"] = None,
) -> Dict[str, Any]:
    """Run an AgentLoop and forward events onto ``event_queue``.

    Each call uses its own queue by default — no module-level shared state.
    The ``stream_chat_events`` side creates a per-request queue so concurrent
    clients don't see each other's events and the drain loop can't busy-spin
    re-queuing foreign events back into the same FIFO.

    Args:
        prompt: User prompt.
        session_id: Optional session ID for cross-turn context.
        run_id: Optional caller-supplied run id; one is generated if absent.
        event_queue: Optional queue that receives ``(run_id, event_type, data)``
            tuples. When omitted, an isolated per-call queue is created and
            events are dropped on the floor. Tests that want to inspect
            streamed events should pass their own queue.
    """
    registry, llm, memory, store = _build_streaming_components()
    if run_id is None:
        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
            + uuid.uuid4().hex[:6]
        )
    if event_queue is None:
        # No consumer attached: create an isolated queue but never read it,
        # so callbacks can fire without blocking the worker thread.
        event_queue = queue.Queue()

    def _callback(event_type: str, data: Dict[str, Any]) -> None:
        event_queue.put((run_id, event_type, data))

    loop = AgentLoop(
        registry,
        llm,
        memory,
        event_callback=_callback,
        session_store=store,
    )
    try:
        result = loop.run(prompt, session_id=session_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("streaming runner failed")
        result = {
            "status": "error",
            "content": str(exc),
            "run_id": run_id,
            "run_dir": "",
        }
    # Override AgentLoop's internal run_id with ours so consumers can match events
    result = dict(result)
    result["run_id"] = run_id
    # Push a sentinel so the async generator knows the run is finished
    event_queue.put((run_id, "__done__", result))
    return result


def stream_chat_events(prompt: str, session_id: str = "") -> AsyncIterator[str]:
    """Async generator yielding SSE-formatted event lines for a single run.

    Each call creates its own queue and worker thread; concurrent clients no
    longer contend on a shared event FIFO.
    """

    async def _drain_queue_until_done(
        my_run_id: str, my_queue: "queue.Queue"
    ) -> AsyncIterator[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        while True:
            # Pull from the synchronous queue without blocking the event loop.
            rid, event_type, payload = await loop.run_in_executor(
                None, my_queue.get
            )
            # With per-request queues the rid guard is defensive only.
            if rid != my_run_id:
                logger.warning(
                    "discarding foreign event rid=%s type=%s", rid, event_type
                )
                continue
            if event_type == "__done__":
                return
            yield {"type": event_type, "data": payload}

    async def _run() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        # Start the worker thread. We generate run_id here so we know it before
        # the first event is queued and can correlate by rid.
        my_run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
            + uuid.uuid4().hex[:6]
        )
        # Per-request queue — the worker thread only writes here, and the
        # drain loop only reads here. No global FIFO to re-queue against.
        my_queue: "queue.Queue" = queue.Queue()
        thread_result: Dict[str, Any] = {}

        def worker() -> None:
            try:
                thread_result["result"] = _run_agent_streaming(
                    prompt,
                    session_id=session_id,
                    run_id=my_run_id,
                    event_queue=my_queue,
                )
            except Exception as exc:  # noqa: BLE001
                thread_result["error"] = exc

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        seq = 0

        # 1) run_start
        seq += 1
        yield format_sse_event(
            event_type="run_start",
            seq=seq,
            ts=_now_iso(),
            run_id=my_run_id,
            data={"prompt": prompt, "session_id": session_id},
        )

        # 2) forward forwarded events until __done__ for our run_id
        async for ev in _drain_queue_until_done(my_run_id, my_queue):
            seq += 1
            yield format_sse_event(
                event_type=ev["type"],
                seq=seq,
                ts=_now_iso(),
                run_id=my_run_id,
                data=ev["data"],
            )

        # 3) Wait for the worker thread to fully exit
        await loop.run_in_executor(None, t.join)

        # 4) Emit final or error
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
