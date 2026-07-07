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