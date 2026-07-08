from __future__ import annotations

import pytest

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import ToolRegistry


class _FakeLLM:
    def chat(self, messages, tools=None):
        class _Resp:
            has_tool_calls = False
            content = "ok"
            tool_calls = []

        return _Resp()


@pytest.fixture
def capture_context_builder(monkeypatch):
    """Replace ContextBuilder with a recorder; return the captured loader."""
    captured = {}

    class _CapturedCB:
        def __init__(self, registry, memory, skills_loader=None):
            captured["loader"] = skills_loader
            self.registry = registry
            self.memory = memory
            self.skills_loader = skills_loader or SkillsLoader()

        def build_messages(self, user_message, history=None):
            return [{"role": "user", "content": user_message}]

        def format_assistant_tool_calls(self, tool_calls, content=None):
            return {"role": "assistant", "content": ""}

        def format_tool_result(self, call_id, name, result):
            return {"role": "tool", "content": ""}

    monkeypatch.setattr(
        "loop_agent.agent.loop.ContextBuilder",
        lambda registry, memory, skills_loader=None: _CapturedCB(registry, memory, skills_loader),
    )
    return captured


def test_agent_loop_default_skills_loader_unchanged(capture_context_builder):
    AgentLoop(ToolRegistry(), _FakeLLM(), WorkspaceMemory()).run("hi")
    assert isinstance(capture_context_builder["loader"], SkillsLoader)


def test_agent_loop_threads_custom_skills_loader_to_context_builder(capture_context_builder):
    custom = SkillsLoader.__new__(SkillsLoader)
    custom.skills = []
    custom.skills_dir = None
    custom._user_skills_dir = None
    AgentLoop(ToolRegistry(), _FakeLLM(), WorkspaceMemory(), skills_loader=custom).run("hi")
    assert capture_context_builder["loader"] is custom
