import json

from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import BaseTool


class LoadSkillTool(BaseTool):
    name = "load_skill"
    description = "Load full documentation for a named skill."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name"},
        },
        "required": ["name"],
    }
    repeatable = True

    def __init__(self, skills_loader: SkillsLoader | None = None) -> None:
        self._loader = skills_loader or SkillsLoader()

    def execute(self, *, name: str) -> str:
        content = self._loader.get_content(name)
        return json.dumps({"status": "ok", "content": content}, ensure_ascii=False)
