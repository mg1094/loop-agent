# Phase 3 — Configurable Supervisor: Worker Identity + Workflow

> Status: DRAFT (awaiting user approval)
> Date: 2026-07-08
> Project: `D:\code\loop-agent`
> Predecessor: Phase 2.4 Supervisor Multi-Agent (commits `0948f65`, `f7910bd`, `d8a01d4`, `6e1c823`)

## Goal

Replace the hard-coded `research → writer → finalize` orchestration with a
**data-driven `Supervisor`** where:

- each worker has an explicit identity (`WorkerSpec`) — tools, skills, system prompt, iteration cap;
- the workflow itself is a list of steps (`WorkflowStep`) — workers can be invoked any number of times in any order.

Default values keep today's behavior exactly, so the public surface (CLI
`run-supervised`, API `POST /chat/supervised`, the streaming SSE event shape)
is **backward compatible**.

## Background

The Phase 2.4 supervisor ships a working `research → writer → finalize`
pipeline, but the design hard-codes several things:

| # | Hard-coded behavior | Limitation |
|---|---------------------|------------|
| 1 | Coordinator system prompt enforces a fixed 3-step script (`research → writer → finalize`) | Users cannot compose other workflows (summarize→translate, research→research→write, etc.) |
| 2 | Workers share one global `SkillsLoader`, exposing every skill description | A worker cannot be told "load skill X only" — there is no per-worker skill scope |
| 3 | All workers get the default `ContextBuilder` system prompt ("You are a helpful research assistant") | Workers have no role-specific instructions beyond what the dispatcher packs into the user message |
| 4 | Final report captured by an LLM-driven `finalize` tool call | The coordinator can forget or skip `finalize`; failure mode is silent |
| 5 | Workers run serially | No way to fan out (research-a + research-b in parallel) |
| 6 | No built-in skill corpus for supervisor use cases | Out of scope for this phase |

Phase 3 resolves #1, #2, #3, and #4. #5 and #6 remain future work (see
"Out of scope").

## Scope

In scope:

- New dataclass `WorkerSpec` (name, tools, skills, system_prompt, max_iterations) in `loop_agent/orchestration/specs.py`.
- New dataclass `WorkflowStep` (worker, task_template) in the same module.
- New `FilteredSkillsLoader` in `loop_agent/orchestration/filtered_skills.py` — thin wrapper that exposes only an allow-listed subset of skills.
- `Supervisor.__init__(workers, workflow, llm, session_store)` accepts:
  - `workers: Optional[List[WorkerSpec]]` — default is `[research, writer]` matching today's behavior;
  - `workflow: Optional[List[WorkflowStep]]` — default is `[research→writer]`.
- Each worker `AgentLoop` gets its per-worker `system_prompt` (via existing `system_prompt` kwarg) and per-worker `FilteredSkillsLoader` (via new `skills_loader` kwarg on `AgentLoop.__init__`).
- Supervisor becomes **itself** the implicit finalizer: after the last workflow step runs, the captured `prev_output` is the final report. The LLM-driven `finalize` tool is no longer needed.
- New event types `workflow_step_start` and `workflow_step_end` are emitted for SSE / CLI observability.
- New status value `partial` for runs that finished the workflow but encountered a non-success step.
- New exception `SupervisorConfigError` for template-rendering failures.
- Tests covering WorkerSpec, FilteredSkillsLoader, configurable Supervisor, and backward-compat re-verification.

Out of scope (deferred):

- Reflection / quality-loop (`Phase 3+`) — adding an `accept` judge step.
- Parallel workers (`Phase 3+`) — fanning out a step to multiple workers and merging results.
- CLI / API surface for declaring custom workers/workflows (`Phase 3+`).
- Skill corpus expansion (depends on a separate "skill authoring" effort).
- Token-budget accounting per worker.
- LLM streaming for worker outputs (`Phase 4+` if requested).

## Design

### Architecture

