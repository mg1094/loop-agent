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
