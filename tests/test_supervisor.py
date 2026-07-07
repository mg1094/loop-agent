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
    research_tools = supervisor.workers["research"].registry.tool_names
    writer_tools = supervisor.workers["writer"].registry.tool_names
    assert research_tools == ["web_search"]
    assert set(writer_tools) == {"read_file", "write_file", "echo"}


def test_supervisor_run_delegates_research_then_writer(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    research_tasks = []
    writer_tasks = []

    class FakeAgentLoop:
        def __init__(self, registry, llm, **kwargs):
            self.registry = registry

        def run(self, user_message, history=None, session_id="", system_prompt=None):
            names = set(self.registry.tool_names)
            if "delegate" in names:
                delegate = self.registry.get("delegate")
                finalize = self.registry.get("finalize")
                research_out = delegate.execute(task=user_message, to="research")
                writer_out = delegate.execute(
                    task=f"write report using {research_out}", to="writer"
                )
                finalize.execute(report=f"REPORT: {writer_out}")
                return {
                    "status": "success",
                    "content": "coordinator done",
                    "run_id": "c1",
                    "run_dir": "/tmp/c1",
                }
            if "web_search" in names:
                research_tasks.append(user_message)
                return {"status": "success", "content": "research summary", "run_id": "r1", "run_dir": "/tmp/r1"}
            if "write_file" in names:
                writer_tasks.append(user_message)
                return {"status": "success", "content": "writer report", "run_id": "w1", "run_dir": "/tmp/w1"}
            raise RuntimeError("unknown worker")

    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", FakeAgentLoop)

    supervisor = Supervisor(llm=_NoopLLM())
    result = supervisor.run("report on X", session_id="sess-1")

    assert result["status"] == "success"
    assert result["content"] == 'REPORT: {"worker": "writer", "output": "writer report"}'
    assert result["session_id"] == "sess-1"
    assert len(research_tasks) == 1
    assert len(writer_tasks) == 1


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