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
