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
