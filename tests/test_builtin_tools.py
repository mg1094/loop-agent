import json
from pathlib import Path

from loop_agent.tools import build_registry


def test_build_registry_has_echo():
    registry = build_registry()
    assert "echo" in registry


def test_echo_tool():
    registry = build_registry()
    result = registry.execute("echo", {"message": "hello"})
    assert json.loads(result)["result"] == "hello"


def test_write_and_read_file(tmp_path: Path):
    registry = build_registry()
    path = tmp_path / "test.txt"
    result = registry.execute("write_file", {"path": str(path), "content": "hello world"})
    assert json.loads(result)["status"] == "ok"

    result = registry.execute("read_file", {"path": str(path)})
    assert json.loads(result)["content"] == "hello world"
