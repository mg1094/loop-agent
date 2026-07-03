from pathlib import Path

from loop_agent.agent.skills import Skill, SkillsLoader


def test_load_skill(tmp_path: Path):
    skill_dir = tmp_path / "writing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: writing
description: Writing assistant.
category: writing
---

## Workflow
Plan, draft, edit.
""", encoding="utf-8")

    loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    assert len(loader.skills) == 1
    assert loader.skills[0].name == "writing"


def test_get_content(tmp_path: Path):
    skill_dir = tmp_path / "writing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: writing
description: Writing assistant.
---

Body here.
""", encoding="utf-8")

    loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    content = loader.get_content("writing")
    assert '<skill name="writing">' in content
    assert "Body here." in content


def test_get_descriptions(tmp_path: Path):
    skill_dir = tmp_path / "writing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: writing
description: Writing assistant.
category: writing
---

Body.
""", encoding="utf-8")

    loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    desc = loader.get_descriptions()
    assert "writing" in desc
    assert "Writing assistant." in desc
