import json
from pathlib import Path

import pytest

from loop_agent.agent.tools import BaseTool, ToolRegistry
from loop_agent.tools import build_registry
from loop_agent.tools.web_search_tool import WebSearchTool


def test_emit_progress_no_op_when_no_sink():
    class _T(BaseTool):
        name = "noop-tool"
        description = "x"
        parameters = {"type": "object", "properties": {}}

        def execute(self, **kwargs):
            self._emit_progress("hello")
            return "{}"

    _T().execute()


def test_tool_registry_binds_progress_per_tool():
    seen: list[tuple[str, str]] = []
    registry = ToolRegistry(
        on_progress=lambda name, phase: seen.append((name, phase))
    )

    class _T(BaseTool):
        name = "tracker"
        description = "x"
        parameters = {"type": "object", "properties": {}}

        def execute(self, **kwargs):
            self._emit_progress("phase-1")
            self._emit_progress("phase-2")
            return "{}"

    registry.register(_T())
    registry.execute("tracker", {})
    assert seen == [("tracker", "phase-1"), ("tracker", "phase-2")]


def test_set_on_progress_rebinds_existing_tools():
    seen: list[tuple[str, str]] = []
    registry = ToolRegistry()

    class _T(BaseTool):
        name = "tracker"
        description = "x"
        parameters = {"type": "object", "properties": {}}

        def execute(self, **kwargs):
            self._emit_progress("hi")
            return "{}"

    registry.register(_T())
    # Pre-set_on_progress: tool has no sink, no-op
    registry.execute("tracker", {})
    assert seen == []

    registry.set_on_progress(
        lambda name, phase: seen.append((name, phase))
    )
    registry.execute("tracker", {})
    assert seen == [("tracker", "hi")]


def test_set_on_progress_can_be_cleared_by_passing_none():
    seen: list[tuple[str, str]] = []
    registry = ToolRegistry(
        on_progress=lambda name, phase: seen.append((name, phase))
    )

    class _T(BaseTool):
        name = "tracker"
        description = "x"
        parameters = {"type": "object", "properties": {}}

        def execute(self, **kwargs):
            self._emit_progress("hi")
            return "{}"

    registry.register(_T())
    registry.execute("tracker", {})
    assert seen == [("tracker", "hi")]

    registry.set_on_progress(None)
    registry.execute("tracker", {})
    assert seen == [("tracker", "hi")]  # unchanged


@pytest.mark.parametrize("tool_name", ["read_file", "write_file"])
def test_built_in_tools_emit_progress(tmp_path: Path, monkeypatch, tool_name):
    seen: list[tuple[str, str]] = []
    registry = build_registry(
        allowed_roots=[tmp_path],
        on_progress=lambda name, phase: seen.append((name, phase)),
    )

    if tool_name == "read_file":
        target = tmp_path / "x.txt"
        target.write_text("hello")
        registry.execute("read_file", {"path": str(target)})
    else:
        target = tmp_path / "x.txt"
        registry.execute(
            "write_file", {"path": str(target), "content": "hi"}
        )

    names = [n for (n, _) in seen]
    assert tool_name in names
    phases = [p for (n, p) in seen if n == tool_name]
    assert any("opening" in p for p in phases)
    assert any("chars" in p or "rejected" in p for p in phases)


def test_read_file_progress_includes_sandbox_rejection(tmp_path: Path):
    """Reading outside allowed roots still emits a rejection phase."""
    seen: list[tuple[str, str]] = []
    registry = build_registry(
        allowed_roots=[tmp_path],
        on_progress=lambda name, phase: seen.append((name, phase)),
    )
    registry.execute("read_file", {"path": "/etc/passwd"})
    phases = [p for (n, p) in seen if n == "read_file"]
    assert any("rejected" in p for p in phases)


def test_web_search_emits_progress_phases(monkeypatch):
    """BoCha is mocked, but we still assert the phase order is emitted."""
    seen: list[tuple[str, str]] = []
    monkeypatch.setenv("BOCHA_API_KEY", "fake")

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "code": 200,
                "data": {
                    "webPages": {
                        "value": [
                            {"name": "t", "url": "u", "snippet": "s"}
                        ],
                        "totalEstimatedMatches": 1,
                    }
                },
            }

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            return _Resp()

    import loop_agent.tools.web_search_tool as ws_mod
    ws_mod.httpx.Client = _Client

    registry = ToolRegistry(
        on_progress=lambda name, phase: seen.append((name, phase))
    )
    registry.register(WebSearchTool())
    result = registry.execute("web_search", {"query": "hi"})
    payload = json.loads(result)
    assert payload["status"] == "ok"

    phases = [p for (n, p) in seen if n == "web_search"]
    assert any("sending query" in p for p in phases)
    assert any("response received" in p for p in phases)
    assert any("parsed" in p for p in phases)


def test_emit_progress_swallows_callback_errors():
    """A misbehaving progress sink must not break tool execution."""
    class _T(BaseTool):
        name = "exploder"
        description = "x"
        parameters = {"type": "object", "properties": {}}

        def execute(self, **kwargs):
            self._emit_progress("phase")
            return json.dumps({"ok": True})

    registry = ToolRegistry(
        on_progress=lambda name, phase: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
    )
    registry.register(_T())
    # Should NOT raise
    assert registry.execute("exploder", {}) == '{"ok": true}'
