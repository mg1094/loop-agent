import json
from unittest.mock import MagicMock

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import BaseTool, ToolRegistry
from loop_agent.providers.chat import ChatLLM, LLMResponse, ToolCallRequest


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo"
    parameters = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    def execute(self, *, message: str) -> str:
        return json.dumps({"result": message})


def test_loop_runs_tool_then_finishes(tmp_path):
    registry = ToolRegistry()
    registry.register(EchoTool())
    memory = WorkspaceMemory()

    llm = MagicMock(spec=ChatLLM)
    llm.chat.side_effect = [
        LLMResponse(
            tool_calls=[ToolCallRequest(id="1", name="echo", arguments={"message": "hello"})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="Done", finish_reason="stop"),
    ]

    loop = AgentLoop(registry, llm, memory, max_iterations=5)
    result = loop.run("say hello")

    assert result["status"] == "success"
    assert result["content"] == "Done"
    assert llm.chat.call_count == 2