```
User
 │
 ▼
Supervisor.run(task, session_id)
 │
 │   ctx = {"task": user_task, "prev_output": ""}
 │   status = "success"
 │
 ▼
for i, step in enumerate(self.workflow):
 │
 │   ► emit("workflow_step_start", {"step": i, "worker": step.worker,
 │                                  "task_preview": task_text[:200]})
 │
 │   ► task_text = _render(step.task_template, ctx)
 │     (raises SupervisorConfigError on missing {xxx})
 │
 │   ► worker = self.worker_loops[step.worker]
 │   ► result = worker.run(
 │         user_message = task_text,
 │         session_id  = session_id,
 │         system_prompt = worker_spec.system_prompt,
 │       )
 │   ► ctx["prev_output"] = result["content"] or ""
 │
 │   ► if result["status"] != "success":
 │         emit("supervisor_step_warning", {"step": i, "status": ...})
 │         status = "partial"
 │
 │   ► emit("workflow_step_end", {"step": i, ...})
 │
 ▼
return {
  status: status,
  content: ctx["prev_output"],
  run_id, run_dir, session_id,
}
```

### Worker isolation matrix

| Dimension | Today | Phase 3 |
|-----------|-------|---------|
| Tools | `_build_worker_registry` filter by name | unchanged — filtered by `WorkerSpec.tools` |
| Skills | global `SkillsLoader`, all visible | `FilteredSkillsLoader` by `WorkerSpec.skills` |
| `system_prompt` | single default | `WorkerSpec.system_prompt` overrides per worker |
| `max_iterations` | global `MAX_ITERATIONS = 30` | `WorkerSpec.max_iterations` per worker |
| `session_id` | shared | unchanged — shared, so `GET /sessions/{id}` shows the full multi-agent trace |
| Trace files | one `run_dir` per AgentLoop call | unchanged |

### Dataclasses

```python
# loop_agent/orchestration/specs.py
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class WorkerSpec:
    """Identity for one worker AgentLoop."""
    name: str                                     # unique id; not empty
    tools: List[str]                              # names from build_registry()
    skills: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None           # None → use ContextBuilder default
    max_iterations: int = 30

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("WorkerSpec.name must not be empty")


@dataclass
class WorkflowStep:
    """One step in the supervisor's workflow."""
    worker: str                                    # must match a WorkerSpec.name
    task_template: str                             # supports {task} and {prev_output}
```

### Filtered Skills Loader

`SkillsLoader` is the existing class that knows how to scan the bundled +
user-skill directories for SKILL.md files. Workers today share one global
instance, so every worker sees every skill description (and every worker
that holds the `load_skill` tool can read any skill body).

We need a proxy that exposes only an allow-listed subset. `LoadSkillTool`
calls `loader.get_content(name)` (see `loop_agent/tools/load_skill_tool.py`)
to resolve a name to a body, so the proxy must override `get_content` —
**not invent a `load(name)` method that does not exist on the base class.**

```python
# loop_agent/orchestration/filtered_skills.py
from loop_agent.agent.skills import SkillsLoader


class FilteredSkillsLoader(SkillsLoader):
    """SkillsLoader proxy that exposes only an allow-listed subset.

    Subclassing keeps duck-typing compatibility with `LoadSkillTool` and
    `ContextBuilder` (both expect a `SkillsLoader`-shaped object).

    Both `skills` (the list exposed to `ContextBuilder` for prompt assembly)
    and `get_content(name)` (the path used by `LoadSkillTool.execute`) are
    narrowed to the allowed set. Reading an unauthorized skill raises
    `PermissionError` — fail-fast and never synthetic, so an LLM cannot
    trick a worker into reading skills outside its scope.
    """

    def __init__(self, full: SkillsLoader, allowed: set[str]):
        # Snapshot skill list at construction; do not call super().__init__()
        # because that would re-scan the disk. The base class has no useful
        # state besides `skills` / `_user_skills_dir` / `skills_dir`.
        self._all = list(full.skills)
        self._user_skills_dir = getattr(full, "_user_skills_dir", None)
        self.skills_dir = getattr(full, "skills_dir", None)
        self.skills = [s for s in self._all if s.name in set(allowed)]
        self._allowed = set(allowed)
        self._skill_by_name = {s.name: s for s in self._all}

    def get_content(self, name: str) -> str:
        if name not in self._allowed:
            raise PermissionError(
                f"Skill '{name}' is not available to this worker"
            )
        if name in self._skill_by_name:
            skill = self._skill_by_name[name]
            return f'<skill name="{name}">\n{skill.body}\n</skill>'
        # Authorized but not in the snapshot — fall through to the base
        # implementation (which lazily loads from disk if available).
        return super().get_content(name)
```

