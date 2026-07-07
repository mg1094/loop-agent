from __future__ import annotations

import pytest

from loop_agent.agent.skills import Skill, SkillsLoader
from loop_agent.orchestration.filtered_skills import FilteredSkillsLoader


def _full_loader() -> SkillsLoader:
    """Build a SkillsLoader with three synthetic skills in memory."""
    loader = SkillsLoader.__new__(SkillsLoader)
    loader.skills = [
        Skill(name="public", description="Visible to all", body="public body"),
        Skill(name="sensitive", description="Restricted", body="hidden"),
        Skill(name="shared", description="Visible to all", body="shared body"),
    ]
    loader.skills_dir = None
    loader._user_skills_dir = None
    return loader


def test_filtered_skills_empty_allowed_returns_everything():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed=set())
    assert {s.name for s in proxy.skills} == {"public", "sensitive", "shared"}


def test_filtered_skills_narrows_skills_list():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed={"public"})
    assert [s.name for s in proxy.skills] == ["public"]
    # Descriptions must only mention allowed names.
    desc = proxy.get_descriptions()
    assert "public" in desc
    assert "sensitive" not in desc


def test_filtered_skills_get_content_allowed_name():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed={"public"})
    body = proxy.get_content("public")
    assert "public body" in body


def test_filtered_skills_get_content_unauthorized_raises_permission_error():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed={"public"})
    with pytest.raises(PermissionError):
        proxy.get_content("sensitive")


def test_filtered_skills_snapshot_isolation():
    full = _full_loader()
    proxy = FilteredSkillsLoader(full, allowed={"public"})
    # Add a new skill to the underlying loader after construction.
    full.skills.append(Skill(name="late-add", description="x", body="y"))
    assert "late-add" not in {s.name for s in proxy.skills}
