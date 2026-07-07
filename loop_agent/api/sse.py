from __future__ import annotations

import json
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from loop_agent.agent.loop import AgentLoop
from loop_agent.cli.commands import _build_streaming_components


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


# Single shared queue for all streaming runs. Items are (run_id, event_type, data).
event_queue: "queue.Queue[Tuple[str, str, Dict[str, Any]]]" = queue.Queue()


def _run_agent_streaming(prompt: str, session_id: str = "") -> Dict[str, Any]:
    """Run an AgentLoop and forward its events into event_queue.

    Returns the same dict shape as cli.commands._run_agent, but with the
    streaming-runner-generated ``run_id`` overlaid so consumers can match
    events in ``event_queue`` to the final result.
    """
    registry, llm, memory, store = _build_streaming_components()
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
        + uuid.uuid4().hex[:6]
    )

    def _callback(event_type: str, data: Dict[str, Any]) -> None:
        event_queue.put((run_id, event_type, data))

    loop = AgentLoop(
        registry, llm, memory, event_callback=_callback, session_store=store
    )
    result = loop.run(prompt, session_id=session_id)
    # Override AgentLoop's internal run_id with ours so consumers can match events
    result = dict(result)
    result["run_id"] = run_id
    # Push a sentinel so the async generator knows the run is finished
    event_queue.put((run_id, "__done__", result))
    return result
