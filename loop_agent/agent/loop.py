from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loop_agent.agent.context import ContextBuilder
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import ToolRegistry
from loop_agent.agent.trace import TraceWriter
from loop_agent.providers.chat import ChatLLM

logger = logging.getLogger(__name__)
RUNS_DIR = Path("runs")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "30"))


def _estimate_tokens(messages: list) -> int:
    return len(json.dumps(messages, default=str, ensure_ascii=False)) // 4


class AgentLoop:
    def __init__(
        self,
        registry: ToolRegistry,
        llm: ChatLLM,
        memory: Optional[WorkspaceMemory] = None,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        self.registry = registry
        self.llm = llm
        self.memory = memory or WorkspaceMemory()
        self._event_callback = event_callback
        self.max_iterations = max_iterations
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if self._event_callback:
            self._event_callback(event_type, data)

    def run(
        self,
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        session_id: str = "",
    ) -> Dict[str, Any]:
        self._cancel_event.clear()

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self.memory.run_dir = str(run_dir)

        context = ContextBuilder(self.registry, self.memory)
        messages = context.build_messages(user_message, history)

        trace = TraceWriter(run_dir)
        trace.write({"type": "start", "run_id": run_id, "prompt": user_message})
        trace.write({"type": "message", "role": "user", "content": user_message})

        iteration = 0
        final_content = ""

        try:
            while iteration < self.max_iterations:
                if self._cancel_event.is_set():
                    trace.write({"type": "cancelled", "iter": iteration + 1})
                    return {"status": "cancelled", "content": "", "run_id": run_id, "run_dir": str(run_dir)}

                iteration += 1
                logger.info("ReAct iteration %d/%d", iteration, self.max_iterations)

                is_last = iteration == self.max_iterations
                tool_defs = None if is_last else self.registry.get_definitions()

                if is_last:
                    trace.write({"type": "forced_text_only", "iter": iteration})

                response = self.llm.stream_chat(
                    messages,
                    tools=tool_defs,
                    should_cancel=self._cancel_event.is_set,
                )

                if not response.has_tool_calls:
                    final_content = response.content or ""
                    if not final_content:
                        trace.write({"type": "empty_model_response", "iter": iteration})
                        return {"status": "empty", "content": "", "run_id": run_id, "run_dir": str(run_dir)}
                    trace.write({"type": "final", "iter": iteration, "content": final_content})
                    return {"status": "success", "content": final_content, "run_id": run_id, "run_dir": str(run_dir)}

                assistant_msg = context.format_assistant_tool_calls(response.tool_calls)
                messages.append(assistant_msg)
                trace.write({"type": "assistant", "iter": iteration, "tool_calls": assistant_msg.get("tool_calls", [])})

                for tc in response.tool_calls:
                    result = self.registry.execute(tc.name, tc.arguments)
                    tool_msg = context.format_tool_result(tc.id, tc.name, result)
                    messages.append(tool_msg)
                    trace.write({"type": "tool_result", "iter": iteration, "name": tc.name, "content": result})
                    self.memory.increment(tc.name)
                    self._emit("tool_result", {"name": tc.name, "result": result})

            return {"status": "max_iterations", "content": final_content, "run_id": run_id, "run_dir": str(run_dir)}

        except Exception as exc:
            logger.exception("AgentLoop failed")
            trace.write({"type": "error", "error": str(exc)})
            return {"status": "error", "content": str(exc), "run_id": run_id, "run_dir": str(run_dir)}
