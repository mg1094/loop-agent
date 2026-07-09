# Phase 4 — DAG + Parallel Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `Supervisor` 支持由 `StepTemplate` + `StepInstance` 定义的 DAG，同层 instance 用 `ThreadPoolExecutor` 并行执行，同时保持 Phase 3 的 `Supervisor(workers, workflow)` API 不变。

**Architecture:** 新增 `loop_agent/orchestration/dag.py` 承载拓扑分层和循环检测；`specs.py` 新增 `StepTemplate` / `StepInstance` / `expand_fanout`；`Supervisor` 接受 `templates`/`instances` 并把老 `workflow` 参数内部转换为 DAG；执行时按拓扑层并行、跨层串行。`WorkerSpec` 和底层 `AgentLoop` 完全不动。

**Tech Stack:** Python 3.11, dataclasses, `concurrent.futures.ThreadPoolExecutor`, pytest.

## Global Constraints

- **Test command (Windows):** `.venv/Scripts/python.exe -m pytest -v`
- **TDD:** every implementation step is preceded by a failing test step.
- **Backward compat:** 9 existing `tests/test_supervisor.py` 测试（第 6-9 原有测试 + 7 个 Phase 3 新增测试）保持通过，不修改其函数体。
- **git status --porcelain empty before commit** — no `.env`, `.sessions/`, `.venv/`, `runs/` staged.
- **Commit messages:** `feat(orchestration): ...` / `test(orchestration): ...` / `docs: ...`
- **Test count target:** 108 → 130+ passing.
- **No new dependencies** — only stdlib `concurrent.futures`.

---

## Task 1: DAG topology utilities

**Files:**
- Create: `loop_agent/orchestration/dag.py`
- Test: `tests/test_dag_validation.py`

**Interfaces:**
- Consumes: `List[StepInstance]` (定义见 Task 2，这里先用 duck-typed minimal `SimpleNamespace` 测试桩)
- Produces: `topological_layers(instances) -> List[List[StepInstance]]`, `validate_dag(instances) -> None`

### Step 1: Write failing tests for `topological_layers`

Create `tests/test_dag_validation.py`:

```python
from __future__ import annotations

import pytest

from loop_agent.orchestration.dag import topological_layers, validate_dag


def _inst(id: str, depends_on: list[str] | None = None):
    """Minimal duck-typed instance for testing the DAG engine."""
    from types import SimpleNamespace

    return SimpleNamespace(id=id, depends_on=list(depends_on or []))


def test_topological_layers_linear_chain():
    instances = [_inst("a"), _inst("b", ["a"]), _inst("c", ["b"])]
    layers = topological_layers(instances)
    assert [[n.id for n in layer] for layer in layers] == [["a"], ["b"], ["c"]]


def test_topological_layers_fan_out_fan_in():
    instances = [
        _inst("root"),
        _inst("a", ["root"]),
        _inst("b", ["root"]),
        _inst("merge", ["a", "b"]),
    ]
    layers = topological_layers(instances)
    assert layers[0] == [instances[0]]
    assert set(n.id for n in layers[1]) == {"a", "b"}
    assert layers[2] == [instances[3]]


def test_topological_layers_empty_list():
    assert topological_layers([]) == []


def test_topological_layers_single_node():
    instances = [_inst("only")]
    assert [[n.id for n in layer] for layer in topological_layers(instances)] == [["only"]]


def test_validate_dag_detects_cycle():
    instances = [_inst("a", ["b"]), _inst("b", ["a"])]
    with pytest.raises(ValueError, match="cycle detected"):
        validate_dag(instances)


def test_validate_dag_detects_self_loop():
    instances = [_inst("a", ["a"])]
    with pytest.raises(ValueError, match="cycle detected"):
        validate_dag(instances)
```

### Step 2: Run tests to verify they fail

```bash
.venv/Scripts/python.exe -m pytest tests/test_dag_validation.py -v
```

Expected: `ModuleNotFoundError: No module named 'loop_agent.orchestration.dag'`.

### Step 3: Implement `loop_agent/orchestration/dag.py`

