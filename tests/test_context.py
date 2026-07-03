from pathlib import Path

from loop_agent.agent.context import ContextBuilder
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import BaseTool, ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo the input."
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
        },
        "required": ["message"],
    }

    def execute(self, *, message: str) -> str:
        return message


def test_system_prompt_contains_tools_and_skills(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(EchoTool())
    memory = WorkspaceMemory()
    skills_loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    builder = ContextBuilder(registry, memory, skills_loader)
    prompt = builder.build_system_prompt()
    assert "echo" in prompt
    assert "Echo the input" in prompt


def test_build_messages(tmp_path: Path):
    registry = ToolRegistry()
    memory = WorkspaceMemory()
    skills_loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    builder = ContextBuilder(registry, memory, skills_loader)
    messages = builder.build_messages("hello")
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "hello" in messages[-1]["content"]
