from pydantic import ValidationError
import pytest

from loop_agent.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SkillsResponse,
    ToolsResponse,
)


def test_chat_request_accepts_prompt():
    req = ChatRequest(prompt="hello")
    assert req.prompt == "hello"


def test_chat_request_rejects_empty_string():
    with pytest.raises(ValidationError):
        ChatRequest(prompt="")


def test_chat_request_rejects_missing_prompt():
    with pytest.raises(ValidationError):
        ChatRequest()


def test_chat_response_round_trip():
    resp = ChatResponse(status="success", content="hi", run_id="r1", run_dir="/tmp/r1")
    assert resp.status == "success"
    assert resp.content == "hi"


def test_skills_response_round_trip():
    resp = SkillsResponse(descriptions="### writing\n  - writing: desc")
    assert "writing" in resp.descriptions


def test_tools_response_round_trip():
    resp = ToolsResponse(tools=["echo", "read_file"])
    assert resp.tools == ["echo", "read_file"]


def test_health_response_round_trip():
    resp = HealthResponse(status="ok", version="0.1.0")
    assert resp.status == "ok"
    assert resp.version == "0.1.0"


def test_chat_request_accepts_session_id():
    req = ChatRequest(prompt="hi", session_id="abc")
    assert req.session_id == "abc"


def test_chat_request_session_id_defaults_to_empty():
    req = ChatRequest(prompt="hi")
    assert req.session_id == ""


def test_chat_request_session_id_too_long():
    with pytest.raises(ValidationError):
        ChatRequest(prompt="hi", session_id="x" * 257)


def test_chat_response_session_id_field():
    resp = ChatResponse(
        status="success", content="hi", run_id="r1",
        run_dir="/tmp/r1", session_id="abc",
    )
    assert resp.session_id == "abc"