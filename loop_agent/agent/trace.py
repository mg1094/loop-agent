from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class TraceWriter:
    def __init__(self, trace_dir: Path) -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / "trace.jsonl"

    def write(self, entry: Dict[str, Any]) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.warning("Trace write failed: %s", exc)

    def write_text_entry(
        self,
        entry: Dict[str, Any],
        field: str,
        value: str,
        offload_kind: str = "",
    ) -> None:
        entry[field] = value
        self.write(entry)
