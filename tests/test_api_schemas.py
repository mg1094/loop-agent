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