import json
from pathlib import Path

from loop_agent.agent.tools import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a text file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
        },
        "required": ["path"],
    }

    def execute(self, *, path: str) -> str:
        try:
            content = Path(path).read_text(encoding="utf-8")
            return json.dumps({"status": "ok", "content": content}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
