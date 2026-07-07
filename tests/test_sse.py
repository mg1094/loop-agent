import json

from loop_agent.api.sse import format_sse_event


def test_format_sse_event_includes_envelope_and_blank_line():
    out = format_sse_event(
        event_type="final",
        seq=1,
        ts="2026-07-07T00:00:00Z",
        run_id="r1",
        data={"status": "success"},
    )
    assert out.endswith("\n\n")
    # Single data: line per spec — one JSON object
    lines = out.split("\n")
    data_lines = [ln for ln in lines if ln.startswith("data:")]
    assert len(data_lines) == 1
    payload = json.loads(data_lines[0][len("data:"):].strip())
    assert payload == {
        "type": "final",
        "seq": 1,
        "ts": "2026-07-07T00:00:00Z",
        "run_id": "r1",
        "status": "success",
    }


def test_format_sse_event_does_not_newline_inside_json():
    # SSE forbids embedded newlines in data: lines; ensure we serialize without them.
    out = format_sse_event(
        event_type="tool_result",
        seq=2,
        ts="2026-07-07T00:00:01Z",
        run_id="r1",
        data={"name": "echo", "output": "line1\nline2"},
    )
    data_lines = [ln for ln in out.split("\n") if ln.startswith("data:")]
    assert len(data_lines) == 1
    payload = json.loads(data_lines[0][len("data:"):].strip())
    assert payload["output"] == "line1\nline2"
