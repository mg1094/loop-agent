import json
from pathlib import Path
from typing import List, Optional

from loop_agent.agent.tools import BaseTool
from loop_agent.tools.path_safety import safe_path


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a text file from an allowed directory."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative file path inside an allowed root.",
            },
        },
        "required": ["path"],
    }

    def __init__(self, allowed_roots: Optional[List[Path]] = None) -> None:
        self._allowed_roots = list(allowed_roots) if allowed_roots else None

    def execute(self, *, path: str) -> str:
        self._emit_progress(f"read_file: opening {path}")
        resolved, ok, reason = safe_path(path, self._allowed_roots)
        if not ok or resolved is None:
            self._emit_progress(f"read_file: rejected ({reason})")
            return json.dumps({"status": "error", "error": reason}, ensure_ascii=False)
        try:
            content = resolved.read_text(encoding="utf-8")
            self._emit_progress(f"read_file: read {len(content)} chars")
        except Exception as exc:
            self._emit_progress(f"read_file: error {type(exc).__name__}")
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
        return json.dumps(
            {"status": "ok", "content": content, "path": str(resolved)},
            ensure_ascii=False,
        )
