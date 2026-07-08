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
