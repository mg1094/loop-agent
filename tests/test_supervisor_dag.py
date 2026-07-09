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
        StepTemplate(id="second", worker="w", task_template="second: {a}"),
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
        StepTemplate(id="c", worker="w", task_template="c: {ia} {ib}"),
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


def test_supervisor_dag_step_event_payload_shape(make_sup):
    """DAG-mode workflow_step_start/end carry instance_id and string step."""
    received = []

    def cb(event_type, data):
        received.append((event_type, data))

    templates = [
        StepTemplate(id="root", worker="w", task_template="root: {task}"),
    ]
    instances = [StepInstance(id="root_1", step="root")]
    sup = make_sup(templates, instances, event_callback=cb)
    sup.run(task="USER")

    step_events = [d for t, d in received if t in ("workflow_step_start", "workflow_step_end")]
    assert len(step_events) == 2
    for payload in step_events:
        assert payload["instance_id"] == "root_1"
        assert payload["step"] == "root"
        assert payload["worker"] == "w"


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


def test_supervisor_dag_ambiguous_final_raises_at_construction(make_sup):
    """Fan-out without fan-in: deepest layer has >1 instance; construction fails.

    Regression test for the silent bug where ``Supervisor.run()`` used to
    return ``_layers[-1][0].content`` arbitrarily when the deepest layer
    had multiple competing sinks. We now refuse to build the Supervisor.
    """
    templates = [
        StepTemplate(id="scout", worker="w", task_template="scout {task}"),
    ]
    instances = expand_fanout(
        "scout",
        [{"x": "A"}, {"x": "B"}, {"x": "C"}],
        id_prefix="s",
    )
    with pytest.raises(ValueError, match="competing sinks"):
        make_sup(templates, instances)


def test_supervisor_dag_final_instance_id_selects_explicit_sink(make_sup):
    """Passing final_instance_id lets a fan-out DAG converge to one sink.

    The Supervisor should run normally; ``result['content']`` must come
    from the instance named in ``final_instance_id``.
    """
    templates = [
        StepTemplate(id="scout", worker="w", task_template="scout {x}: {task}"),
    ]
    instances = expand_fanout(
        "scout",
        [{"x": "A"}, {"x": "B"}, {"x": "C"}],
        id_prefix="s",
    )
    sup = make_sup(templates, instances, final_instance_id="s_1")
    result = sup.run(task="USER")
    assert result["status"] == "success"
    assert len(_FakeAgentLoop.calls) == 3
    # The fake echoes ``user_message`` into ``out:<user_message>``; the
    # final content must be the second scout instance's output (s_1).
    assert "out:scout B: USER" == result["content"]


def test_supervisor_dag_final_instance_id_not_a_sink_raises(make_sup):
    """final_instance_id pointing at an intermediate node is a config error."""
    templates = [
        StepTemplate(id="root", worker="w", task_template="root: {task}"),
        StepTemplate(id="leaf", worker="w", task_template="leaf: {root}"),
    ]
    instances = [
        StepInstance(id="root_1", step="root"),
        StepInstance(id="leaf_1", step="leaf", depends_on=["root_1"]),
    ]
    # ``root_1`` is in layer 0, not the deepest layer.
    with pytest.raises(ValueError, match="must be the id of an instance in the deepest topological layer"):
        make_sup(templates, instances, final_instance_id="root_1")


def test_supervisor_dag_final_instance_id_unknown_raises(make_sup):
    """final_instance_id pointing at a non-existent id is rejected."""
    templates = [
        StepTemplate(id="root", worker="w", task_template="root: {task}"),
    ]
    instances = [StepInstance(id="root_1", step="root")]
    with pytest.raises(ValueError, match="must be the id of an instance"):
        make_sup(templates, instances, final_instance_id="does_not_exist")

