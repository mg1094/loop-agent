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

    The fake also threads ``event_callback`` through ``__init__`` (matching
    the real ``AgentLoop`` signature) and emits a synthetic worker event from
    inside ``run()`` so tests can verify the Supervisor hands the callback
    down to workers end-to-end.
    """

    calls: list = []

    def __init__(self, registry, llm, **kwargs):
        self.registry = registry
        self.tool_names = registry.tool_names
        self.kwargs = kwargs
        self.event_callback = kwargs.get("event_callback")

    def run(self, user_message, history=None, session_id="", system_prompt=None):
        type(self).calls.append({
            "user_message": user_message,
            "session_id": session_id,
            "system_prompt": system_prompt,
        })
        # Simulate the real AgentLoop emitting a worker-side event so callers
        # can verify the Supervisor threads ``event_callback`` down.
        if self.event_callback is not None:
            self.event_callback(
                "tool_result",
                {"name": "fake_tool", "result": "fake_output"},
            )
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
    # Workflow mode uses integer step indices and no instance_id.
    for event_type, payload in workflow_events:
        assert "instance_id" not in payload
        assert isinstance(payload["step"], int)
        assert payload["worker"] == "r"
    assert sorted(d["step"] for _, d in workflow_events) == [0, 0, 1, 1]
    # The fake worker also emits a "tool_result" event from inside run(),
    # proving the Supervisor actually threaded event_callback down to the
    # worker AgentLoop (not just declared the kwarg).
    worker_events = [r for r in received if r[0] == "tool_result"]
    assert len(worker_events) == 2  # one per workflow step


def test_supervisor_defaults_construct_without_bocha_api_key(monkeypatch):
    """C2 regression: default Supervisor() must not raise when BOCHA_API_KEY is unset.

    The historical ``_build_worker_registry`` silently skipped tools that
    weren't available in the current environment. The brief's strict
    ``ValueError`` regressed that behavior, breaking ``run-supervised`` on
    any checkout without a BOCHA subscription. The current contract is
    silent-skip with a debug log so the Supervisor continues to build with
    whatever tools ARE available.
    """
    monkeypatch.delenv("BOCHA_API_KEY", raising=False)
    _FakeAgentLoop.calls = []
    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", _FakeAgentLoop)
    # Must not raise.
    sup = Supervisor(llm=_NoopLLM())
    # research worker should exist; ``web_search`` is silently skipped.
    assert "research" in sup.worker_loops
    # writer worker depends only on built-in tools and is unaffected.
    assert "writer" in sup.worker_loops


def test_supervisor_load_skill_tool_honors_worker_skills_allow_list(monkeypatch):
    """End-to-end: a worker with skills=['public'] cannot load 'sensitive'.

    Regression for C1: the per-worker FilteredSkillsLoader must be threaded
    into LoadSkillTool, not just ContextBuilder. Without that wiring the
    LoadSkillTool falls back to a default SkillsLoader and bypasses the
    allow-list entirely.
    """
    from loop_agent.agent.skills import Skill, SkillsLoader

    # Force every SkillsLoader() construction to return a known snapshot
    # with two skills so we can assert which one is reachable.
    def _patched_loader(*args, **kwargs):
        loader = SkillsLoader.__new__(SkillsLoader)
        loader.skills = [
            Skill(name="public", description="p", body="public body"),
            Skill(name="sensitive", description="s", body="SENSITIVE_BODY"),
        ]
        loader.skills_dir = None
        loader._user_skills_dir = None
        return loader

    monkeypatch.setattr(
        "loop_agent.orchestration.supervisor.SkillsLoader", _patched_loader
    )
    monkeypatch.setattr(
        "loop_agent.orchestration.filtered_skills.SkillsLoader", _patched_loader
    )

    workers = [
        WorkerSpec(name="r", tools=["load_skill", "echo"], skills=["public"]),
    ]
    steps = [WorkflowStep("r", "{task}")]
    sup = Supervisor(llm=_NoopLLM(), workers=workers, workflow=steps)

    # The LoadSkillTool inside the worker must point at a FilteredSkillsLoader
    # that has been narrowed to the allow-list.
    worker = sup.worker_loops["r"]
    tool = worker.registry.get("load_skill")
    assert tool is not None
    from loop_agent.orchestration.filtered_skills import FilteredSkillsLoader

    assert isinstance(tool._loader, FilteredSkillsLoader)
    assert {s.name for s in tool._loader.skills} == {"public"}

    # Calling load_skill on a name outside the allow-list surfaces as an
    # error tool result via the registry's exception wrapper.
    import json as _json

    result = _json.loads(worker.registry.execute("load_skill", {"name": "sensitive"}))
    assert result["status"] == "error"
    assert result["tool"] == "load_skill"
    assert "sensitive" in result["error"]
    assert "not available" in result["error"]

    # An allowed name still works.
    result_ok = _json.loads(worker.registry.execute("load_skill", {"name": "public"}))
    assert result_ok["status"] == "ok"
    assert "public body" in result_ok["content"]
