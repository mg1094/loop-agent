import json
from pathlib import Path

from loop_agent.agent.tools import BaseTool


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a text file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    }
    is_readonly = False

    def execute(self, *, path: str, content: str) -> str:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return json.dumps({"status": "ok", "path": str(p)}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