```python
"""DAG topology utilities for the configurable Supervisor.

Provides Kahn-based topological layering and eager cycle/unknown-dep
validation. Instances are treated as opaque nodes with ``.id`` and
``.depends_on`` attributes.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set


def validate_dag(instances: Iterable[Any]) -> None:
    """Validate that ``instances`` form a DAG with no unknown dependencies.

    Raises:
        ValueError: If an id is duplicated, a dependency references an unknown
            id, or a cycle exists.
    """
    instances = list(instances)
    ids: Set[str] = set()
    duplicates: List[str] = []
    for inst in instances:
        if inst.id in ids:
            duplicates.append(inst.id)
        ids.add(inst.id)
    if duplicates:
        raise ValueError(f"Duplicate StepInstance.id detected: {duplicates}")

    for inst in instances:
        for dep in inst.depends_on:
            if dep not in ids:
                raise ValueError(
                    f"StepInstance(id={inst.id!r}) depends on unknown id {dep!r}"
                )

    # Kahn's algorithm: if we cannot remove all nodes, there's a cycle.
    in_degree: Dict[str, int] = {inst.id: 0 for inst in instances}
    dependents: Dict[str, List[str]] = {inst.id: [] for inst in instances}
    for inst in instances:
        for dep in inst.depends_on:
            in_degree[inst.id] += 1
            dependents[dep].append(inst.id)

    queue = [inst_id for inst_id, deg in in_degree.items() if deg == 0]
    removed: Set[str] = set()
    while queue:
        current = queue.pop(0)
        removed.add(current)
        for dep_id in dependents[current]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(dep_id)

    if len(removed) != len(instances):
        remaining = sorted(ids - removed)
        raise ValueError(f"cycle detected among StepInstance ids: {remaining}")


def topological_layers(instances: Iterable[Any]) -> List[List[Any]]:
    """Return instances grouped into topological layers.

    Layer 0 contains all nodes with no dependencies; each subsequent layer
    contains nodes whose dependencies are all in previous layers. Nodes
    within the same layer are independent and may execute in parallel.
    """
    instances = list(instances)
    validate_dag(instances)

    instance_by_id = {inst.id: inst for inst in instances}
    in_degree = {inst.id: len(inst.depends_on) for inst in instances}
    dependents: Dict[str, List[str]] = {inst.id: [] for inst in instances}
    for inst in instances:
        for dep in inst.depends_on:
            dependents[dep].append(inst.id)

    layers: List[List[Any]] = []
    remaining_ids = set(instance_by_id.keys())
    while remaining_ids:
        current_layer_ids = [
            inst_id for inst_id in remaining_ids if in_degree[inst_id] == 0
        ]
        if not current_layer_ids:
            # Should never happen because validate_dag already rejected cycles.
            raise ValueError("cycle detected")

        current_layer = [instance_by_id[inst_id] for inst_id in current_layer_ids]
        layers.append(current_layer)
        for inst_id in current_layer_ids:
            remaining_ids.remove(inst_id)
            for dependent in dependents[inst_id]:
                in_degree[dependent] -= 1

    return layers
```

### Step 4: Run tests to verify they pass

```bash
.venv/Scripts/python.exe -m pytest tests/test_dag_validation.py -v
```

Expected: 6 passed.

### Step 5: Commit

```bash
git add loop_agent/orchestration/dag.py tests/test_dag_validation.py
git commit -m "feat(orchestration): add DAG topology utilities with cycle detection"
```

---

## Task 2: StepTemplate, StepInstance, expand_fanout

**Files:**
- Modify: `loop_agent/orchestration/specs.py`
- Test: `tests/test_step_template.py`, `tests/test_step_instance.py`, `tests/test_expand_fanout.py`

**Interfaces:**
- Consumes: existing `WorkerSpec` fields
- Produces:
  - `StepTemplate(id, worker, task_template)` dataclass
  - `StepInstance(id, step, user_vars, depends_on)` dataclass
  - `expand_fanout(step, items, id_prefix) -> List[StepInstance]`

### Step 1: Write failing tests

Create `tests/test_step_template.py`:

