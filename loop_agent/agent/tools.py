from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)



class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}
    repeatable: bool = True
    is_readonly: bool = True
    skip_auto_register: bool = False

    def _emit_progress(self, phase: str) -> None:
        """Surface a long-running-tool phase to the active progress sink.

        ``ToolRegistry._bind_on_progress`` attaches a callback named
        ``_on_progress`` to each registered tool. Tools that want to
        advertise progress call ``self._emit_progress("...")``; if the
        tool is constructed standalone (without going through the
        registry) or no sink is wired, ``_emit_progress`` is a safe no-op.
        Never raise out of this method — tool progress must never break
        the underlying tool call.
        """
        cb = getattr(self, "_on_progress", None)
        if cb is None:
            return
        try:
            cb(phase)
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    def check_available(cls) -> bool:
        return True

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a JSON string."""

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}, "required": []},
            },
        }


class ToolRegistry:
    def __init__(
        self,
        on_progress: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self._on_progress = on_progress

    def set_on_progress(
        self, on_progress: Optional[Callable[[str, str], None]]
    ) -> None:
        """Attach a progress sink after registry construction.

        Tools already registered receive the new callback the next time
        ``_bind_on_progress`` runs. Useful for ``AgentLoop`` which only
        knows about its own event callback at run time.
        """
        self._on_progress = on_progress
        self._bind_on_progress()

    def _bind_on_progress(self) -> None:
        for tool in self._tools.values():
            name = tool.name
            if self._on_progress is None:
                tool._on_progress = lambda _phase: None
            else:
                cb = self._on_progress
                # Capture ``name`` via default arg so the closure binds
                # to the right tool even if the registry is reused.
                tool._on_progress = (lambda phase, _n=name: cb(_n, phase))

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        self._bind_on_progress()

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_definitions(self) -> List[Dict[str, Any]]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute(
        self,
        name: str,
        params: Dict[str, Any],
        on_error: Optional[Callable[[str, str], None]] = None,
    ) -> str:
        tool = self._tools.get(name)
        if not tool:
            error = f"Tool '{name}' not found"
            if on_error:
                on_error("ToolNotFoundError", error)
            return json.dumps({"status": "error", "error": error}, ensure_ascii=False)
        try:
            return tool.execute(**params)
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            if on_error:
                on_error(type(exc).__name__, str(exc))
            return json.dumps({"status": "error", "tool": name, "error": str(exc)}, ensure_ascii=False)

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
