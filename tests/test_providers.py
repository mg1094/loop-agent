import os

from loop_agent.providers.llm import _sync_provider_env
from loop_agent.providers.chat import LLMResponse


def test_sync_provider_env_openai(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    _sync_provider_env()
    assert os.getenv("OPENAI_API_KEY") == "sk-test"


def test_llm_response_has_tool_calls():
    response = LLMResponse(
        content="hello",
        finish_reason="stop",
    )
    assert not response.has_tool_calls