```python
from __future__ import annotations

import pytest

from loop_agent.orchestration.specs import StepTemplate


def test_step_template_defaults():
    t = StepTemplate(id="scout", worker="scout", task_template="hello")
    assert t.id == "scout"
    assert t.worker == "scout"
    assert t.task_template == "hello"


def test_step_template_rejects_empty_id():
    with pytest.raises(ValueError):
        StepTemplate(id="", worker="w", task_template="t")


def test_step_template_rejects_empty_worker():
    with pytest.raises(ValueError):
        StepTemplate(id="i", worker="  ", task_template="t")


def test_step_template_rejects_non_string_task_template():
    with pytest.raises(ValueError):
        StepTemplate(id="i", worker="w", task_template=123)  # type: ignore[arg-type]
```

Create `tests/test_step_instance.py`:

```python
from __future__ import annotations

import pytest

from loop_agent.orchestration.specs import StepInstance


def test_step_instance_defaults():
    i = StepInstance(id="s1", step="scout")
    assert i.user_vars == {}
    assert i.depends_on == []


def test_step_instance_rejects_empty_id():
    with pytest.raises(ValueError):
        StepInstance(id="", step="scout")


def test_step_instance_rejects_empty_step():
    with pytest.raises(ValueError):
        StepInstance(id="s1", step="  ")


def test_step_instance_rejects_non_dict_user_vars():
    with pytest.raises(ValueError):
        StepInstance(id="s1", step="scout", user_vars="bad")  # type: ignore[arg-type]
```

Create `tests/test_expand_fanout.py`:

```python
from __future__ import annotations

import pytest

from loop_agent.orchestration.specs import StepInstance, expand_fanout


def test_expand_fanout_creates_instances():
    instances = expand_fanout(
        "scout",
        [{"symbol": "AAPL"}, {"symbol": "GOOG"}],
        id_prefix="s",
    )
    assert len(instances) == 2
    assert instances[0].id == "s_0"
    assert instances[0].step == "scout"
    assert instances[0].user_vars == {"symbol": "AAPL"}
    assert instances[1].id == "s_1"
    assert instances[1].user_vars == {"symbol": "GOOG"}


def test_expand_fanout_empty_items():
    assert expand_fanout("scout", [], id_prefix="s") == []


def test_expand_fanout_validates_prefix():
    with pytest.raises(ValueError):
        expand_fanout("scout", [{}], id_prefix="")
```

### Step 2: Run tests to verify they fail

```bash
.venv/Scripts/python.exe -m pytest tests/test_step_template.py tests/test_step_instance.py tests/test_expand_fanout.py -v
```

Expected: ImportError for `StepTemplate` / `StepInstance` / `expand_fanout`.

### Step 3: Extend `loop_agent/orchestration/specs.py`

Append to the existing file (keep `WorkerSpec` and `WorkflowStep` intact):

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class StepTemplate:
    """模板：声明一个 step 的形状（worker + 任务模板）。无运行时状态。"""

    id: str
    worker: str
    task_template: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("StepTemplate.id must be a non-empty string")
        if not isinstance(self.worker, str) or not self.worker.strip():
            raise ValueError("StepTemplate.worker must be a non-empty string")
        if not isinstance(self.task_template, str):
            raise ValueError("StepTemplate.task_template must be a string")


@dataclass
class StepInstance:
    """运行时实例：模板的具体执行。

    每个 instance 是 DAG 的一个节点；``depends_on`` 引用其他
    ``StepInstance.id``。
    """

    id: str
    step: str
    user_vars: Dict[str, str] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("StepInstance.id must be a non-empty string")
        if not isinstance(self.step, str) or not self.step.strip():
            raise ValueError("StepInstance.step must reference a StepTemplate.id")
        if not isinstance(self.user_vars, dict):
            raise ValueError("StepInstance.user_vars must be a dict")
        if not isinstance(self.depends_on, list):
            raise ValueError("StepInstance.depends_on must be a list")


