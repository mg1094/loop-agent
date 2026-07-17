from loop_agent.agent.skills import SkillsLoader


def test_builtin_skills_loaded():
    loader = SkillsLoader()
    names = {s.name for s in loader.skills}
    assert "writing" in names
    assert "coding" in names
    assert "research" in names
    assert "report-writing" in names
    assert "code-review" in names
