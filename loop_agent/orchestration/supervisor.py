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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import ToolRegistry
from loop_agent.providers.chat import ChatLLM
from loop_agent.storage.session_store import SessionStore
from loop_agent.tools import build_registry

from loop_agent.orchestration.dag import topological_layers, validate_dag
from loop_agent.orchestration.filtered_skills import FilteredSkillsLoader
from loop_agent.orchestration.specs import (
    StepInstance,
    StepTemplate,
    WorkerSpec,
    WorkflowStep,
)

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

_DEFAULT_TEMPLATES: List[StepTemplate] = [
    StepTemplate(
        id="research",
        worker="research",
        task_template=_DEFAULT_WORKFLOW[0].task_template,
    ),
    StepTemplate(
        id="writer",
        worker="writer",
        task_template=_DEFAULT_WORKFLOW[1].task_template,
    ),
]

_DEFAULT_INSTANCES: List[StepInstance] = [
    StepInstance(id="research", step="research"),
    StepInstance(id="writer", step="writer", depends_on=["research"]),
]


class Supervisor:
    """Run an N-step workflow of typed workers.

    Constructor arguments default to the historical ``research -> writer``
    pipeline. Both ``workers`` and ``workflow`` may be customized; the
    two must match by name (``WorkflowStep.worker`` references
    ``WorkerSpec.name``).

    DAG mode accepts ``templates`` and ``instances`` instead of ``workflow``.
    The DAG is executed in topological layers, with independent instances
    within a layer running in parallel via ``ThreadPoolExecutor``.
    """

    def __init__(
        self,
        llm: Optional[ChatLLM] = None,
        session_store: Optional[SessionStore] = None,
        workers: Optional[List[WorkerSpec]] = None,
        templates: Optional[List[StepTemplate]] = None,
        instances: Optional[List[StepInstance]] = None,
        workflow: Optional[List[WorkflowStep]] = None,
        max_parallel: int = 4,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        if workers is not None and len(workers) == 0:
            raise ValueError("Supervisor.workers must contain at least one WorkerSpec")
        if workflow is not None and len(workflow) == 0:
            raise ValueError("Supervisor.workflow must contain at least one WorkflowStep")
        if max_parallel < 1:
            raise ValueError("Supervisor.max_parallel must be >= 1")

        self._workflow_from_dag = False
        if workflow is not None:
            if templates is not None or instances is not None:
                raise ValueError(
                    "Cannot specify both workflow and templates/instances"
                )
            templates, instances = self._normalize_workflow(workflow)
            self.workflow: List[WorkflowStep] = list(workflow)
        else:
            if templates is None and instances is None:
                templates = list(_DEFAULT_TEMPLATES)
                instances = list(_DEFAULT_INSTANCES)
                self.workflow = list(_DEFAULT_WORKFLOW)
            elif templates is None or instances is None:
                raise ValueError(
                    "Supervisor templates and instances must be provided together"
                )
            else:
                self._workflow_from_dag = True

        self._workers_specs: List[WorkerSpec] = (
            list(workers) if workers is not None else list(_DEFAULT_WORKERS)
        )
        self.llm: ChatLLM = llm or ChatLLM()
        self.session_store: Optional[SessionStore] = session_store
        self._event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = (
            event_callback
        )
        self._max_parallel: int = max_parallel

        # Eager validation so misconfigurations fail at construction time.
        self._validate_and_build(templates, instances)

    # -- helpers --------------------------------------------------------------

    def _normalize_workflow(
        self, workflow: List[WorkflowStep]
    ) -> tuple[List[StepTemplate], List[StepInstance]]:
        templates: List[StepTemplate] = []
        instances: List[StepInstance] = []
        for i, step in enumerate(workflow):
            template_id = f"_step_{i}"
            templates.append(
                StepTemplate(
                    id=template_id,
                    worker=step.worker,
                    task_template=step.task_template,
                )
            )
            deps = [f"_step_{i - 1}_inst"] if i > 0 else []
            instances.append(
                StepInstance(
                    id=f"{template_id}_inst",
                    step=template_id,
                    depends_on=deps,
                )
            )
        return templates, instances

    def _synthesize_workflow(
        self, templates: Dict[str, StepTemplate], instances: List[StepInstance]
    ) -> List[WorkflowStep]:
        """Derive a linear WorkflowStep list from a DAG for backward-compat readers."""
        steps: List[WorkflowStep] = []
        for layer in self._layers:
            for inst in layer:
                template = templates[inst.step]
                steps.append(WorkflowStep(template.worker, template.task_template))
        return steps

    def _validate_and_build(
        self, templates: List[StepTemplate], instances: List[StepInstance]
    ) -> None:
        names = [w.name for w in self._workers_specs]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Duplicate WorkerSpec.name detected; names must be unique: {names}"
            )
        names_set = set(names)

        template_ids = [t.id for t in templates]
        if len(template_ids) != len(set(template_ids)):
            raise ValueError(
                f"Duplicate StepTemplate.id detected; ids must be unique: {template_ids}"
            )
        template_by_id = {t.id: t for t in templates}

        validate_dag(instances)
        instance_by_id = {inst.id: inst for inst in instances}

        for inst in instances:
            if inst.step not in template_by_id:
                raise ValueError(
                    f"StepInstance(id={inst.id!r}) references unknown step {inst.step!r}; "
                    f"known steps: {sorted(template_by_id)}"
                )
            worker = template_by_id[inst.step].worker
            if worker not in names_set:
                raise ValueError(
                    f"StepTemplate(id={inst.step!r}) references unknown worker {worker!r}; "
                    f"known workers: {sorted(names_set)}"
                )

        self._templates: Dict[str, StepTemplate] = template_by_id
        self._instances: List[StepInstance] = list(instances)
        self._instances_by_id: Dict[str, StepInstance] = instance_by_id
        self._layers: List[List[StepInstance]] = topological_layers(instances)
        if self._workflow_from_dag:
            self.workflow = self._synthesize_workflow(self._templates, self._instances)
        self.worker_loops: Dict[str, AgentLoop] = self._build_workers()

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
        input); the aggregate status becomes ``partial``. To short-circuit,
        inspect the step status in your own caller before invoking subsequent
        steps.

        Returns:
            ``{status, content, run_id, run_dir, session_id}`` - same shape as
            ``POST /chat``. ``status`` is ``success`` when every step
            succeeded; ``partial`` when at least one step returned a
            non-success status. ``run_id`` and ``run_dir`` are intentionally
            empty at this aggregate level - per-worker runs each have their
            own, accessible via ``GET /sessions/{session_id}``.
        """
        outputs: Dict[str, str] = {}
        aggregate_status = "success"
        spec_by_name = {w.name: w for w in self._workers_specs}

        for layer_idx, layer in enumerate(self._layers):
            if self._workflow_from_dag:
                self._emit(
                    "workflow_layer_start",
                    {"layer": layer_idx, "size": len(layer)},
                )

            with ThreadPoolExecutor(max_workers=self._max_parallel) as executor:
                futures = {
                    executor.submit(
                        self._run_instance,
                        inst,
                        task,
                        outputs,
                        session_id,
                        spec_by_name,
                    ): inst
                    for inst in layer
                }
                for future in as_completed(futures):
                    inst = futures[future]
                    result = future.result()
                    outputs[inst.id] = result.get("content") or ""
                    if result.get("status") != "success":
                        aggregate_status = "partial"
                        self._emit(
                            "supervisor_step_warning",
                            {
                                "instance_id": inst.id,
                                "step": inst.step,
                                "status": result.get("status"),
                            },
                        )

            if self._workflow_from_dag:
                self._emit("workflow_layer_end", {"layer": layer_idx})

        final_id = self._instances[-1].id if self._instances else None
        return {
            "status": aggregate_status,
            "content": outputs.get(final_id, ""),
            "run_id": "",
            "run_dir": "",
            "session_id": session_id,
        }

    def _run_instance(
        self,
        instance: StepInstance,
        task: str,
        outputs: Dict[str, str],
        session_id: str,
        spec_by_name: Dict[str, WorkerSpec],
    ) -> Dict[str, Any]:
        template = self._templates[instance.step]
        task_text = self._render(template, instance, task, outputs)

        self._emit(
            "workflow_step_start",
            {
                "instance_id": instance.id,
                "step": instance.step,
                "worker": template.worker,
                "task_preview": task_text[:200],
            },
        )

        worker = self.worker_loops[template.worker]
        spec = spec_by_name[template.worker]
        result = worker.run(
            user_message=task_text,
            session_id=session_id,
            system_prompt=spec.system_prompt,
        )

        self._emit(
            "workflow_step_end",
            {
                "instance_id": instance.id,
                "step": instance.step,
                "worker": template.worker,
                "status": result.get("status"),
                "content_preview": (result.get("content") or "")[:200],
            },
        )
        return result

    def _render(
        self,
        template: StepTemplate,
        instance: StepInstance,
        task: str,
        outputs: Dict[str, str],
    ) -> str:
        ctx: Dict[str, str] = {"task": task, "prev_output": ""}
        ctx.update(instance.user_vars)
        for dep_id in instance.depends_on:
            dep_output = outputs.get(dep_id, f"[upstream failed: {dep_id}]")
            ctx[dep_id] = dep_output
            dep_inst = self._instances_by_id.get(dep_id)
            if dep_inst is not None:
                ctx[dep_inst.step] = dep_output
        if len(instance.depends_on) == 1:
            ctx["prev_output"] = outputs[instance.depends_on[0]]
        try:
            return template.task_template.format(**ctx)
        except KeyError as exc:
            raise SupervisorConfigError(
                f"StepTemplate(id={template.id!r}, worker={template.worker!r}) has "
                f"unknown placeholder {{{exc.args[0]!r}}}; supported placeholders "
                f"are {{task}}, {{prev_output}}, dependency ids, and user_vars. "
                f"Template: {template.task_template[:200]!r}"
            ) from exc

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
