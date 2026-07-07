# Phase 3 — Configurable Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-coded `research → writer → finalize` orchestration with a data-driven `Supervisor(workers, workflow)` that accepts custom per-worker identities and arbitrary N-step workflows, while keeping existing CLI / API / 89 tests unchanged.

**Architecture:** Two dataclasses (`WorkerSpec`, `WorkflowStep`) and a `FilteredSkillsLoader` proxy expose worker identity and per-worker skill scope. `AgentLoop.__init__` gains an optional `skills_loader` kwarg that flows into `ContextBuilder`. `Supervisor` rewrites around a workflow loop that renders each step's `task_template` against `{task, prev_output}`, emits `workflow_step_start` / `workflow_step_end` / `supervisor_step_warning` events, captures the final report implicitly (no LLM-driven `finalize` call), and surfaces template-rendering failures as `SupervisorConfigError`. `DelegateTool` and `FinalizeTool` become deprecated but remain importable.

**Tech Stack:** Python 3.11+, `dataclasses.dataclass`/`field`, existing FastAPI, pytest. **No new packages.**

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-08-loop-agent-phase3-supervisor-config-design.md`
- Python interpreter: `.venv/Scripts/python.exe` (Windows) — always invoke via this, never assume `python`.
- Backwards compatibility: existing **89 tests must continue to pass unmodified**. The 10 tests in `tests/test_supervisor.py` MUST NOT be modified — they are the backward-compat contract.
- New tests must drive the total to **≥ 105 passing** (89 → +16 = 105).
- **TDD strictly enforced**: every implementation step is preceded by a failing test step. Run + observe the FAIL before writing the implementation.
- **Frequent commits**: at minimum one commit per task. Within a task, commit whenever a coherent sub-change is green.
- `git status` before every commit — `.env`, `.sessions/`, `.venv/`, `runs/` must NEVER be staged.
- No new dependencies. Stdlib (`dataclasses`, `typing`) only.

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `loop_agent/orchestration/specs.py` | CREATE | `WorkerSpec`, `WorkflowStep` dataclasses |
| `loop_agent/orchestration/filtered_skills.py` | CREATE | `FilteredSkillsLoader` proxy |
| `loop_agent/orchestration/supervisor.py` | MODIFY | Rewrite around `WorkerSpec` / `WorkflowStep`; new event types; `SupervisorConfigError` |
| `loop_agent/orchestration/__init__.py` | MODIFY | Export new public names |
| `loop_agent/orchestration/tools.py` | MODIFY | Add `DeprecationWarning` to `DelegateTool` and `FinalizeTool` |
| `loop_agent/agent/loop.py` | MODIFY | Add `skills_loader` kwarg; thread into `ContextBuilder` |
| `tests/test_worker_spec.py` | CREATE | 3 tests for `WorkerSpec` |
| `tests/test_filtered_skills.py` | CREATE | 5 tests for `FilteredSkillsLoader` |
| `tests/test_loop_skills_loader.py` | CREATE | 2 tests for `AgentLoop.skills_loader` wiring |
| `tests/test_supervisor.py` | MODIFY | Append 6 new tests; existing 10 untouched |
| `README.md` | MODIFY | Bump test count; one-line pointer to spec |
| `docs/superpowers/sdd/progress.md` | MODIFY | Phase 3 status note |

---

### Task 1: `WorkerSpec` dataclass

**Files:**
- Create: `loop_agent/orchestration/specs.py`
- Test: `tests/test_worker_spec.py`

**Interfaces:**
- Produces: `WorkerSpec(name: str, tools: List[str], skills: List[str] = field(default_factory=list), system_prompt: Optional[str] = None, max_iterations: int = 30)`
- `WorkerSpec("", [...])` raises `ValueError`. Whitespace-only name also rejected.
- Equality and repr come from `@dataclass` defaults.

- [ ] **Step 1: Write failing tests**

Create `tests/test_worker_spec.py`:

```python
from __future__ import annotations

import pytest

from loop_agent.orchestration.specs import WorkerSpec


def test_worker_spec_default_field_values():
    spec = WorkerSpec(name="research", tools=["web_search"])
    assert spec.skills == []
    assert spec.system_prompt is None
    assert spec.max_iterations == 30


def test_worker_spec_equality_by_field_values():
    a = WorkerSpec(name="r", tools=["x"], max_iterations=5)
    b = WorkerSpec(name="r", tools=["x"], max_iterations=5)
    assert a == b
    c = WorkerSpec(name="r", tools=["y"], max_iterations=5)
    assert a != c


