from __future__ import annotations

from typing import Any


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown text.

    Returns:
        (metadata dict, body text)
    """
    meta: dict[str, Any] = {}
    body = text
    stripped = text.lstrip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                meta = yaml.safe_load(parts[1]) or {}
            except ImportError:
                meta = {}
            body = parts[2].strip("\n")
    return meta, body
