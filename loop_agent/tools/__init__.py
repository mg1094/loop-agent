from __future__ import annotations

import importlib
import logging
import pkgutil
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from loop_agent.agent.tools import BaseTool, ToolRegistry

if TYPE_CHECKING:
    from loop_agent.agent.skills import SkillsLoader

logger = logging.getLogger(__name__)

_SUBCLASSES_CACHE: list[type[BaseTool]] | None = None


def _discover_subclasses() -> list[type[BaseTool]]:
    global _SUBCLASSES_CACHE
    if _SUBCLASSES_CACHE is not None:
        return _SUBCLASSES_CACHE

    pkg_dir = str(Path(__file__).parent)
    for _, module_name, _ in pkgutil.iter_modules([pkg_dir]):
        if module_name.startswith("_"):
            continue
        try:
            importlib.import_module(f"loop_agent.tools.{module_name}")
        except Exception as exc:
            logger.warning("Skipped loop_agent.tools.%s: %s", module_name, exc)

    classes: list[type[BaseTool]] = []
    queue = deque(BaseTool.__subclasses__())
    while queue:
        cls = queue.popleft()
        if cls.name:
            classes.append(cls)
        queue.extend(cls.__subclasses__())

    _SUBCLASSES_CACHE = classes
    return classes


def build_registry(
    *,
    skills_loader: "SkillsLoader | None" = None,
    event_callback: Callable[[str, dict], None] | None = None,
) -> ToolRegistry:
    from loop_agent.tools.load_skill_tool import LoadSkillTool

    registry = ToolRegistry()
    for cls in _discover_subclasses():
        try:
            if hasattr(cls, "check_available") and not cls.check_available():
                logger.info("Tool %s unavailable, skipping", cls.name)
                continue
            if cls is LoadSkillTool:
                registry.register(cls(skills_loader=skills_loader))
            else:
                registry.register(cls())
        except Exception as exc:
            logger.warning("Failed to register tool %s: %s", cls.name, exc)

    return registry