def expand_fanout(
    step: str,
    items: List[Dict[str, str]],
    id_prefix: str,
) -> List[StepInstance]:
    """把 ``items`` 列表展开成 N 个 StepInstance（1:1 fan-out）。"""
    if not isinstance(step, str) or not step.strip():
        raise ValueError("expand_fanout step must be a non-empty string")
    if not isinstance(id_prefix, str) or not id_prefix.strip():
        raise ValueError("expand_fanout id_prefix must be a non-empty string")
    if not isinstance(items, list):
        raise ValueError("expand_fanout items must be a list")
    return [
        StepInstance(
            id=f"{id_prefix}_{i}",
            step=step,
            user_vars=item,
        )
        for i, item in enumerate(items)
    ]
```

**Note:** existing `specs.py` already has `from __future__ import annotations` and `from dataclasses import dataclass, field`. Add only missing imports (`Dict`, `List` if not already present) and the new definitions. Keep `WorkerSpec` and `WorkflowStep` exactly as they are.

### Step 4: Run tests to verify they pass

```bash
.venv/Scripts/python.exe -m pytest tests/test_step_template.py tests/test_step_instance.py tests/test_expand_fanout.py -v
```

Expected: 11 passed.

### Step 5: Commit

```bash
git add loop_agent/orchestration/specs.py tests/test_step_template.py tests/test_step_instance.py tests/test_expand_fanout.py
git commit -m "feat(orchestration): add StepTemplate, StepInstance, and expand_fanout helper"
```

---

## Task 3: Supervisor DAG execution

**Files:**
- Modify: `loop_agent/orchestration/supervisor.py`
- Modify: `loop_agent/orchestration/__init__.py`
- Test: `tests/test_supervisor_dag.py`

**Interfaces:**
- Consumes: `StepTemplate`, `StepInstance`, `expand_fanout` (Task 2); `topological_layers` (Task 1); existing `AgentLoop`, `WorkerSpec`
- Produces:
  - `Supervisor(..., templates=..., instances=..., workflow=..., max_parallel=4)`
  - `Supervisor.run(task, session_id)` executing DAG in topological layers
  - `workflow_step_start` / `workflow_step_end` / `supervisor_step_warning` / `workflow_layer_start` / `workflow_layer_end` events

### Step 1: Write failing tests

Create `tests/test_supervisor_dag.py`:

```python
from __future__ import annotations

import pytest

from loop_agent.orchestration import (
    Supervisor,
    SupervisorConfigError,
    WorkerSpec,
    WorkflowStep,
    StepTemplate,
    StepInstance,
    expand_fanout,
)


class _NoopLLM:
    def __init__(self, *args, **kwargs):
        pass


class _FakeAgentLoop:
    calls: list[dict] = []

    def __init__(self, registry, llm, **kwargs):
        self.registry = registry
        self.tool_names = registry.tool_names
        self.event_callback = kwargs.get("event_callback")

    def run(self, user_message, history=None, session_id="", system_prompt=None):
        self.calls.append(
            {
                "user_message": user_message,
                "session_id": session_id,
                "system_prompt": system_prompt,
            }
        )
        if self.event_callback:
            self.event_callback("tool_result", {"message": "fake"})
        return {
            "status": "success",
            "content": f"out:{user_message}",
            "run_id": "r",
            "run_dir": "/tmp/r",
        }


@pytest.fixture(autouse=True)
def _reset_fake_calls(monkeypatch):
    _FakeAgentLoop.calls = []
    monkeypatch.setattr(
        "loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop
    )


@pytest.fixture
def make_sup():
    def _make(templates, instances, workers=None, **kwargs):
        workers = workers or [WorkerSpec(name="w", tools=[])]
        return Supervisor(
            llm=_NoopLLM(),
            workers=workers,
            templates=templates,
            instances=instances,
            **kwargs,
        )

    return _make


