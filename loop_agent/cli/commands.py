from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.providers.chat import ChatLLM
from loop_agent.tools import build_registry


def _load_env() -> None:
    for candidate in [
        Path.home() / ".loop-agent" / ".env",
        Path.cwd() / ".env",
    ]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break


def _run_agent(user_message: str) -> Dict[str, Any]:
    _load_env()
    skills_loader = SkillsLoader()
    registry = build_registry(skills_loader=skills_loader)
    llm = ChatLLM()
    memory = WorkspaceMemory()
    loop = AgentLoop(registry, llm, memory)
    return loop.run(user_message)


def run_command(user_message: str) -> Dict[str, Any]:
    return _run_agent(user_message)


def list_skills() -> str:
    _load_env()
    loader = SkillsLoader()
    return loader.get_descriptions()


def list_tool_names() -> List[str]:
    _load_env()
    registry = build_registry()
    return sorted(registry.tool_names)


def list_tools() -> str:
    return "\n".join(list_tool_names())