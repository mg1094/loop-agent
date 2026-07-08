from __future__ import annotations

import json
import warnings
from typing import Any, Callable

from loop_agent.agent.tools import BaseTool


class DelegateTool(BaseTool):
    name = "delegate"
    description = (
        "Assign a subtask to a specialized worker. "
        "Workers: research (web search), writer (produce final report)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Clear subtask description for the worker.",
            },
            "to": {
                "type": "string",
                "enum": ["research", "writer"],
                "description": "Name of the worker to delegate to.",
            },
        },
        "required": ["task", "to"],
    }
    repeatable = True
    is_readonly = True
    skip_auto_register = True

    def __init__(self, dispatcher: Callable[[str, str], str]) -> None:
        warnings.warn(
            "DelegateTool is deprecated; configure workflows via Supervisor(workers, workflow) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._dispatcher = dispatcher

    def execute(self, *, task: str, to: str, **kwargs: Any) -> str:
        output = self._dispatcher(task, to)
        return json.dumps({"worker": to, "output": output}, ensure_ascii=False)


class FinalizeTool(BaseTool):
    name = "finalize"
    description = "Return the final report to the user and end the session."
    parameters = {
        "type": "object",
        "properties": {
            "report": {
                "type": "string",
                "description": "Final report content to return to the user.",
            },
        },
        "required": ["report"],
    }
    repeatable = False
    is_readonly = True
    skip_auto_register = True

    def __init__(self, callback: Callable[[str], None]) -> None:
        warnings.warn(
            "FinalizeTool is deprecated; the Supervisor captures the final report implicitly after the last workflow step.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._callback = callback

    def execute(self, *, report: str, **kwargs: Any) -> str:
        self._callback(report)
        return json.dumps({"status": "finalized"}, ensure_ascii=False)