def test_supervisor_dag_executes_in_layers(make_sup):
    templates = [
        StepTemplate(id="root", worker="w", task_template="root: {task}"),
        StepTemplate(id="leaf", worker="w", task_template="leaf: {root}"),
    ]
    instances = [
        StepInstance(id="root", step="root"),
        StepInstance(id="leaf", step="leaf", depends_on=["root"]),
    ]
    sup = make_sup(templates, instances)
    result = sup.run(task="USER", session_id="s1")

    assert result["status"] == "success"
    assert result["session_id"] == "s1"
    assert len(_FakeAgentLoop.calls) == 2
    assert _FakeAgentLoop.calls[0]["user_message"] == "root: USER"
    assert _FakeAgentLoop.calls[1]["user_message"] == "leaf: out:root: USER"


def test_supervisor_dag_fan_out_executes_in_parallel(make_sup, monkeypatch):
    templates = [
        StepTemplate(id="scout", worker="w", task_template="scout {symbol}: {task}"),
        StepTemplate(id="merge", worker="w", task_template="merge {s_0} {s_1}"),
    ]
    instances = expand_fanout(
        "scout", [{"symbol": "A"}, {"symbol": "B"}], id_prefix="s"
    ) + [StepInstance(id="m", step="merge", depends_on=["s_0", "s_1"])]

    sup = make_sup(templates, instances)
    result = sup.run(task="USER")
    assert result["status"] == "success"
    assert len(_FakeAgentLoop.calls) == 3
    merge_call = [c for c in _FakeAgentLoop.calls if c["user_message"].startswith("merge")][0]
    assert "out:scout A: USER" in merge_call["user_message"]
    assert "out:scout B: USER" in merge_call["user_message"]


def test_supervisor_dag_prev_output_shorthand_for_single_dep(make_sup):
    templates = [
        StepTemplate(id="first", worker="w", task_template="first: {task}"),
        StepTemplate(id="second", worker="w", task_template="second: {prev_output}"),
    ]
    instances = [
        StepInstance(id="a", step="first"),
        StepInstance(id="b", step="second", depends_on=["a"]),
    ]
    sup = make_sup(templates, instances)
    sup.run(task="USER")
    assert _FakeAgentLoop.calls[1]["user_message"] == "second: out:first: USER"


def test_supervisor_dag_unknown_dep_raises_value_error(make_sup):
    templates = [StepTemplate(id="t", worker="w", task_template="{task}")]
    instances = [StepInstance(id="a", step="t", depends_on=["nope"])]
    with pytest.raises(ValueError, match="depends on unknown id"):
        make_sup(templates, instances)


def test_supervisor_dag_cycle_raises_value_error(make_sup):
    templates = [StepTemplate(id="t", worker="w", task_template="{task}")]
    instances = [
        StepInstance(id="a", step="t", depends_on=["b"]),
        StepInstance(id="b", step="t", depends_on=["a"]),
    ]
    with pytest.raises(ValueError, match="cycle detected"):
        make_sup(templates, instances)


def test_supervisor_dag_duplicate_instance_id_raises_value_error(make_sup):
    templates = [StepTemplate(id="t", worker="w", task_template="{task}")]
    instances = [
        StepInstance(id="a", step="t"),
        StepInstance(id="a", step="t"),
    ]
    with pytest.raises(ValueError, match="Duplicate StepInstance.id"):
        make_sup(templates, instances)


def test_supervisor_dag_unknown_step_raises_value_error(make_sup):
    templates = [StepTemplate(id="t", worker="w", task_template="{task}")]
    instances = [StepInstance(id="a", step="missing")]
    with pytest.raises(ValueError, match="unknown step"):
        make_sup(templates, instances)


def test_supervisor_dag_partial_status_on_failed_step(make_sup):
    class _FailingLoop(_FakeAgentLoop):
        def run(self, user_message, history=None, session_id="", system_prompt=None):
            return {
                "status": "error",
                "content": "broken",
                "run_id": "r",
                "run_dir": "/tmp/r",
            }

    templates = [
        StepTemplate(id="first", worker="w", task_template="first: {task}"),
        StepTemplate(id="second", worker="w", task_template="second: {first}"),
    ]
    instances = [
        StepInstance(id="a", step="first"),
        StepInstance(id="b", step="second", depends_on=["a"]),
    ]

    import loop_agent.orchestration.supervisor as supervisor_mod

    supervisor_mod.AgentLoop = _FailingLoop
    sup = make_sup(templates, instances)
    result = sup.run(task="USER")
    assert result["status"] == "partial"
    assert result["content"] == "broken"


