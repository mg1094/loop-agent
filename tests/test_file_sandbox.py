import json
from pathlib import Path

from loop_agent.tools import build_registry


def test_file_tools_unsandboxed_by_default(tmp_path: Path):
    """When allowed_roots is omitted, write_file/read_file roam freely (legacy)."""
    registry = build_registry()
    target = tmp_path / "outside-anywhere.txt"
    payload = registry.execute("write_file", {"path": str(target), "content": "x"})
    assert json.loads(payload)["status"] == "ok"


def test_write_inside_allowed_root_succeeds(tmp_path: Path):
    registry = build_registry(allowed_roots=[tmp_path])
    target = tmp_path / "ok.txt"
    payload = registry.execute("write_file", {"path": str(target), "content": "hi"})
    assert json.loads(payload)["status"] == "ok"
    payload = registry.execute("read_file", {"path": str(target)})
    assert json.loads(payload)["content"] == "hi"


def test_write_outside_allowed_root_is_rejected(tmp_path: Path):
    registry = build_registry(allowed_roots=[tmp_path])
    other = Path("/etc/passwd")
    payload = registry.execute("write_file", {"path": str(other), "content": "x"})
    body = json.loads(payload)
    assert body["status"] == "error"
    assert "outside allowed roots" in body["error"]


def test_read_outside_allowed_root_is_rejected(tmp_path: Path):
    registry = build_registry(allowed_roots=[tmp_path])
    payload = registry.execute("read_file", {"path": "/etc/passwd"})
    body = json.loads(payload)
    assert body["status"] == "error"
    assert "outside allowed roots" in body["error"]


def test_dotdot_escape_is_rejected(tmp_path: Path):
    registry = build_registry(allowed_roots=[tmp_path])
    sub = tmp_path / "sub"
    sub.mkdir()
    escape = sub / ".." / ".." / "etc" / "passwd"
    payload = registry.execute("read_file", {"path": str(escape)})
    body = json.loads(payload)
    assert body["status"] == "error"
    assert "outside allowed roots" in body["error"]


def test_default_sandbox_includes_runs_dir(tmp_path: Path, monkeypatch):
    """The CLI/API builder pins cwd + cwd/runs as allowed roots."""
    from loop_agent.cli import commands

    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()

    roots = commands._default_allowed_roots()
    assert tmp_path.resolve() in roots
    assert (tmp_path / "runs").resolve() in roots


def test_unrestricted_env_var_disables_sandbox(monkeypatch):
    from loop_agent.cli import commands

    monkeypatch.setenv("LOOP_AGENT_UNRESTRICTED_FILES", "1")
    assert commands._default_allowed_roots() == []