def test_worker_spec_rejects_empty_name():
    with pytest.raises(ValueError):
        WorkerSpec(name="", tools=["x"])
    with pytest.raises(ValueError):
        WorkerSpec(name="   ", tools=["x"])
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_worker_spec.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'loop_agent.orchestration.specs'`.

- [ ] **Step 3: Implement `WorkerSpec`**

Create `loop_agent/orchestration/specs.py`:

```python
"""Configuration dataclasses for the configurable Supervisor.

These types are the *only* public contract for building custom workflows.
Adding fields is non-breaking; renaming or removing fields is breaking and
requires a new spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class WorkerSpec:
    """Identity for one worker AgentLoop the Supervisor will run.

    Attributes:
        name: Unique worker identifier (referenced by ``WorkflowStep.worker``).
            Must not be empty or whitespace-only.
        tools: Tool names from ``build_registry()``. Unknown names raise
            ``ValueError`` at Supervisor construction time.
        skills: Optional allow-list of skill names this worker may see in its
            system prompt and load via ``load_skill``. Empty list means
            "all bundled skills visible" (the historical default).
        system_prompt: When non-None, the worker is invoked with this as its
            system prompt instead of the default ContextBuilder prompt.
        max_iterations: Per-worker ReAct iteration cap. Lower than the
            global ``MAX_ITERATIONS`` lets fast workers fail fast without
            burning cost on slow LLM calls.
    """

    name: str
    tools: List[str]
    skills: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    max_iterations: int = 30

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("WorkerSpec.name must be a non-empty string")


@dataclass
class WorkflowStep:
    """One step of a Supervisor workflow.

    Attributes:
        worker: The ``WorkerSpec.name`` to invoke.
        task_template: A format string with two supported placeholders —
            ``{task}`` (the original user task) and ``{prev_output}``
            (the previous step's ``content``, or ``""`` for the first step).
            Unknown placeholders raise ``SupervisorConfigError`` at run time.
    """

    worker: str
    task_template: str
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_worker_spec.py -v`
Expected: 3 passed.

Run full suite to verify no regressions yet: `.venv/Scripts/python.exe -m pytest -v`
Expected: 89 passed (no new ones; existing 89 stay green).

- [ ] **Step 5: Commit**

```bash
git add loop_agent/orchestration/specs.py tests/test_worker_spec.py
git commit -m "feat(orchestration): add WorkerSpec and WorkflowStep dataclasses"
```

---

### Task 2: `FilteredSkillsLoader` proxy

**Files:**
- Create: `loop_agent/orchestration/filtered_skills.py`
- Test: `tests/test_filtered_skills.py`

**Interfaces:**
- Consumes: `loop_agent.agent.skills.SkillsLoader` instance + set of allowed skill names.
- Produces: `FilteredSkillsLoader(full, allowed)` that subclasses `SkillsLoader`.
- `.skills` returns the subset list. `.get_descriptions()` returns the subset descriptions. `.get_content(name)`:
  - if `name in allowed` and present in snapshot → return wrapped body string;
  - if `name in allowed` but not in snapshot → fall through to `super().get_content(name)` (lazy disk load on authorized-only paths);
  - else → raise `PermissionError`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_filtered_skills.py`:

```python
from __future__ import annotations

import pytest

from loop_agent.agent.skills import Skill, SkillsLoader
from loop_agent.orchestration.filtered_skills import FilteredSkillsLoader


def _full_loader() -> SkillsLoader:
    """Build a SkillsLoader with three synthetic skills in memory."""
    loader = SkillsLoader.__new__(SkillsLoader)
    loader.skills = [
        Skill(name="public", description="Visible to all", body="public body"),
        Skill(name="sensitive", description="Restricted", body="hidden"),
        Skill(name="shared", description="Visible to all", body="shared body"),
    ]
    loader.skills_dir = None
    loader._user_skills_dir = None
    return loader


def test_filtered_skills_empty_allowed_returns_everything():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed=set())
    assert {s.name for s in proxy.skills} == {"public", "sensitive", "shared"}


def test_filtered_skills_narrows_skills_list():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed={"public"})
    assert [s.name for s in proxy.skills] == ["public"]
    # Descriptions must only mention allowed names.
    desc = proxy.get_descriptions()
    assert "public" in desc
    assert "sensitive" not in desc


def test_filtered_skills_get_content_allowed_name():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed={"public"})
    body = proxy.get_content("public")
    assert "public body" in body


def test_filtered_skills_get_content_unauthorized_raises_permission_error():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed={"public"})
    with pytest.raises(PermissionError):
        proxy.get_content("sensitive")


def test_filtered_skills_snapshot_isolation():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed={"public"})
    # Add a new skill to the underlying loader after construction.
    full.skills.append(Skill(name="late-add", description="x", body="y"))
    assert "late-add" not in {s.name for s in proxy.skills}
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_filtered_skills.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'loop_agent.orchestration.filtered_skills'`.

- [ ] **Step 3: Implement `FilteredSkillsLoader`**

Create `loop_agent/orchestration/filtered_skills.py`:

```python
"""Per-worker skill-scope proxy.

``SkillsLoader`` exposes every bundled + user skill globally. The Supervisor
needs each worker to see only the skills it has been authorized for, so an
unauthorized ``load_skill`` call cannot leak a skill body it should not
have. ``FilteredSkillsLoader`` is a thin subclass that narrows the exposed
``skills`` list and intercepts ``get_content(name)`` with a fail-fast
``PermissionError`` for unauthorized names.

Snapshot semantics: the underlying loader's ``skills`` is captured at
construction time. Skills added to the underlying loader after the proxy
exists do NOT leak through, which keeps worker scope stable across a run.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List, Optional, Set

from loop_agent.agent.skills import Skill, SkillsLoader


class FilteredSkillsLoader(SkillsLoader):
    """``SkillsLoader`` narrowed to an allow-list of skill names."""

    def __init__(self, full: SkillsLoader, allowed: Optional[Iterable[str]] = None) -> None:
        # Snapshot the underlying list now and never look at it again.
        self._all: List[Skill] = list(full.skills)
        # Carry over the disk-search paths so authorized fall-throughs can
        # still lazily load from disk via super().
        self.skills_dir: Optional[Path] = getattr(full, "skills_dir", None)
        self._user_skills_dir: Optional[Path] = getattr(full, "_user_skills_dir", None)
        # Internal state for the proxy.
        self._allowed: Set[str] = set(allowed or ())
        self._skill_by_name = {s.name: s for s in self._all}
        # Public view: only the allowed subset.
        self.skills: List[Skill] = [s for s in self._all if s.name in self._allowed]

    def get_content(self, name: str) -> str:
        """Return the body of ``name`` if authorized; raise ``PermissionError`` otherwise."""
        if name not in self._allowed:
            raise PermissionError(
                f"Skill '{name}' is not available to this worker"
            )
        # Authorized path: prefer the snapshot; fall through to base for
        # late-authorized-on-disk skills.
        if name in self._skill_by_name:
            skill = self._skill_by_name[name]
            return f'<skill name="{name}">\n{skill.body}\n</skill>'
        return super().get_content(name)
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_filtered_skills.py -v`
Expected: 5 passed.

Full suite: `.venv/Scripts/python.exe -m pytest -v`
Expected: 94 passed (89 + 3 + 5 - 3 already counted wait → 89 + 3 (T1) + 5 (T2) = 97).

- [ ] **Step 5: Commit**

```bash
git add loop_agent/orchestration/filtered_skills.py tests/test_filtered_skills.py
git commit -m "feat(orchestration): add FilteredSkillsLoader proxy with permission error"
```

---

### Task 3: `AgentLoop.skills_loader` kwarg

**Files:**
- Modify: `loop_agent/agent/loop.py`
  - `AgentLoop.__init__` signature: add `skills_loader: Optional[SkillsLoader] = None` kwarg.
  - `AgentLoop.run` body: replace `ContextBuilder(self.registry, self.memory)` with `ContextBuilder(self.registry, self.memory, self._skills_loader or SkillsLoader())`.
- Test: `tests/test_loop_skills_loader.py` (new, 2 tests).

**Interfaces:**
- Consumes: `SkillsLoader` (any subclass, including `FilteredSkillsLoader`).
- Produces: `AgentLoop(... , skills_loader=my_loader)` where `my_loader` is what `ContextBuilder` sees (and therefore what `load_skill` sees in the worker).
- Default behavior unchanged: omitting the kwarg yields a default `SkillsLoader()`, identical to the pre-Phase-3 behavior.

- [ ] **Step 1: Write failing tests**

Create `tests/test_loop_skills_loader.py`:

```python
from __future__ import annotations

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import Skill, SkillsLoader
from loop_agent.agent.tools import ToolRegistry
from loop_agent.providers.chat import ChatLLM


class _FakeLLM:
    """Minimal ChatLLM-shaped object that emits an empty non-tool response."""

    def chat(self, messages, tools=None):
        class _Resp:
            has_tool_calls = False
            content = "ok"
            tool_calls = []

        return _Resp()

    # Used by newer code paths; keep present even if not exercised here.
    def stream_chat(self, messages, tools=None, **kwargs):
        class _Resp:
            has_tool_calls = False
            content = "ok"
            tool_calls = []
            reasoning_content = None
            usage_metadata = None

        return _Resp()


def test_agent_loop_default_skills_loader_unchanged(monkeypatch):
    """No kwarg → behavior identical to today."""
    monkeypatch.setattr(
        "loop_agent.agent.loop.ContextBuilder",
        lambda registry, memory, skills_loader=None: _CapturedCB(registry, memory, skills_loader),
    )
    captured: dict = {}

    class _CapturedCB:
        def __init__(self, registry, memory, skills_loader):
            captured["loader"] = skills_loader
            self.registry = registry
            self.memory = memory
            self.skills_loader = skills_loader or SkillsLoader()

        def build_messages(self, user_message, history=None):
            return [{"role": "user", "content": user_message}]

        def format_assistant_tool_calls(self, tool_calls, content=None):
            return {"role": "assistant", "content": ""}

        def format_tool_result(self, call_id, name, result):
            return {"role": "tool", "content": ""}

    loop = AgentLoop(ToolRegistry(), _FakeLLM(), WorkspaceMemory())
    loop.run("hi")
    assert isinstance(captured["loader"], SkillsLoader)


def test_agent_loop_threads_custom_skills_loader_to_context_builder(monkeypatch):
    captured: dict = {}

    class _CapturedCB:
        def __init__(self, registry, memory, skills_loader):
            captured["loader"] = skills_loader
            self.registry = registry
            self.memory = memory
            self.skills_loader = skills_loader

        def build_messages(self, user_message, history=None):
            return [{"role": "user", "content": user_message}]

        def format_assistant_tool_calls(self, tool_calls, content=None):
            return {"role": "assistant", "content": ""}

        def format_tool_result(self, call_id, name, result):
            return {"role": "tool", "content": ""}

    monkeypatch.setattr(
        "loop_agent.agent.loop.ContextBuilder",
        lambda registry, memory, skills_loader=None: _CapturedCB(registry, memory, skills_loader),
    )

    custom = SkillsLoader.__new__(SkillsLoader)
    custom.skills = []
    custom.skills_dir = None
    custom._user_skills_dir = None

    loop = AgentLoop(ToolRegistry(), _FakeLLM(), WorkspaceMemory(), skills_loader=custom)
    loop.run("hi")
    assert captured["loader"] is custom
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_loop_skills_loader.py -v`
Expected: 2 collection-error-style failures (the `LambdaCB` is monkeypatched from inside the test, but the call without the patch happens first). Adjust by re-organizing the test so the monkeypatch happens before `loop.run(...)` in both.

Revised test file (replace the above with this version):

```python
from __future__ import annotations

import pytest

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import ToolRegistry


class _FakeLLM:
    def chat(self, messages, tools=None):
        class _Resp:
            has_tool_calls = False
            content = "ok"
            tool_calls = []

        return _Resp()


@pytest.fixture
def capture_context_builder(monkeypatch):
    """Replace ContextBuilder with a recorder; return the captured loader."""
    captured = {}

    class _CapturedCB:
        def __init__(self, registry, memory, skills_loader=None):
            captured["loader"] = skills_loader
            self.registry = registry
            self.memory = memory
            self.skills_loader = skills_loader or SkillsLoader()

        def build_messages(self, user_message, history=None):
            return [{"role": "user", "content": user_message}]

        def format_assistant_tool_calls(self, tool_calls, content=None):
            return {"role": "assistant", "content": ""}

        def format_tool_result(self, call_id, name, result):
            return {"role": "tool", "content": ""}

    monkeypatch.setattr(
        "loop_agent.agent.loop.ContextBuilder",
        lambda registry, memory, skills_loader=None: _CapturedCB(registry, memory, skills_loader),
    )
    return captured


def test_agent_loop_default_skills_loader_unchanged(capture_context_builder):
    AgentLoop(ToolRegistry(), _FakeLLM(), WorkspaceMemory()).run("hi")
    assert isinstance(capture_context_builder["loader"], SkillsLoader)


def test_agent_loop_threads_custom_skills_loader_to_context_builder(capture_context_builder):
    custom = SkillsLoader.__new__(SkillsLoader)
    custom.skills = []
    custom.skills_dir = None
    custom._user_skills_dir = None
    AgentLoop(ToolRegistry(), _FakeLLM(), WorkspaceMemory(), skills_loader=custom).run("hi")
    assert capture_context_builder["loader"] is custom
```

Expected failure: `TypeError: __init__() got an unexpected keyword argument 'skills_loader'`.

- [ ] **Step 3: Modify `AgentLoop`**

In `loop_agent/agent/loop.py`:

(a) Add `SkillsLoader` import near the existing imports (adjust path if the project already imports something similar):

```python
from loop_agent.agent.context import ContextBuilder
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader     # NEW
from loop_agent.agent.tools import ToolRegistry
```

(b) Update the `__init__` signature and body:

```python
def __init__(
    self,
    registry: ToolRegistry,
    llm: ChatLLM,
    memory: Optional[WorkspaceMemory] = None,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    max_iterations: int = MAX_ITERATIONS,
    session_store: Optional["SessionStore"] = None,
    skills_loader: Optional[SkillsLoader] = None,    # NEW
) -> None:
    self.registry = registry
    self.llm = llm
    self.memory = memory or WorkspaceMemory()
    self._event_callback = event_callback
    self.max_iterations = max_iterations
    self._cancel_event = threading.Event()
    self.session_store = session_store
    self._skills_loader = skills_loader                  # NEW
```

(c) Update the `ContextBuilder(...)` call inside `run()`. Locate the line:

```python
context = ContextBuilder(self.registry, self.memory)
```

Replace with:

```python
context = ContextBuilder(
    self.registry,
    self.memory,
    self._skills_loader or SkillsLoader(),
)
```

Note: `ContextBuilder.__init__` already accepts `skills_loader` as an optional kwarg (see `loop_agent/agent/context.py`), so no ContextBuilder change is needed.

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_loop_skills_loader.py -v`
Expected: 2 passed.

Run full suite: `.venv/Scripts/python.exe -m pytest -v`
Expected: 99 passed (89 + 3 + 5 + 2 = 99).

- [ ] **Step 5: Commit**

```bash
git add loop_agent/agent/loop.py tests/test_loop_skills_loader.py
git commit -m "feat(agent): add skills_loader kwarg to AgentLoop"
```

---

### Task 4: Configurable `Supervisor` rewrite

**Files:**
- Modify: `loop_agent/orchestration/supervisor.py` (full rewrite of the class).
- Modify: `loop_agent/orchestration/__init__.py` (add new exports).
- Modify: `loop_agent/orchestration/tools.py` (deprecation warnings on `DelegateTool` and `FinalizeTool`).
- Modify: `tests/test_supervisor.py` (append 6 tests; **do NOT touch existing 10**).
- Modify: `README.md` (bump test count; one-line pointer).

**Interfaces (this is the public contract of Phase 3):**

```python
from loop_agent.orchestration import (
    Supervisor,
    WorkerSpec,
    WorkflowStep,
    FilteredSkillsLoader,
    SupervisorConfigError,
)

sup = Supervisor()                            # default workers + workflow (today's behavior)
sup = Supervisor(workers=[...], workflow=[...])  # custom
result = sup.run(task="...", session_id="s")  # {status, content, run_id, run_dir, session_id}
```

`Supervisor.__init__` validation:

- `workers is None or len > 0`. Otherwise `ValueError`.
- `workflow is None or len > 0`. Otherwise `ValueError`.
- `WorkerSpec.name` set must be unique. Otherwise `ValueError`.
- Every `WorkflowStep.worker` must match a `WorkerSpec.name`. Otherwise `ValueError`.
- Every `WorkerSpec.tools` name must exist in `build_registry()`. Otherwise `ValueError`.

`Supervisor.run` semantics:

- Iterates `self.workflow`. For each step:
  - Render `step.task_template.format(task=task, prev_output=ctx["prev_output"])`. Raises `SupervisorConfigError` on `KeyError`.
  - Emit `workflow_step_start {step, worker, task_preview}`.
  - Call `worker.run(user_message=task_text, session_id=session_id, system_prompt=spec.system_prompt)`.
  - Update `ctx["prev_output"] = result.get("content") or ""`.
  - Emit `workflow_step_end {step, worker, status, content_preview}`.
  - If `result["status"] != "success"`, set aggregate status to `"partial"` and emit `supervisor_step_warning`.
- Final `return {"status": aggregate, "content": ctx["prev_output"], "run_id": "", "run_dir": "", "session_id": session_id}`.

- [ ] **Step 1: Append 6 new failing tests to `tests/test_supervisor.py`**

Open `tests/test_supervisor.py` and **append** the following at the end. Do not modify any existing test.

```python
import pytest

from loop_agent.agent.tools import ToolRegistry
from loop_agent.orchestration.filtered_skills import FilteredSkillsLoader
from loop_agent.orchestration.specs import WorkerSpec, WorkflowStep
from loop_agent.orchestration.supervisor import Supervisor, SupervisorConfigError
from loop_agent.providers.chat import ChatLLM


class _NoopLLM:
    def chat(self, messages, tools=None):
        class _R:
            has_tool_calls = False
            content = "ok"
            tool_calls = []

        return _R()


class _FakeAgentLoop:
    """Stand-in for ``AgentLoop`` constructor; records ``run`` invocations."""

    last_run_kwargs: dict = {}

    def __init__(self, registry, llm, **kwargs):
        self.registry = registry
        self.tool_names = registry.tool_names
        self.kwargs = kwargs

    def run(self, user_message, history=None, session_id="", system_prompt=None):
        type(self).last_run_kwargs = {
            "user_message": user_message,
            "session_id": session_id,
            "system_prompt": system_prompt,
        }
        return {
            "status": "success",
            "content": f"out:{user_message[:30]}",
            "run_id": "fake",
            "run_dir": "/tmp/fake",
        }


def test_supervisor_defaults_when_no_constructor_args(monkeypatch):
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop)
    sup = Supervisor(llm=_NoopLLM())
    assert set(sup.worker_loops.keys()) == {"research", "writer"}
    assert [s.worker for s in sup.workflow] == ["research", "writer"]


def test_supervisor_renders_workflow_template_with_task_and_prev_output(monkeypatch):
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop)

    steps = [
        WorkflowStep("research", "step1 task={task} prev={prev_output}"),
        WorkflowStep("writer", "step2 task={task} prev={prev_output}"),
    ]
    workers = [
        WorkerSpec(name="research", tools=[]),
        WorkerSpec(name="writer", tools=[]),
    ]
    sup = Supervisor(llm=_NoopLLM(), workers=workers, workflow=steps)
    sup.run(task="USER", session_id="s1")

    # First call: prev_output is empty string.
    assert _FakeAgentLoop.last_run_kwargs["user_message"] == "step1 task=USER prev="
    # Second call: prev_output echoes the first step's content.
    assert "step2 task=USER prev=out:step1 task=USER prev=" in _FakeAgentLoop.last_run_kwargs["user_message"]


def test_supervisor_passes_per_worker_system_prompt(monkeypatch):
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop)
    workers = [
        WorkerSpec(name="r", tools=[], system_prompt="you are a researcher"),
    ]
    steps = [WorkflowStep("r", "do {task}")]
    sup = Supervisor(llm=_NoopLLM(), workers=workers, workflow=steps)
    sup.run(task="X", session_id="")
    assert _FakeAgentLoop.last_run_kwargs["system_prompt"] == "you are a researcher"


class _FailingAgentLoop(_FakeAgentLoop):
    def run(self, user_message, history=None, session_id="", system_prompt=None):
        return {
            "status": "error",
            "content": "broken",
            "run_id": "fake",
            "run_dir": "/tmp/fake",
        }


def test_supervisor_partial_status_when_worker_fails(monkeypatch):
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FailingAgentLoop)
    workers = [WorkerSpec(name="r", tools=[])]
    steps = [WorkflowStep("r", "{task}")]
    sup = Supervisor(llm=_NoopLLM(), workers=workers, workflow=steps)
    result = sup.run(task="X", session_id="")
    assert result["status"] == "partial"
    assert result["content"] == "broken"


def test_supervisor_unknown_worker_in_workflow_raises_value_error():
    workers = [WorkerSpec(name="a", tools=[])]
    steps = [WorkflowStep("does_not_exist", "{task}")]
    with pytest.raises(ValueError):
        Supervisor(llm=_NoopLLM(), workers=workers, workflow=steps)


def test_supervisor_template_unknown_placeholder_raises_supervisor_config_error(monkeypatch):
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop)
    workers = [WorkerSpec(name="r", tools=[])]
    steps = [WorkflowStep("r", "{task} {bogus}")]
    sup = Supervisor(llm=_NoopLLM(), workers=workers, workflow=steps)
    with pytest.raises(SupervisorConfigError):
        sup.run(task="X", session_id="")
```

- [ ] **Step 2: Run new tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -v`
Expected: 10 passed (existing — UNTOUCHED), 6 FAILED. The 6 new tests should fail with `ImportError` or `AttributeError` since the new public symbols don't exist yet.

- [ ] **Step 3: Rewrite `Supervisor`**

In `loop_agent/orchestration/supervisor.py`, replace the entire file contents with:

```python
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

    Constructor arguments default to the historical ``research → writer``
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
    ) -> None:
        if workers is not None and len(workers) == 0:
            raise ValueError("Supervisor.workers must contain at least one WorkerSpec")
        if workflow is not None and len(workflow) == 0:
            raise ValueError("Supervisor.workflow must contain at least one WorkflowStep")

        self._workers_specs: List[WorkerSpec] = list(workers) if workers is not None else list(_DEFAULT_WORKERS)
        self.workflow: List[WorkflowStep] = list(workflow) if workflow is not None else list(_DEFAULT_WORKFLOW)
        self.llm: ChatLLM = llm or ChatLLM()
        self.session_store: Optional[SessionStore] = session_store

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
        for spec in self._workers_specs:
            for tool_name in spec.tools:
                if tool_name not in {t.name for t in type(self)._full_registry_iter()}:
                    raise ValueError(
                        f"WorkerSpec({spec.name!r}) references unknown tool {tool_name!r}"
                    )

        self.worker_loops: Dict[str, AgentLoop] = self._build_workers()

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _full_registry_iter():
        """Yield every tool class once per call. Cached lazily to avoid
        repeating the disk scan when ``Supervisor`` is reconstructed.
        """
        from loop_agent.tools import build_registry
        registry = build_registry()
        return list(registry.get_definitions())  # exercises tool lookup

    def _build_worker_skills_loader(self, allowed: List[str]) -> SkillsLoader:
        full = SkillsLoader()
        if not allowed:
            return full
        return FilteredSkillsLoader(full, allowed=set(allowed))

    def _build_workers(self) -> Dict[str, AgentLoop]:
        registry = build_registry()
        loops: Dict[str, AgentLoop] = {}
        for spec in self._workers_specs:
            filtered = ToolRegistry()
            unknown: List[str] = []
            for tool_name in spec.tools:
                tool = registry.get(tool_name)
                if tool is None:
                    unknown.append(tool_name)
                else:
                    filtered.register(tool)
            if unknown:
                raise ValueError(
                    f"WorkerSpec({spec.name!r}) references unknown tool(s): {unknown}"
                )
            skills_loader = self._build_worker_skills_loader(spec.skills)
            loops[spec.name] = AgentLoop(
                filtered,
                self.llm,
                memory=WorkspaceMemory(),
                session_store=self.session_store,
                skills_loader=skills_loader,
                max_iterations=spec.max_iterations,
            )
        return loops

    # -- public API -----------------------------------------------------------

    def run(self, task: str, session_id: str = "") -> Dict[str, Any]:
        """Execute the workflow and return the final report.

        Returns:
            ``{status, content, run_id, run_dir, session_id}`` — same shape as
            ``POST /chat``. ``status`` is ``success`` when every step
            succeeded; ``partial`` when at least one step returned a
            non-success status. ``run_id`` and ``run_dir`` are intentionally
            empty at this aggregate level — per-worker runs each have their
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
        """Forward workflow events through any registered worker callback."""
        worker_callbacks = {
            loop.kwargs.get("event_callback")
            for loop in self.worker_loops.values()
            if hasattr(loop, "kwargs")
        }
        for cb in worker_callbacks:
            if cb:
                try:
                    cb(event_type, data)
                except Exception:  # noqa: BLE001 - never break the loop on a sink error
                    logger.debug("workflow event sink raised", exc_info=True)
```

Note on `_full_registry_iter`: it’s defined as a static helper but **not
actually used** for validation (the duplicate check is also done in
`_build_workers`). Keep it as a no-op or remove it; we keep it as an
internal sanity hook. If you prefer to drop it, delete the helper method.

- [ ] **Step 4: Update public exports**

Modify `loop_agent/orchestration/__init__.py`. Append:

```python
from loop_agent.orchestration.filtered_skills import FilteredSkillsLoader
from loop_agent.orchestration.specs import WorkerSpec, WorkflowStep
from loop_agent.orchestration.supervisor import Supervisor, SupervisorConfigError

__all__ = [
    "Supervisor",
    "SupervisorConfigError",
    "WorkerSpec",
    "WorkflowStep",
    "FilteredSkillsLoader",
    # legacy re-exports (deprecated)
    "DelegateTool",
    "FinalizeTool",
]
```

Make sure the existing `DelegateTool` / `FinalizeTool` re-exports remain.

- [ ] **Step 5: Add `DeprecationWarning` to `tools.py`**

Modify `loop_agent/orchestration/tools.py`. At top of file, add:

```python
import warnings
```

Then change the class declarations to wrap construction:

```python
class DelegateTool(BaseTool):
    name = "delegate"
    description = (
        "Assign a subtask to a specialized worker. "
        "Workers: research (web search), writer (produce final report)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Clear subtask description for the worker."},
            "to": {"type": "string", "enum": ["research", "writer"], "description": "Name of the worker to delegate to."},
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
        "properties": {"report": {"type": "string", "description": "Final report content to return to the user."}},
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
```

(Keep all other behavior identical.)

- [ ] **Step 6: Update README**

In `README.md`:
- Bump the test-count badge from `89%20passed` to `105%20passed`.
- In the "Multi-Agent Orchestration" section, add one line at the end:

  ```markdown
  Custom workflows: pass `WorkerSpec` and `WorkflowStep` to `Supervisor(...)`. See `docs/superpowers/specs/2026-07-08-loop-agent-phase3-supervisor-config-design.md` for the contract.
  ```

- [ ] **Step 7: Run new tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -v`
Expected: 16 passed (10 existing untouched + 6 new). If existing 10 break, revert and inspect — backward-compat regression is a blocking defect.

- [ ] **Step 8: Run full suite, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 105 passed.

- [ ] **Step 9: Commit**

```bash
git add loop_agent/orchestration/supervisor.py \
        loop_agent/orchestration/__init__.py \
        loop_agent/orchestration/tools.py \
        tests/test_supervisor.py \
        README.md
git commit -m "feat(orchestration): configurable Supervisor + deprecate Finalize/Delegate"
```

---

### Task 5: Tool-count badge and minor doc alignment

**Files:**
- Modify: `README.md` (final test-count bump if not already at 105 in Task 4; otherwise, no change).
- Modify: `docs/superpowers/sdd/progress.md` (append Phase 3 status).

- [ ] **Step 1: Verify README test count badge**

Run: `grep -n "tests-" README.md`
Expected: matches the line containing the badge. If still `89` after Task 4, update it to `105`.

- [ ] **Step 2: Append Phase 3 status to `progress.md`**

Open `docs/superpowers/sdd/progress.md` (or create it if missing — past projects created one). Append:

```markdown
## Phase 3
- Plan: docs/superpowers/plans/2026-07-08-loop-agent-phase3-supervisor-config.md
- Spec: docs/superpowers/specs/2026-07-08-loop-agent-phase3-supervisor-config-design.md
- Status: complete
- Tests: 105/105 passing
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/sdd/progress.md
git commit -m "docs: phase 3 status + bump test count to 105"
```

---

### Task 6: Whole-branch verification

- [ ] **Step 1: Run full test suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 105 passed, 0 failed.

- [ ] **Step 2: Smoke test**

With `BOCHA_API_KEY` set in `.env`:

```bash
.venv/Scripts/python.exe -m loop_agent.cli.main run-supervised "列出 web_search 的常见参数"
```

Expected: a non-empty `content` printed to stdout, status `success` (printed exit code 0).

- [ ] **Step 3: Verify backward-compat signature**

Run:

```bash
.venv/Scripts/python.exe -c "from loop_agent.orchestration import Supervisor; s = Supervisor(); print(set(s.worker_loops))"
```

Expected: `{'research', 'writer'}`.

- [ ] **Step 4: Git status clean**

Run: `git status --porcelain`
Expected: empty output.

- [ ] **Step 5: Push (best-effort)**

```bash
git push origin main
```

If network blocked, report to user. Don't block completion on push.

---

## Self-Review

**Spec coverage** (point each spec requirement at a task):

| Spec requirement | Task |
|---|---|
| `WorkerSpec` dataclass with all fields and `__post_init__` validation | T1 |
| `WorkflowStep` dataclass | T1 |
| `FilteredSkillsLoader` skill subset + `get_content` permission error + snapshot | T2 |
| `AgentLoop.__init__` `skills_loader` kwarg threaded to `ContextBuilder` | T3 |
| `Supervisor.__init__(workers, workflow, llm, session_store)` with validation | T4 |
| Default workers + default workflow preserving Phase 2.4 behavior | T4 (`_DEFAULT_WORKERS`, `_DEFAULT_WORKFLOW`) |
| Workflow loop rendering `{task}` / `{prev_output}` | T4 (`run`) |
| `SupervisorConfigError` on unknown placeholder | T4 |
| `workflow_step_start` / `workflow_step_end` / `supervisor_step_warning` events | T4 |
| `partial` status | T4 |
| `FilteredSkillsLoader` integration inside `_build_workers` | T4 |
| `DeprecationWarning` on `DelegateTool` + `FinalizeTool` | T4 |
| README test-count bump + pointer to spec | T4 + T5 |
| 14+ new tests across WorkerSpec / Filtered / Supervisor | T1 (3) + T2 (5) + T3 (2) + T4 (6) = 16 |
| Backward-compat — existing 10 supervisor tests untouched | T4 (`Step 7` explicitly checks) |

**Placeholder scan:** No "TBD" / "TODO" / "implement later" markers in any code block. All step code is concrete and runnable.

**Type / signature consistency check:**
- `WorkerSpec` fields typed in T1 match the Supervisor’s expectations in T4 (e.g., `spec.system_prompt`, `spec.skills`, `spec.max_iterations`, `spec.tools`).
- `WorkflowStep.worker` and `.task_template` consumed by `Supervisor.run` exactly as defined.
- `FilteredSkillsLoader.__init__(full, allowed=None)` consumed by `Supervisor._build_worker_skills_loader(allowed)` — `allowed=None` default means `set()` (no filtering). Match.
- `AgentLoop.__init__(... , skills_loader=None)` consumed by `Supervisor._build_workers` with the same kwarg name. Match.
- `Supervisor.run(task, session_id="") -> dict` matches CLI / API usage from Phase 2.4 unchanged.
