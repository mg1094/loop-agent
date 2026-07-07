from __future__ import annotations

from typing import Any, Dict, List, Optional

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import ToolRegistry
from loop_agent.providers.chat import ChatLLM
from loop_agent.storage.session_store import SessionStore
from loop_agent.tools import build_registry

from loop_agent.orchestration.tools import DelegateTool, FinalizeTool


_COORDINATOR_PROMPT = """You are a supervisor coordinating two workers to produce a report.

Workers:
- research: searches the web and returns a structured summary
- writer: writes the final report based on the research summary

Rules:
1. First call delegate(task="...", to="research") to gather information.
2. Then call delegate(task="...", to="writer") with the research summary.
3. Finally call finalize(report="...") with the writer's report.
4. Do not answer the user directly.

The user asked: {task}"""


class Supervisor:
    WORKER_TOOLS: Dict[str, List[str]] = {
        "research": ["web_search"],
        "writer": ["read_file", "write_file", "echo"],
    }

    def __init__(
        self,
        llm: Optional[ChatLLM] = None,
        session_store: Optional[SessionStore] = None,
    ) -> None:
        self.llm = llm or ChatLLM()
        self.session_store = session_store
        self.workers = self._build_workers()

    def _build_worker_registry(self, tool_names: List[str]) -> ToolRegistry:
        full_registry = build_registry()
        filtered = ToolRegistry()
        for name in tool_names:
            tool = full_registry.get(name)
            if tool:
                filtered.register(tool)
        return filtered

    def _build_workers(self) -> Dict[str, AgentLoop]:
        return {
            name: AgentLoop(
                self._build_worker_registry(tool_names),
                self.llm,
                memory=WorkspaceMemory(),
                session_store=self.session_store,
            )
            for name, tool_names in self.WORKER_TOOLS.items()
        }

    def _build_coordinator(
        self, session_id: str, final_report: List[str]
    ) -> AgentLoop:
        def dispatcher(task: str, worker_name: str) -> str:
            worker = self.workers.get(worker_name)
            if not worker:
                return f"Error: unknown worker '{worker_name}'"
            result = worker.run(task, session_id=session_id)
            return result.get("content", "")

        def capture_final(report: str) -> None:
            final_report.append(report)

        registry = ToolRegistry()
        registry.register(DelegateTool(dispatcher))
        registry.register(FinalizeTool(capture_final))

        return AgentLoop(
            registry,
            self.llm,
            memory=WorkspaceMemory(),
            session_store=self.session_store,
        )

    def run(self, task: str, session_id: str = "") -> Dict[str, Any]:
        final_report: List[str] = []
        coordinator = self._build_coordinator(session_id, final_report)
        system_prompt = _COORDINATOR_PROMPT.format(task=task)
        result = coordinator.run(
            task,
            session_id=session_id,
            system_prompt=system_prompt,
        )
        result = dict(result)
        if final_report:
            result["content"] = final_report[-1]
        result["session_id"] = session_id
        return result