### Supervisor changes

The `WORKER_TOOLS` constant disappears. Default values move into two class
constants:

```python
# loop_agent/orchestration/supervisor.py
_DEFAULT_WORKERS = [
    WorkerSpec(
        name="research",
        tools=["web_search"],
        system_prompt=None,            # use default
        max_iterations=20,
    ),
    WorkerSpec(
        name="writer",
        tools=["read_file", "write_file", "echo"],
        system_prompt=None,            # use default
        max_iterations=20,
    ),
]

_DEFAULT_WORKFLOW = [
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
    def __init__(
        self,
        llm: Optional[ChatLLM] = None,
        session_store: Optional[SessionStore] = None,
        workers: Optional[List[WorkerSpec]] = None,
        workflow: Optional[List[WorkflowStep]] = None,
    ):
        if workers is not None and len(workers) == 0:
            raise ValueError("workers must contain at least one WorkerSpec")
        if workflow is not None and len(workflow) == 0:
            raise ValueError("workflow must contain at least one WorkflowStep")

        self.worker_specs: List[WorkerSpec] = workers or list(_DEFAULT_WORKERS)
        self.workflow: List[WorkflowStep] = workflow or list(_DEFAULT_WORKFLOW)
        self.llm = llm or ChatLLM()
        self.session_store = session_store

        # Build worker loops eagerly so unknown workers fail at construction.
        names = [w.name for w in self.worker_specs]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Duplicate WorkerSpec.name detected; names must be unique: {names}"
            )
        for step in self.workflow:
            if step.worker not in set(names):
                raise ValueError(
                    f"WorkflowStep references unknown worker '{step.worker}'"
                )
        self.worker_loops = self._build_workers()

    def _build_skills_loader(self, allowed: List[str]) -> SkillsLoader:
        full = SkillsLoader()
        if not allowed:
            return full
        return FilteredSkillsLoader(full, allowed=set(allowed))

    def _build_workers(self) -> Dict[str, AgentLoop]:
        full_registry = build_registry()
        loops: Dict[str, AgentLoop] = {}
        for spec in self.worker_specs:
            registry = ToolRegistry()
            for tool_name in spec.tools:
                tool = full_registry.get(tool_name)
                if tool is None:
                    raise ValueError(
                        f"WorkerSpec({spec.name!r}) references unknown tool "
                        f"{tool_name!r}"
                    )
                registry.register(tool)
            skills_loader = self._build_skills_loader(spec.skills)
            loops[spec.name] = AgentLoop(
                registry,
                self.llm,
                memory=WorkspaceMemory(),
                session_store=self.session_store,
                skills_loader=skills_loader,
                max_iterations=spec.max_iterations,
            )
        return loops

    def run(self, task: str, session_id: str = "") -> Dict[str, Any]:
        ctx = {"task": task, "prev_output": ""}
        status = "success"
        last_step_warning: Dict[str, Any] | None = None

        for i, step in enumerate(self.workflow):
            try:
                task_text = step.task_template.format(**ctx)
            except KeyError as exc:
                raise SupervisorConfigError(
                    f"WorkflowStep[{i}] (worker={step.worker!r}) has unknown "
                    f"placeholder {{{exc.args[0]!r}}} in task_template; "
                    f"only {{{{task}}}} and {{{{prev_output}}}} are supported. "
                    f"Template: {step.task_template[:200]!r}"
                ) from exc

            self._emit("workflow_step_start", {
                "step": i,
                "worker": step.worker,
                "task_preview": task_text[:200],
            })

            worker_loop = self.worker_loops[step.worker]
            spec = next(s for s in self.worker_specs if s.name == step.worker)
            result = worker_loop.run(
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
                status = "partial"
                last_step_warning = {
                    "step": i,
                    "worker": step.worker,
                    "status": result.get("status"),
                }
                self._emit("supervisor_step_warning", last_step_warning)

        return {
            "status": status,
            "content": ctx["prev_output"],
            "run_id": "",            # workers each have their own run_id; aggregate here is empty
            "run_dir": "",
            "session_id": session_id,
        }


class SupervisorConfigError(Exception):
    """Workflow step template rendering error (unknown placeholder)."""
```

