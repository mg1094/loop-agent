import json

from loop_agent.orchestration.tools import DelegateTool, FinalizeTool


def test_delegate_tool_calls_dispatcher():
    calls = []

    def dispatcher(task, worker):
        calls.append((task, worker))
        return f"done: {worker}"

    tool = DelegateTool(dispatcher)
    result = tool.execute(task="search X", to="research")
    payload = json.loads(result)
    assert payload == {"worker": "research", "output": "done: research"}
    assert calls == [("search X", "research")]


def test_delegate_tool_rejects_unknown_worker():
    tool = DelegateTool(lambda t, w: "")
    result = tool.execute(task="x", to="hacker")
    payload = json.loads(result)
    assert payload["worker"] == "hacker"


def test_finalize_tool_calls_callback():
    captured = []
    tool = FinalizeTool(lambda report: captured.append(report))
    result = tool.execute(report="final answer")
    assert json.loads(result) == {"status": "finalized"}
    assert captured == ["final answer"]


from loop_agent.agent.loop import AgentLoop  # noqa: E402
from loop_agent.agent.memory import WorkspaceMemory  # noqa: E402
from loop_agent.agent.tools import ToolRegistry  # noqa: E402


def test_agent_loop_accepts_custom_system_prompt(monkeypatch):
    class FakeLLM:
        def chat(self, messages, tools=None):
            class Resp:
                has_tool_calls = False
                content = "ok"
                tool_calls = []
            return Resp()

    registry = ToolRegistry()
    loop = AgentLoop(registry, FakeLLM(), WorkspaceMemory())
    result = loop.run(
        "hi",
        system_prompt="You are a coordinator. Use delegate and finalize.",
    )
    assert result["status"] == "success"
    assert result["content"] == "ok"


from loop_agent.orchestration.supervisor import Supervisor  # noqa: E402


class _NoopLLM:
    def __init__(self, *args, **kwargs):
        pass


