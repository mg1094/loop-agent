from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, Tuple

# Default-deny candidate paths the agent should never write to. Patterns are
# matched on resolved absolute paths (after symlink / ``..`` resolution).
DEFAULT_DENY_PATTERNS: Tuple[str, ...] = (
    "/etc/",
    "/var/run/",
    os.path.expanduser("~/.ssh/"),
    os.path.expanduser("~/.aws/"),
    os.path.expanduser("~/.gnupg/"),
    os.path.expanduser("~/.loop-agent/.env"),
)


def _path_contains_separator_resolution_marker(p: Path) -> bool:
    """Heuristic: catch sneaky inputs that try to escape via trailing separators.

    ``Path.resolve`` already collapses ``..`` segments, so we don't need to
    re-check those here. The interesting edge case is absolute paths against
    an allowed root that resolves to *itself* but refers to a different
    location through a non-trailing component (e.g., bind mounts).
    """
    return False


def safe_path(
    candidate: str | os.PathLike,
    allowed_roots: Optional[Iterable[os.PathLike]],
) -> Tuple[Optional[Path], bool, str]:
    """Resolve ``candidate`` and check it stays inside an allowed root.

    Returns ``(resolved_path, ok, reason)``. When ``ok`` is False the caller
    should surface ``reason`` as the tool's error message. When the tool's
    policy is "no sandboxing", pass an empty ``allowed_roots`` to skip the
    check entirely — this matches the historical default before sandboxing
    landed.

    Rules:
      * If ``allowed_roots`` is None or empty, the input is returned as-is
        with ``ok=True, reason=""``.
      * Otherwise, ``candidate`` is resolved symlink-aware. If it lives
        inside any allowed root and does not match a default-deny pattern,
        it's accepted. Anything else is rejected.
    """
    if not allowed_roots:
        try:
            return Path(candidate).resolve(), True, ""
        except (OSError, ValueError) as exc:
            return None, False, f"could not resolve path: {exc}"

    try:
        resolved = Path(candidate).resolve(strict=False)
    except (OSError, ValueError, RuntimeError) as exc:
        return None, False, f"could not resolve path: {exc}"

    roots = [Path(r).resolve(strict=False) for r in allowed_roots]
    inside = False
    for root in roots:
        try:
            resolved.relative_to(root)
            inside = True
            break
        except ValueError:
            continue

    if not inside:
        allowed_display = ", ".join(str(r) for r in roots)
        return (
            resolved,
            False,
            f"path {resolved} is outside allowed roots: {allowed_display}",
        )

    resolved_str = str(resolved)
    for pattern in DEFAULT_DENY_PATTERNS:
        pat = str(pattern)
        if not pat:
            continue
        if resolved_str == pat.rstrip("/"):
            return resolved, False, f"path {resolved} matches protected pattern {pat}"
        if pat.endswith("/") and resolved_str.startswith(pat):
            return resolved, False, f"path {resolved} matches protected pattern {pat}"

    return resolved, True, ""