Note: the worker `AgentLoop.run` already constructs its own `run_id` /
`run_dir`; the Supervisor's aggregate return keeps them blank because they
refer to per-worker runs. The user-facing `GET /sessions/{session_id}`
remains the canonical place to inspect each worker run.

### AgentLoop signature change

```python
# loop_agent/agent/loop.py
def __init__(
    self,
    registry: ToolRegistry,
    llm: ChatLLM,
    memory: Optional[WorkspaceMemory] = None,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    max_iterations: int = MAX_ITERATIONS,
    session_store: Optional["SessionStore"] = None,
    skills_loader: Optional[SkillsLoader] = None,   # NEW
) -> None:
    ...
    self._skills_loader = skills_loader             # NEW
```

And in `run()`, replace `ContextBuilder(self.registry, self.memory)` with:

```python
skills_loader = self._skills_loader or SkillsLoader()
context = ContextBuilder(self.registry, self.memory, skills_loader)
```

This is non-breaking: callers that omit `skills_loader` get the same default
loader as before.

### Event stream additions

Two new event types flow through the same `event_callback` machinery:

| Event | When | Payload |
|-------|------|---------|
| `workflow_step_start` | Supervisor enters a step | `{step, worker, task_preview}` |
| `workflow_step_end` | Worker call returns | `{step, worker, status, content_preview}` |
| `supervisor_step_warning` | Worker step did not succeed | `{step, worker, status}` |

These are additive — existing SSE / CLI consumers ignore events they don't
recognize, so existing tests still pass.

### Status taxonomy

`Supervisor.run()` return values now include a new `partial` status:

| Worker step status | Supervisor status |
|--------------------|-------------------|
| all `success` | `success` |
| any `error` / `max_iterations` / `empty` / `cancelled` | `partial` |

The CLI prints `content` regardless of status (already does today). The API
response carries `status` so callers can branch.

## CLI

```bash
loop-agent run-supervised "Write a report on Alibaba's 2024 ESG progress"
```

No new flags in this phase. A later phase can add `--workflow path.json` for
custom flows.

## API

```bash
POST /chat/supervised
Content-Type: application/json

{
  "prompt": "Write a report on Alibaba's 2024 ESG progress",
  "session_id": "demo"
}
```

Response shape unchanged from `/chat`. The richer `workflow_step_*` events
flow through the same `/chat/stream` SSE channel if invoked via
`POST /chat/supervised/stream` (out of scope for this phase unless trivial
to add).

## Testing

### Backward-compat (must pass unchanged)

- All 10 existing tests in `tests/test_supervisor.py` keep passing without
  modification. They assert the same end-to-end behavior (research worker
  then writer worker then finalize-equivalent final capture).
- All 79 other existing tests continue to pass.

### New tests (`~14`)

`tests/test_worker_spec.py`:

1. `test_worker_spec_default_field_values` — skills defaults to `[]`, system_prompt defaults to `None`, max_iterations defaults to 30.
2. `test_worker_spec_equality` — two specs with same fields compare equal.
3. `test_worker_spec_rejects_empty_name` — `WorkerSpec("", [...])` raises `ValueError`.

`tests/test_filtered_skills.py`:

4. `test_filtered_skills_empty_allowed_returns_everything` — proxy with no allow list passes through all skills.
5. `test_filtered_skills_narrows_descriptions` — non-allowed names disappear from `get_descriptions()` and from `.skills`.
6. `test_filtered_skills_load_allowed_name_via_get_content` — proxy returns the matching skill body through `get_content()`.
7. `test_filtered_skills_load_unauthorized_via_get_content_raises_permission_error` — `get_content("private")` raises `PermissionError`, not the synthetic fallback string.
8. `test_filtered_skills_snapshot_isolation` — adding skills to the underlying loader after construction does not leak into the filtered view.

