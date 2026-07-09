"""Configuration dataclasses for the configurable Supervisor.

These types are the *only* public contract for building custom workflows.
Adding fields is non-breaking; renaming or removing fields is breaking and
requires a new spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