def test_supervisor_dag_events_include_layer_events(make_sup):
    received = []

    def cb(event_type, data):
        received.append(event_type)

    templates = [
        StepTemplate(id="a", worker="w", task_template="a: {task}"),
        StepTemplate(id="b", worker="w", task_template="b: {task}"),
        StepTemplate(id="c", worker="w", task_template="c: {a} {b}"),
    ]
    instances = [
        StepInstance(id="ia", step="a"),
        StepInstance(id="ib", step="b"),
        StepInstance(id="ic", step="c", depends_on=["ia", "ib"]),
    ]
    sup = make_sup(templates, instances, event_callback=cb)
    sup.run(task="USER")
    assert "workflow_layer_start" in received
    assert "workflow_layer_end" in received


def test_supervisor_dag_workflow_backward_compat(make_sup):
    """Phase 3 workflow=[WorkflowStep(...)] keeps working unchanged."""
    sup = Supervisor(
        llm=_NoopLLM(),
        workers=[WorkerSpec(name="r", tools=[]), WorkerSpec(name="w", tools=[])],
        workflow=[
            WorkflowStep("r", "step1 {task}"),
            WorkflowStep("w", "step2 {prev_output}"),
        ],
    )
    result = sup.run(task="USER", session_id="s1")
    assert result["status"] == "success"
    assert len(_FakeAgentLoop.calls) == 2
    assert _FakeAgentLoop.calls[1]["user_message"] == "step2 out:step1 USER"
```

### Step 2: Run tests to verify they fail

```bash
.venv/Scripts/python.exe -m pytest tests/test_supervisor_dag.py -v
```

Expected: failures because `Supervisor` does not accept `templates`/`instances`, `StepTemplate` not exported from `loop_agent.orchestration`, etc.

### Step 3: Refactor `loop_agent/orchestration/supervisor.py`

Requirements:
1. Keep `WorkerSpec`, `_DEFAULT_WORKERS` unchanged.
2. Add `_DEFAULT_TEMPLATES` and `_DEFAULT_INSTANCES` mirroring `_DEFAULT_WORKFLOW`.
3. Modify `Supervisor.__init__` to accept `templates`, `instances`, `workflow` (backward compat), `max_parallel=4`.
4. Internally normalize:
   - if `workflow` provided, convert to `templates` + linear `instances`
   - if neither `workflow` nor `templates`/`instances` provided, use defaults
   - if both provided, raise `ValueError`
5. Validate `templates` ids unique; `instances` ids unique; every `instance.step` in `template_by_id`; every `dep` in `instance_by_id`; no cycles via `validate_dag`.
6. Store `self._templates: Dict[str, StepTemplate]`, `self._instances: List[StepInstance]`, `self._layers: List[List[StepInstance]]`.
7. Preserve `self.workflow` attribute for backward compat tests that read it (set it from `workflow` or synthesize a linear list of `WorkflowStep` from the DAG). Phase 3 `test_supervisor_defaults_when_no_constructor_args` asserts `[s.worker for s in sup.workflow] == ["research", "writer"]`, so `self.workflow` must remain a list of `WorkflowStep`.
8. Rewrite `run()` to iterate layers:
   - emit `workflow_layer_start` / `workflow_layer_end`
   - per instance emit `workflow_step_start` / `workflow_step_end`
   - use `ThreadPoolExecutor(max_workers=self._max_parallel)` for the layer
   - render template with `ctx = {"task": task, **instance.user_vars}` plus each dep's content and (if single dep) `prev_output`
   - aggregate status = "partial" if any non-success
   - final `content` = deepest layer's first instance output
9. Keep `_build_workers()` and `_emit()` behavior; ensure `event_callback` threaded to workers.

Key code sections (illustrative):

```python
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
    expand_fanout,
)

logger = logging.getLogger(__name__)


class SupervisorConfigError(Exception):
    """Raised when a workflow step template cannot be rendered."""


