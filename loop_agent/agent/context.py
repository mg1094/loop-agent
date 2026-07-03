from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import ToolRegistry

if TYPE_CHECKING:
    pass

_SYSTEM_PROMPT = """You are a helpful research assistant.

You have access to {tool_count} tools and {skill_count} skills.

## Tools

{tool_descriptions}

## Skills

Use `load_skill(name)` to read full documentation before starting a complex task.

{skill_descriptions}

## Current State

{memory_summary}

## Guidelines

- Load the relevant skill first when starting a new type of task.
- Ask the user if critical info is missing.
- Respond in the same language the user used.
- Today is {current_datetime}.
"""


class ContextBuilder:
    def __init__(
        self,
        registry: ToolRegistry,
        memory: WorkspaceMemory,
        skills_loader: Optional[SkillsLoader] = None,
    ) -> None:
        self.registry = registry
        self.memory = memory
        self.skills_loader = skills_loader or SkillsLoader()

    def build_system_prompt(self, user_message: str = "") -> str:
        now = datetime.now()
        return _SYSTEM_PROMPT.format(
            tool_count=len(self.registry),
            skill_count=len(self.skills_loader.skills),
            tool_descriptions=self._format_tool_descriptions(),
            skill_descriptions=self.skills_loader.get_descriptions(),
            memory_summary=self.memory.to_summary(),
            current_datetime=now.strftime("%A, %B %d, %Y %H:%M (local)"),
        )

    def _format_tool_descriptions(self) -> str:
        lines = []
        for tool in self.registry._tools.values():
            params = tool.parameters.get("properties", {})
            required = tool.parameters.get("required", [])
            param_parts = []
            for pname, pschema in params.items():
                req = " (required)" if pname in required else ""
                param_parts.append(
                    f"    - {pname}: {pschema.get('description', pschema.get('type', ''))}{req}"
                )
            param_text = "\n".join(param_parts) if param_parts else "    (no params)"
            lines.append(f"### {tool.name}\n{tool.description}\n  Params:\n{param_text}")
        return "\n\n".join(lines)

    def build_messages(
        self,
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.build_system_prompt(user_message)},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    @staticmethod
    def format_tool_result(tool_call_id: str, tool_name: str, result: str) -> Dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        }

    @staticmethod
    def format_assistant_tool_calls(
        tool_calls: list,
        content: Optional[str] = None,
    ) -> Dict[str, Any]:
        formatted = []
        for tc in tool_calls:
            formatted.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            })
        msg: Dict[str, Any] = {"role": "assistant", "content": content or ""}
        if formatted:
            msg["tool_calls"] = formatted
        return msg