`tests/test_supervisor.py` (additions, existing 10 untouched):

9. `test_supervisor_uses_default_workers_when_constructor_args_omitted` — same workers, same workflow as today.
10. `test_supervisor_renders_workflow_template_with_task_and_prev_output` — multi-step example uses `{prev_output}` correctly.
11. `test_supervisor_passess_per_worker_system_prompt` — given `WorkerSpec(system_prompt="...")`, the worker is invoked with that prompt.
12. `test_supervisor_partial_status_when_worker_fails` — given a worker returning `{"status": "error"}`, the supervisor returns `status="partial"` and still propagates content.
13. `test_supervisor_unknown_worker_in_workflow_raises_value_error` — constructor fails fast.
14. `test_supervisor_template_unknown_placeholder_raises_supervisor_config_error` — task template containing `{bogus}` raises with the step index.

### Total target

89 → ~103 tests passing. CI gate: full `pytest -v` must be green before merge.

## Files

Create:

- `loop_agent/orchestration/specs.py` — `WorkerSpec`, `WorkflowStep`.
- `loop_agent/orchestration/filtered_skills.py` — `FilteredSkillsLoader`.
- `tests/test_worker_spec.py`.
- `tests/test_filtered_skills.py`.

Modify:

- `loop_agent/orchestration/supervisor.py` — rewrite around `WorkerSpec` / `WorkflowStep`; remove `_COORDINATOR_PROMPT`, `_build_coordinator`, `FinalizeTool` dependency; add `SupervisorConfigError`.
- `loop_agent/orchestration/__init__.py` — export the new dataclasses and error.
- `loop_agent/orchestration/tools.py` — keep `DelegateTool` *and* `FinalizeTool` importable; both classes gain a `DeprecationWarning` at module import (or at class instantiation) so any external consumer is loudly notified, but nothing breaks this phase.
- `loop_agent/agent/loop.py` — add `skills_loader` kwarg to `__init__`; thread it into `ContextBuilder` in `run()`.
- `tests/test_supervisor.py` — append 6 new tests; do **not** touch existing 10.
- `README.md` — one-line note in the Multi-Agent section pointing at the docs for custom workflows; bump test count.

Delete (only if no remaining references):

- None this phase. `DelegateTool` and `FinalizeTool` are intentionally retained in `tools.py` with `DeprecationWarning`. A future phase may delete them once external consumers are migrated.

## Backward compatibility

- `Supervisor(llm, session_store)` (today's call shape) — unchanged; defaults match Phase 2.4 behavior.
- `Supervisor()` — unchanged.
- `run-supervised` CLI — unchanged.
- `POST /chat/supervised` API — unchanged.
- `tests/test_supervisor.py` existing 10 — unchanged.

## Risks

| Risk | Mitigation |
|------|------------|
| `AgentLoop.__init__` change touches a hot path | Adding a kwarg with `None` default is non-breaking; full existing test suite is the contract. |
| Removing `finalize` tool breaks a downstream consumer expecting it | Keep `FinalizeTool` importable from `loop_agent.orchestration.tools` with a `DeprecationWarning`; removal deferred to a later phase. |
| Per-worker `system_prompt` overrides silently break callers that rely on the default behavior | Defaults are `None`, meaning "use ContextBuilder default" — identical behavior to today. |
| Template injection via user-provided task containing `{prev_output}` | Format string treats `{prev_output}` as a literal placeholder; raw user input flows into *worker* prompts, not the format template, so no injection risk. |
| Worker step fails mid-workflow with no partial content | Status `partial` + non-empty `content` (whatever the failing step produced); empty content only if first step empty. |
| Long `prev_output` strings bloat next-step prompts | Existing worker `system_prompt` / `ContextBuilder` already cap tool results; same applies to worker output. No new mitigation required; revisit in Phase 4 if measured to overflow. |

## Open questions

None blocking this phase. Future enhancements to consider post-merge:

- Reflection loop (`accept` judge step).
- Parallel step (a `WorkflowStep.worker` that takes a list and merges results).
- CLI flag `--workflow path/to/json` and `POST /chat/workflow` to pass declarative specs.
- Skill corpus expansion (writing skills, search skills).
