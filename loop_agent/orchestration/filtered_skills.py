"""Per-worker skill-scope proxy.

``SkillsLoader`` exposes every bundled + user skill globally. The Supervisor
needs each worker to see only the skills it has been authorized for, so an
unauthorized ``load_skill`` call cannot leak a skill body it should not
have. ``FilteredSkillsLoader`` is a thin subclass that narrows the exposed
``skills`` list and intercepts ``get_content(name)`` with a fail-fast
``PermissionError`` for unauthorized names.

Snapshot semantics: the underlying loader's ``skills`` is captured at
construction time. Skills added to the underlying loader after the proxy
exists do NOT leak through, which keeps worker scope stable across a run.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Set

from loop_agent.agent.skills import Skill, SkillsLoader


class FilteredSkillsLoader(SkillsLoader):
    """``SkillsLoader`` narrowed to an allow-list of skill names."""

    def __init__(self, full: SkillsLoader, allowed: Optional[Iterable[str]] = None) -> None:
        # Snapshot the underlying list now and never look at it again.
        self._all: List[Skill] = list(full.skills)
        # Carry over the disk-search paths so authorized fall-throughs can
        # still lazily load from disk via super().
        self.skills_dir: Optional[Path] = getattr(full, "skills_dir", None)
        self._user_skills_dir: Optional[Path] = getattr(full, "_user_skills_dir", None)
        # Internal state for the proxy. An empty allow-list means
        # "no restriction" so the worker sees every skill in the snapshot.
        self._allowed: Set[str] = set(allowed or ())
        self._skill_by_name = {s.name: s for s in self._all}
        # Public view: only the allowed subset (or full snapshot if no
        # allow-list was supplied).
        if self._allowed:
            self.skills: List[Skill] = [s for s in self._all if s.name in self._allowed]
        else:
            self.skills: List[Skill] = list(self._all)

    def get_content(self, name: str) -> str:
        """Return the body of ``name`` if authorized; raise ``PermissionError`` otherwise."""
        # Only enforce the allow-list when one was actually supplied.
        if self._allowed and name not in self._allowed:
            raise PermissionError(
                f"Skill '{name}' is not available to this worker"
            )
        # Authorized path: prefer the snapshot; fall through to base for
        # late-authorized-on-disk skills.
        if name in self._skill_by_name:
            skill = self._skill_by_name[name]
            return f'<skill name="{name}">\n{skill.body}\n</skill>'
        return super().get_content(name)
