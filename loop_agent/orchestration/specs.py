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