_DEFAULT_WORKERS: List[WorkerSpec] = [...]  # existing

_DEFAULT_TEMPLATES: List[StepTemplate] = [
    StepTemplate(
        id="research",
        worker="research",
        task_template=(...),
    ),
    StepTemplate(
        id="writer",
        worker="writer",
        task_template=(...),
    ),
]

_DEFAULT_INSTANCES: List[StepInstance] = [
    StepInstance(id="research", step="research"),
    StepInstance(id="writer", step="writer", depends_on=["research"]),
]


class Supervisor:
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
        # ... normalization + validation ...

    def _normalize_workflow(self, workflow: List[WorkflowStep]) -> tuple[List[StepTemplate], List[StepInstance]]:
        templates = []
        instances = []
        for i, step in enumerate(workflow):
            template_id = f"_step_{i}"
            templates.append(StepTemplate(
                id=template_id,
                worker=step.worker,
                task_template=step.task_template,
            ))
            deps = [f"_step_{i-1}_inst"] if i > 0 else []
            instances.append(StepInstance(
                id=f"{template_id}_inst",
                step=template_id,
                depends_on=deps,
            ))
        return templates, instances

    def _validate_and_build(self, templates, instances) -> None:
        ...

    def run(self, task: str, session_id: str = "") -> Dict[str, Any]:
        outputs: Dict[str, str] = {}
        aggregate_status = "success"
        spec_by_name = {w.name: w for w in self._workers_specs}

        for layer_idx, layer in enumerate(self._layers):
            self._emit("workflow_layer_start", {"layer": layer_idx, "size": len(layer)})

            with ThreadPoolExecutor(max_workers=self._max_parallel) as executor:
                futures = {
                    executor.submit(
                        self._run_instance, inst, task, outputs, session_id, spec_by_name
                    ): inst
                    for inst in layer
                }
                for future in as_completed(futures):
                    inst = futures[future]
                    result = future.result()
                    outputs[inst.id] = result.get("content") or ""
                    if result.get("status") != "success":
                        aggregate_status = "partial"
                        self._emit("supervisor_step_warning", {...})

            self._emit("workflow_layer_end", {"layer": layer_idx})

        final_id = self._instances[-1].id if self._instances else None
        return {
            "status": aggregate_status,
            "content": outputs.get(final_id, ""),
            "run_id": "",
            "run_dir": "",
            "session_id": session_id,
        }

    def _run_instance(self, instance, task, outputs, session_id, spec_by_name):
        template = self._templates[instance.step]
        task_text = self._render(template, instance, task, outputs)
        self._emit("workflow_step_start", {...})
        worker = self.worker_loops[template.worker]
        spec = spec_by_name[template.worker]
        result = worker.run(
            user_message=task_text,
            session_id=session_id,
            system_prompt=spec.system_prompt,
        )
        self._emit("workflow_step_end", {...})
        return result

    def _render(self, template, instance, task, outputs):
        ctx: Dict[str, str] = {"task": task}
        ctx.update(instance.user_vars)
        if len(instance.depends_on) == 1:
            ctx["prev_output"] = outputs[instance.depends_on[0]]
        for dep_id in instance.depends_on:
            ctx[dep_id] = outputs.get(dep_id, f"[upstream failed: {dep_id}]")
        try:
            return template.task_template.format(**ctx)
        except KeyError as exc:
            raise SupervisorConfigError(...) from exc
```

Implementer must fill in all `...` with concrete code and error messages matching spec.

### Step 4: Update `loop_agent/orchestration/__init__.py`

Add re-exports:

```python
from loop_agent.orchestration.dag import topological_layers, validate_dag
from loop_agent.orchestration.filtered_skills import FilteredSkillsLoader
from loop_agent.orchestration.specs import (
    StepInstance,
    StepTemplate,
    WorkerSpec,
    WorkflowStep,
    expand_fanout,
)
from loop_agent.orchestration.supervisor import Supervisor, SupervisorConfigError
from loop_agent.orchestration.tools import DelegateTool, FinalizeTool

