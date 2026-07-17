import json
from pathlib import Path

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import BaseTool, ToolRegistry


class _BoomTool(BaseTool):
    name = "boom"
    description = "Always fails."
    parameters = {"type": "object", "properties": {}}

    def execute(self, **kwargs):
        raise RuntimeError("intentional failure")


def test_tool_registry_execute_calls_on_error():
    seen = []
    registry = ToolRegistry()
    registry.register(_BoomTool())

    result = registry.execute(
        "boom",
        {},
        on_error=lambda exc_type, exc_msg: seen.append((exc_type, exc_msg)),
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert seen == [("RuntimeError", "intentional failure")]


def test_agent_loop_writes_tool_error_to_trace(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(_BoomTool())

    class FakeLLM:
        _calls = 0

        def chat(self, messages, tools=None):
            FakeLLM._calls += 1
            if FakeLLM._calls == 1:
                class Resp:
                    has_tool_calls = True
                    content = ""
                    tool_calls = [
                        type("TC", (), {"id": "tc-1", "name": "boom", "arguments": {}})
                    ]
                return Resp()
            class Resp:
                has_tool_calls = False
                content = "done"
                tool_calls = []
            return Resp()

    loop = AgentLoop(registry, FakeLLM(), WorkspaceMemory())
    result = loop.run("trigger boom")
    assert result["status"] == "success"
    assert result["content"] == "done"

    run_dir = Path(result["run_dir"])
    trace_file = run_dir / "trace.jsonl"
    lines = trace_file.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines if line.strip()]

    error_events = [e for e in events if e.get("type") == "tool_error"]
    assert len(error_events) == 1
    assert error_events[0]["name"] == "boom"
    assert error_events[0]["exception_type"] == "RuntimeError"
    assert "intentional failure" in error_events[0]["error"]

    # tool_result still follows so the agent sees the JSON error payload
    result_events = [e for e in events if e.get("type") == "tool_result"]
    assert len(result_events) == 1
    assert json.loads(result_events[0]["content"])["status"] == "error"


def test_missing_tool_also_calls_on_error():
    seen = []
    registry = ToolRegistry()
    result = registry.execute(
        "nonexistent",
        {},
        on_error=lambda exc_type, exc_msg: seen.append((exc_type, exc_msg)),
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert seen == [("ToolNotFoundError", "Tool 'nonexistent' not found")]
