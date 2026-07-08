"""Configurable Supervisor.

Replace the hard-coded research→writer→finalize dance with a data-driven
``Supervisor(workers, workflow)``. Default values preserve today's behavior
exactly, so the CLI ``run-supervised`` and HTTP ``POST /chat/supervised``
paths remain backward compatible.

Public surface lives in this module and is re-exported from
``loop_agent.orchestration``.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import ToolRegistry
from loop_agent.providers.chat import ChatLLM
from loop_agent.storage.session_store import SessionStore
from loop_agent.tools import build_registry

from loop_agent.orchestration.filtered_skills import FilteredSkillsLoader
from loop_agent.orchestration.specs import WorkerSpec, WorkflowStep

logger = logging.getLogger(__name__)


class SupervisorConfigError(Exception):
    """Raised when a workflow step template cannot be rendered.

    Examples include unknown placeholders (anything other than ``{task}`` and
    ``{prev_output}``). Surfaced at run-time, not construction time, so the
    full intent of the misconfigured template is preserved in the error.
    """


_DEFAULT_WORKERS: List[WorkerSpec] = [
    WorkerSpec(
        name="research",
        tools=["web_search"],
        max_iterations=20,
    ),
    WorkerSpec(
        name="writer",
        tools=["read_file", "write_file", "echo"],
        max_iterations=20,
    ),
]

_DEFAULT_WORKFLOW: List[WorkflowStep] = [
    WorkflowStep(
        worker="research",
        task_template=(
            "Search the web for facts about: {task}\n"
            "Return a structured summary (titles, URLs, snippets, "
            "and the dates of the sources)."
        ),
    ),
    WorkflowStep(
        worker="writer",
        task_template=(
            "Write a structured report on: {task}\n\n"
            "Use the following research summary as your source material:\n"
            "---\n{prev_output}\n---\n\n"
            "Produce the report as plain text, around 600 words, "
            "with a short conclusion."
        ),
    ),
]


class Supervisor:
    """Run an N-step workflow of typed workers.

    Constructor arguments default to the historical ``research -> writer``
    pipeline. Both ``workers`` and ``workflow`` may be customized; the
    two must match by name (``WorkflowStep.worker`` references
    ``WorkerSpec.name``).
    """

    def __init__(
        self,
        llm: Optional[ChatLLM] = None,
        session_store: Optional[SessionStore] = None,
        workers: Optional[List[WorkerSpec]] = None,
        workflow: Optional[List[WorkflowStep]] = None,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        if workers is not None and len(workers) == 0:
            raise ValueError("Supervisor.workers must contain at least one WorkerSpec")
        if workflow is not None and len(workflow) == 0:
            raise ValueError("Supervisor.workflow must contain at least one WorkflowStep")

        self._workers_specs: List[WorkerSpec] = list(workers) if workers is not None else list(_DEFAULT_WORKERS)
        self.workflow: List[WorkflowStep] = list(workflow) if workflow is not None else list(_DEFAULT_WORKFLOW)
        self.llm: ChatLLM = llm or ChatLLM()
        self.session_store: Optional[SessionStore] = session_store
        self._event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = event_callback

        # Eager validation so misconfigurations fail at construction time.
        names = [w.name for w in self._workers_specs]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Duplicate WorkerSpec.name detected; names must be unique: {names}"
            )
        names_set = set(names)
        for step in self.workflow:
            if step.worker not in names_set:
                raise ValueError(
                    f"WorkflowStep references unknown worker {step.worker!r}; "
                    f"known workers: {sorted(names_set)}"
                )

        self.worker_loops: Dict[str, AgentLoop] = self._build_workers()

    # -- helpers --------------------------------------------------------------

    def _build_worker_skills_loader(self, allowed: List[str]) -> SkillsLoader:
        full = SkillsLoader()
        if not allowed:
            return full
        return FilteredSkillsLoader(full, allowed=set(allowed))

    def _build_workers(self) -> Dict[str, AgentLoop]:
        loops: Dict[str, AgentLoop] = {}
        for spec in self._workers_specs:
            skills_loader = self._build_worker_skills_loader(spec.skills)
            # Build a worker-scoped registry so ``LoadSkillTool`` reads from
            # the same ``skills_loader`` that the ContextBuilder does. Without
            # this the tool would fall back to a default ``SkillsLoader()``
            # and bypass the worker's allow-list.
            worker_registry = build_registry(skills_loader=skills_loader)
            filtered = ToolRegistry()
            for tool_name in spec.tools:
                tool = worker_registry.get(tool_name)
                if tool is None:
                    # Silent skip: tools like ``web_search`` are only
                    # registered when their backing API key is present.
                    # Preserve backward-compat for default ``Supervisor()``
                    # on machines that have not opted in.
                    logger.debug(
                        "WorkerSpec(%s) skips tool %s (not available)",
                        spec.name,
                        tool_name,
                    )
                    continue
                filtered.register(tool)
            loops[spec.name] = AgentLoop(
                filtered,
                self.llm,
                memory=WorkspaceMemory(),
                session_store=self.session_store,
                event_callback=self._event_callback,
                skills_loader=skills_loader,
                max_iterations=spec.max_iterations,
            )
        return loops

    # -- public API -----------------------------------------------------------

    def run(self, task: str, session_id: str = "") -> Dict[str, Any]:
        """Execute the workflow and return the final report.

        When a step returns a non-success status, the workflow continues
        with subsequent steps (using the failing step's content as the next
        ``prev_output``); the aggregate status becomes ``partial``. To
        short-circuit, inspect the step status in your own caller before
        invoking subsequent steps.

        Returns:
            ``{status, content, run_id, run_dir, session_id}`` - same shape as
            ``POST /chat``. ``status`` is ``success`` when every step
            succeeded; ``partial`` when at least one step returned a
            non-success status. ``run_id`` and ``run_dir`` are intentionally
            empty at this aggregate level - per-worker runs each have their
            own, accessible via ``GET /sessions/{session_id}``.
        """
        ctx: Dict[str, str] = {"task": task, "prev_output": ""}
        aggregate_status = "success"
        spec_by_name = {w.name: w for w in self._workers_specs}

        for i, step in enumerate(self.workflow):
            try:
                task_text = step.task_template.format(**ctx)
            except KeyError as exc:
                raise SupervisorConfigError(
                    f"WorkflowStep[{i}] (worker={step.worker!r}) has unknown "
                    f"placeholder {{{exc.args[0]!r}}}; only {{task}} and "
                    f"{{prev_output}} are supported. Template: "
                    f"{step.task_template[:200]!r}"
                ) from exc

            self._emit("workflow_step_start", {
                "step": i,
                "worker": step.worker,
                "task_preview": task_text[:200],
            })

            worker = self.worker_loops[step.worker]
            spec = spec_by_name[step.worker]
            result = worker.run(
                user_message=task_text,
                session_id=session_id,
                system_prompt=spec.system_prompt,
            )

            ctx["prev_output"] = result.get("content") or ""
            self._emit("workflow_step_end", {
                "step": i,
                "worker": step.worker,
                "status": result.get("status"),
                "content_preview": ctx["prev_output"][:200],
            })

            if result.get("status") != "success":
                aggregate_status = "partial"
                self._emit("supervisor_step_warning", {
                    "step": i,
                    "worker": step.worker,
                    "status": result.get("status"),
                })

        return {
            "status": aggregate_status,
            "content": ctx["prev_output"],
            "run_id": "",
            "run_dir": "",
            "session_id": session_id,
        }

    # -- event bridge ---------------------------------------------------------

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Forward workflow events through the user-supplied callback.

        ``event_callback`` is threaded down into each worker ``AgentLoop`` at
        construction time, so the same sink sees both per-iteration events
        from inside workers and the supervisor-level
        ``workflow_step_start`` / ``workflow_step_end`` /
        ``supervisor_step_warning`` events emitted here.
        """
        cb = self._event_callback
        if cb is None:
            return
        try:
            cb(event_type, data)
        except Exception:  # noqa: BLE001 - never break the loop on a sink error
            logger.warning("supervisor event sink raised", exc_info=True)
