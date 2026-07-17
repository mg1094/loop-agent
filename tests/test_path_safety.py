from pathlib import Path

from loop_agent.tools.path_safety import safe_path


def test_safe_path_returns_resolved_when_no_roots_supplied():
    """Backward compat: missing/empty allowed_roots means no sandbox."""
    resolved, ok, reason = safe_path("/tmp/anything.txt", [])
    assert ok is True
    assert reason == ""
    assert resolved == Path("/tmp/anything.txt").resolve()


def test_safe_path_accepts_candidate_inside_allowed_root(tmp_path: Path):
    (tmp_path / "a.txt").write_text("ok")
    resolved, ok, reason = safe_path(tmp_path / "a.txt", [tmp_path])
    assert ok is True, reason
    assert reason == ""
    assert resolved == (tmp_path / "a.txt").resolve()


def test_safe_path_rejects_candidate_outside_allowed_root(tmp_path: Path):
    other = Path("/etc/passwd")
    _, ok, reason = safe_path(other, [tmp_path])
    assert ok is False
    assert "outside allowed roots" in reason


def test_safe_path_rejects_dotdot_escape(tmp_path: Path):
    nested = tmp_path / "sub"
    nested.mkdir()
    escape = nested / ".." / ".." / "etc" / "passwd"
    _, ok, reason = safe_path(escape, [tmp_path])
    assert ok is False
    assert "outside allowed roots" in reason


def test_safe_path_rejects_default_deny_etc(tmp_path: Path):
    # Symbolic link from inside allowed root -> /etc would still be caught
    # by resolution. Without the symlink, /etc itself should be blocked
    # because it isn't inside tmp_path.
    _, ok, reason = safe_path("/etc/passwd", [tmp_path])
    assert ok is False


def test_safe_path_accepts_multiple_roots(tmp_path: Path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    target = root_b / "x.txt"
    target.write_text("hi")

    _, ok, reason = safe_path(target, [root_a, root_b])
    assert ok is True, reason