def test_supervisor_builds_worker_registries_with_allowed_tools_only(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    supervisor = Supervisor(llm=_NoopLLM())
    research_tools = supervisor.worker_loops["research"].registry.tool_names
    writer_tools = supervisor.worker_loops["writer"].registry.tool_names
    assert research_tools == ["web_search"]
    assert set(writer_tools) == {"read_file", "write_file", "echo"}


def test_supervisor_run_delegates_research_then_writer(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    research_calls = []
    writer_calls = []

    class FakeAgentLoop:
        def __init__(self, registry, llm, **kwargs):
            self.registry = registry
            self.tool_names = registry.tool_names

        def run(self, user_message, history=None, session_id="", system_prompt=None):
            if "web_search" in self.tool_names:
                research_calls.append({"user_message": user_message, "session_id": session_id})
                return {"status": "success", "content": "research summary", "run_id": "r1", "run_dir": "/tmp/r1"}
            if "write_file" in self.tool_names:
                writer_calls.append({"user_message": user_message, "session_id": session_id})
                return {"status": "success", "content": "writer report", "run_id": "w1", "run_dir": "/tmp/w1"}
            raise RuntimeError("unknown worker")

    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", FakeAgentLoop)

    supervisor = Supervisor(llm=_NoopLLM())
    result = supervisor.run("report on X", session_id="sess-1")

    # New design returns the writer's content directly as the final report.
    assert result["status"] == "success"
    assert result["content"] == "writer report"
    assert result["session_id"] == "sess-1"
    # Each worker ran exactly once, with the threaded session_id.
    assert len(research_calls) == 1
    assert len(writer_calls) == 1
    assert research_calls[0]["session_id"] == "sess-1"
    assert writer_calls[0]["session_id"] == "sess-1"
    # The writer's task text contains the researcher's output (template substitution).
    assert "research summary" in writer_calls[0]["user_message"]


from loop_agent.cli import commands  # noqa: E402


def test_run_supervised_command(monkeypatch):
    def fake_run(task, session_id=""):
        return {
            "status": "success",
            "content": f"report: {task}",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
            "session_id": session_id,
        }

    monkeypatch.setattr(
        "loop_agent.cli.commands._run_supervised", fake_run
    )
    result = commands.run_supervised_command("topic X", session_id="s1")
    assert result["content"] == "report: topic X"
    assert result["session_id"] == "s1"


from fastapi.testclient import TestClient  # noqa: E402
from loop_agent.api.app import create_app  # noqa: E402


def test_chat_supervised_endpoint(monkeypatch):
    def fake_run(task, session_id=""):
        return {
            "status": "success",
            "content": f"supervised: {task}",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
        }

    monkeypatch.setattr("loop_agent.api.routes._run_supervised", fake_run)
    client = TestClient(create_app())
    resp = client.post(
        "/chat/supervised",
        json={"prompt": "report on X", "session_id": "s1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "supervised: report on X"
    assert body["session_id"] == "s1"


def test_chat_supervised_blank_prompt_returns_400(monkeypatch):
    called = []

    def fake_run(task, session_id=""):
        called.append(task)
        return {
            "status": "success",
            "content": "",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
        }

    monkeypatch.setattr("loop_agent.api.routes._run_supervised", fake_run)
    client = TestClient(create_app())
    resp = client.post("/chat/supervised", json={"prompt": "   "})
    assert resp.status_code == 400
    assert called == []


import pytest  # noqa: E402

from loop_agent.agent.tools import ToolRegistry  # noqa: E402
from loop_agent.orchestration.filtered_skills import FilteredSkillsLoader  # noqa: E402
from loop_agent.orchestration.specs import WorkerSpec, WorkflowStep  # noqa: E402
from loop_agent.orchestration.supervisor import Supervisor, SupervisorConfigError  # noqa: E402
from loop_agent.providers.chat import ChatLLM  # noqa: E402


class _NoopLLM:
    def chat(self, messages, tools=None):
        class _R:
            has_tool_calls = False
            content = "ok"
            tool_calls = []

        return _R()


class _FakeAgentLoop:
    """Stand-in for ``AgentLoop`` constructor; records all ``run`` invocations.

    ``calls`` is a list of dicts (one per ``run`` call), so tests can assert the
    Nth call's arguments rather than only whatever call happened last.
    Each test that monkeypatches this class MUST reset ``_FakeAgentLoop.calls = []``
    at the start so test ordering does not leak state.
    """

    calls: list = []

    def __init__(self, registry, llm, **kwargs):
        self.registry = registry
        self.tool_names = registry.tool_names
        self.kwargs = kwargs

    def run(self, user_message, history=None, session_id="", system_prompt=None):
        type(self).calls.append({
            "user_message": user_message,
            "session_id": session_id,
            "system_prompt": system_prompt,
        })
        return {
            "status": "success",
            "content": f"out:{user_message[:30]}",
            "run_id": "fake",
            "run_dir": "/tmp/fake",
        }


def test_supervisor_defaults_when_no_constructor_args(monkeypatch):
    # web_search requires BOCHA_API_KEY to be available in build_registry();
    # the Supervisor's defaults include web_search for the "research" worker.
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    _FakeAgentLoop.calls = []
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop)
    sup = Supervisor(llm=_NoopLLM())
    assert set(sup.worker_loops.keys()) == {"research", "writer"}
    assert [s.worker for s in sup.workflow] == ["research", "writer"]


def test_supervisor_renders_workflow_template_with_task_and_prev_output(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    _FakeAgentLoop.calls = []
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

    # The helper records every run() invocation in order.
    assert len(_FakeAgentLoop.calls) == 2
    # First call: prev_output is empty string.
    assert _FakeAgentLoop.calls[0]["user_message"] == "step1 task=USER prev="
    # Second call: prev_output echoes the first step's content.
    assert "step2 task=USER prev=out:step1 task=USER prev=" in _FakeAgentLoop.calls[1]["user_message"]


def test_supervisor_passes_per_worker_system_prompt(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    _FakeAgentLoop.calls = []
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop)
    workers = [
        WorkerSpec(name="r", tools=[], system_prompt="you are a researcher"),
    ]
    steps = [WorkflowStep("r", "do {task}")]
    sup = Supervisor(llm=_NoopLLM(), workers=workers, workflow=steps)
    sup.run(task="X", session_id="")
    assert _FakeAgentLoop.calls[0]["system_prompt"] == "you are a researcher"


class _FailingAgentLoop(_FakeAgentLoop):
    def run(self, user_message, history=None, session_id="", system_prompt=None):
        # Do NOT append to _FakeAgentLoop.calls — the base class would, but
        # the override here is total; it only returns an error payload.
        return {
            "status": "error",
            "content": "broken",
            "run_id": "fake",
            "run_dir": "/tmp/fake",
        }


def test_supervisor_partial_status_when_worker_fails(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    _FakeAgentLoop.calls = []
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
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    _FakeAgentLoop.calls = []
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop)
    workers = [WorkerSpec(name="r", tools=[])]
    steps = [WorkflowStep("r", "{task} {bogus}")]
    sup = Supervisor(llm=_NoopLLM(), workers=workers, workflow=steps)
    with pytest.raises(SupervisorConfigError):
        sup.run(task="X", session_id="")


def test_supervisor_event_callback_receives_workflow_events(monkeypatch):
    """Verify event_callback is threaded into worker AgentLoops AND used by Supervisor._emit."""
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    _FakeAgentLoop.calls = []
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop)
    workers = [WorkerSpec(name="r", tools=[])]
    steps = [
        WorkflowStep("r", "step1 {task}"),
        WorkflowStep("r", "step2 {prev_output}"),
    ]
    received: list[tuple[str, dict]] = []

    def cb(event_type, data):
        received.append((event_type, data))

    sup = Supervisor(llm=_NoopLLM(), workers=workers, workflow=steps, event_callback=cb)
    sup.run(task="hi", session_id="")
    types = {t for t, _ in received}
    assert {"workflow_step_start", "workflow_step_end"}.issubset(types)
    # Two start + two end events = four workflow events total.
    workflow_events = [r for r in received if r[0].startswith("workflow_")]
    assert len(workflow_events) == 4