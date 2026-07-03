import json
from pathlib import Path

from loop_agent.agent.trace import TraceWriter


def test_trace_write(tmp_path: Path):
    writer = TraceWriter(tmp_path)
    writer.write({"type": "start", "iter": 1})
    writer.write({"type": "final", "content": "done"})

    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "start"
