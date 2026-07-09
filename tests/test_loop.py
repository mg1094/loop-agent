import json
from pathlib import Path
from unittest.mock import MagicMock

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import BaseTool, ToolRegistry
from loop_agent.providers.chat import ChatLLM, LLMResponse, ToolCallRequest
from loop_agent.storage.session_store import SessionStore


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


class GreeterTool(BaseTool):
    name = "greet"
    description = "Greet"
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    def execute(self, *, name: str) -> str:
        return json.dumps({"result": f"hello {name}"})


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


def test_loop_persists_messages_when_session_store_provided(tmp_path: Path):
    registry = ToolRegistry()
    memory = WorkspaceMemory()
    store = SessionStore(tmp_path / "sessions.db")

    llm = MagicMock(spec=ChatLLM)
    llm.chat.side_effect = [
        LLMResponse(content="first reply", finish_reason="stop"),
        LLMResponse(content="second reply", finish_reason="stop"),
    ]

    loop = AgentLoop(registry, llm, memory, session_store=store)
    r1 = loop.run("first prompt", session_id="sess1")
    assert r1["status"] == "success"

    r2 = loop.run("second prompt", session_id="sess1")
    assert r2["status"] == "success"

    # store should contain both user messages and both assistant replies
    loaded = store.load_messages("sess1")
    assert [m["content"] for m in loaded if m["role"] == "user"] == [
        "first prompt", "second prompt"
    ]
    assert [m["content"] for m in loaded if m["role"] == "assistant"] == [
        "first reply", "second reply"
    ]


def test_loop_handles_manual_compact_tool_call():
    registry = ToolRegistry()
    memory = WorkspaceMemory()

    llm = MagicMock(spec=ChatLLM)
    llm.chat.side_effect = [
        LLMResponse(
            tool_calls=[
                ToolCallRequest(
                    id="compact-1",
                    name="compact",
                    arguments={"focus_topic": "important topic"},
                )
            ],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="handoff summary", finish_reason="stop"),
        LLMResponse(content="Done after compact", finish_reason="stop"),
    ]

    loop = AgentLoop(registry, llm, memory, max_iterations=5)
    result = loop.run("keep going")

    assert result["status"] == "success"
    assert result["content"] == "Done after compact"
    assert llm.chat.call_count == 3
    summary_prompt = llm.chat.call_args_list[1].args[0][0]["content"]
    assert "FOCUS TOPIC: important topic" in summary_prompt
