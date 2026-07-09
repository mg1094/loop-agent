from __future__ import annotations

import json
from typing import Any

from loop_agent.agent.tools import BaseTool


class CompactTool(BaseTool):
    name = "compact"
    description = (
        "Compress conversation history to free context space. Call when the "
        "conversation is long or earlier details need to be preserved in a "
        "handoff summary. Optionally specify focus_topic."
    )
    parameters = {
        "type": "object",
        "properties": {
            "focus_topic": {
                "type": "string",
                "description": "Topic to preserve in detail during compression.",
            },
        },
        "required": [],
    }
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        return json.dumps({"status": "ok", "message": "Compression triggered"})