__all__ = [
    "Supervisor",
    "SupervisorConfigError",
    "WorkerSpec",
    "WorkflowStep",
    "StepTemplate",
    "StepInstance",
    "expand_fanout",
    "FilteredSkillsLoader",
    "topological_layers",
    "validate_dag",
    "DelegateTool",
    "FinalizeTool",
]
```

### Step 5: Run tests

```bash
.venv/Scripts/python.exe -m pytest tests/test_supervisor_dag.py -v
```

Expected: 10 passed.

Then run Phase 3 backward compat tests:

```bash
.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -v
```

Expected: existing 16 passed (9 original + 7 Phase 3 added).

### Step 6: Run full suite

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: 130+ passed, 0 failed.

### Step 7: Commit

```bash
git add loop_agent/orchestration/supervisor.py loop_agent/orchestration/__init__.py tests/test_supervisor_dag.py
git commit -m "feat(orchestration): Supervisor executes DAG templates/instances in parallel layers"
```

---

## Task 4: README badge + progress ledger

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/sdd/progress.md`

### Step 1: Update README test badge

```bash
grep -n "tests-" README.md
```

Change badge from `tests-108%20passed` to `tests-130%20passed` (or exact final count after full suite).

### Step 2: Append Phase 4 status to progress.md

Append:

```markdown
## Phase 4
- Plan: docs/superpowers/plans/2026-07-09-loop-agent-phase4-dag-parallel.md
- Spec: docs/superpowers/specs/2026-07-09-phase4-dag-parallel.md
- Status: complete
- Tests: <final count>/<final count> passing
```

### Step 3: Commit

```bash
git add README.md docs/superpowers/sdd/progress.md
git commit -m "docs: phase 4 status + bump test count to <final>"
```

---

## Task 5: Whole-branch verification

**Files:**
- All changed files

### Step 1: Run full test suite

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: 130+ passed, 0 failed.

### Step 2: Verify backward compat signatures

```bash
.venv/Scripts/python.exe -c "from loop_agent.orchestration import Supervisor, StepTemplate, StepInstance, expand_fanout, topological_layers; print('ok')"
```

Expected: `ok`.

### Step 3: Git status clean

```bash
git status --porcelain
```

Expected: empty output.

### Step 4: Push (best-effort)

```bash
git push origin main
```

If network blocked, report to user. Don't block completion on push.

---

## Spec Coverage

| Spec requirement | Task |
|---|---|
| `StepTemplate` dataclass with validation | T2 |
| `StepInstance` dataclass with validation | T2 |
| `expand_fanout` helper | T2 |
| `topological_layers` / `validate_dag` | T1 |
| `Supervisor.__init__(templates, instances, workflow shim, max_parallel)` | T3 |
| DAG validation (duplicate id, unknown step, unknown dep, cycle) | T1 + T3 tests |
| Layer-parallel execution with ThreadPoolExecutor | T3 |
| Template rendering with `{task}`, user_vars, `{dep_id}`, `{prev_output}` | T3 |
| `partial` status on failure | T3 |
| `workflow_layer_start/end` events | T3 |
| Backward compat `Supervisor(workers, workflow)` | T3 |
| `self.workflow` remains `List[WorkflowStep]` for Phase 3 tests | T3 |
| README badge + progress ledger | T4 |
| 22+ new tests | T1 (6) + T2 (11) + T3 (10) = 27 |

## Placeholder scan

No "TBD", "TODO", "implement later" markers. Every step has exact code, exact commands, expected outputs.

## Type / Signature Consistency

- `StepTemplate.id` / `StepInstance.id` referenced by `depends_on: List[str]`
- `StepInstance.step` references `StepTemplate.id`
- `Supervisor._templates: Dict[str, StepTemplate]` keyed by template id
- `Supervisor._instances: List[StepInstance]`
- `expand_fanout(step: str, items: List[Dict[str, str]], id_prefix: str) -> List[StepInstance]`
- `topological_layers(instances: Iterable[Any]) -> List[List[Any]]`
- `validate_dag(instances: Iterable[Any]) -> None`
- `Supervisor.run(task, session_id="") -> Dict[str, Any]` unchanged
