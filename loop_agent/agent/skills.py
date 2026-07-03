from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loop_agent.agent.frontmatter import parse_frontmatter


USER_SKILLS_DIR = Path.home() / ".loop-agent" / "skills" / "user"


@dataclass
class Skill:
    name: str
    description: str = ""
    category: str = "other"
    body: str = ""
    dir_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def load_support_file(self, filename: str) -> Optional[str]:
        if not self.dir_path:
            return None
        path = self.dir_path / filename
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None


def _load_skill_dir(dir_path: Path) -> Optional[Skill]:
    skill_file = dir_path / "SKILL.md"
    if not skill_file.exists():
        return None
    try:
        text = skill_file.read_text(encoding="utf-8")
    except Exception:
        return None

    meta, body = parse_frontmatter(text)
    name = meta.get("name", dir_path.name)
    if not name:
        return None

    return Skill(
        name=name,
        description=meta.get("description", ""),
        category=meta.get("category", "other"),
        body=body,
        dir_path=dir_path,
        metadata=meta,
    )


class SkillsLoader:
    _CATEGORY_ORDER = [
        "writing", "coding", "research", "analysis", "tool", "other"
    ]

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        user_skills_dir: Optional[Path] = None,
    ) -> None:
        self.skills_dir = skills_dir or Path(__file__).resolve().parents[1] / "skills"
        self._user_skills_dir = user_skills_dir or USER_SKILLS_DIR
        self.skills: List[Skill] = []
        self._load()

    def _load(self) -> None:
        seen_names: set[str] = set()
        for directory in (self._user_skills_dir, self.skills_dir):
            if not directory or not directory.exists():
                continue
            for path in sorted(directory.iterdir()):
                if path.is_dir() and (path / "SKILL.md").exists():
                    skill = _load_skill_dir(path)
                    if skill and skill.name not in seen_names:
                        self.skills.append(skill)
                        seen_names.add(skill.name)

    def get_descriptions(self) -> str:
        if not self.skills:
            return "(no skills)"

        groups: Dict[str, List[Skill]] = {}
        for skill in self.skills:
            groups.setdefault(skill.category, []).append(skill)

        ordered_cats = [c for c in self._CATEGORY_ORDER if c in groups]
        ordered_cats += [c for c in sorted(groups) if c not in ordered_cats]

        lines: List[str] = []
        for cat in ordered_cats:
            lines.append(f"\n### {cat}")
            for skill in groups[cat]:
                lines.append(f"  - {skill.name}: {skill.description}")
        return "\n".join(lines)

    def get_content(self, name: str) -> str:
        for skill in self.skills:
            if skill.name == name:
                return f'<skill name="{name}">\n{skill.body}\n</skill>'

        if self._user_skills_dir:
            skill = _load_skill_dir(self._user_skills_dir / name)
            if skill:
                self.skills.append(skill)
                return f'<skill name="{name}">\n{skill.body}\n</skill>'

        available = ", ".join(s.name for s in self.skills)
        return f"Error: Unknown skill '{name}'. Available: {available}"
