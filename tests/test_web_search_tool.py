import json
import os

import httpx
import pytest

from loop_agent.agent.tools import ToolRegistry
from loop_agent.tools import build_registry
from loop_agent.tools.web_search_tool import WebSearchTool


class FakeResponse:
    def __init__(self, status_code, json_data, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=None, response=self
            )


def test_web_search_tool_schema():
    tool = WebSearchTool()
    assert tool.name == "web_search"
    assert "query" in tool.parameters["properties"]
    assert "count" in tool.parameters["properties"]
    assert tool.is_readonly is True


def test_web_search_tool_unavailable_without_env(monkeypatch):
    monkeypatch.delenv("BOCHA_API_KEY", raising=False)
    assert WebSearchTool.check_available() is False


def test_web_search_tool_available_with_env(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    assert WebSearchTool.check_available() is True


def test_web_search_tool_returns_error_when_key_missing(monkeypatch):
    monkeypatch.delenv("BOCHA_API_KEY", raising=False)
    tool = WebSearchTool()
    result = tool.execute(query="test")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "BOCHA_API_KEY" in payload["error"]


def test_web_search_tool_success(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.bocha.cn/v1/web-search"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["query"] == "阿里巴巴 ESG"
        return FakeResponse(
            200,
            {
                "code": 200,
                "data": {
                    "webPages": {
                        "totalEstimatedMatches": 100,
                        "value": [
                            {
                                "name": "Title 1",
                                "url": "https://example.com/1",
                                "snippet": "Snippet 1",
                            },
                            {
                                "name": "Title 2",
                                "url": "https://example.com/2",
                                "snippet": "Snippet 2",
                            },
                        ],
                    }
                },
            },
        )

    monkeypatch.setattr("httpx.Client.post", lambda self, url, headers=None, json=None, timeout=None: fake_post(url, headers, json, timeout))

    tool = WebSearchTool()
    result = tool.execute(query="阿里巴巴 ESG", count=5)
    payload = json.loads(result)
    assert payload["status"] == "ok"
    assert payload["query"] == "阿里巴巴 ESG"
    assert len(payload["results"]) == 2
    assert payload["results"][0]["title"] == "Title 1"


def test_web_search_tool_clamps_count(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse(
            200,
            {
                "code": 200,
                "data": {"webPages": {"totalEstimatedMatches": 0, "value": []}},
            },
        )

    monkeypatch.setattr("httpx.Client.post", lambda self, url, headers=None, json=None, timeout=None: fake_post(url, headers, json, timeout))

    tool = WebSearchTool()
    tool.execute(query="x", count=100)
    assert captured["json"]["count"] == 50

    tool.execute(query="x", count=0)
    assert captured["json"]["count"] == 1


def test_web_search_tool_api_error_response(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(
            200,
            {"code": 500, "msg": "Internal error"},
        )

    monkeypatch.setattr("httpx.Client.post", lambda self, url, headers=None, json=None, timeout=None: fake_post(url, headers, json, timeout))

    tool = WebSearchTool()
    result = tool.execute(query="test")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "Internal error"


def test_web_search_tool_http_error(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")

    def fake_post(self, url, headers=None, json=None, timeout=None):
        resp = FakeResponse(401, {}, text="Unauthorized")
        raise httpx.HTTPStatusError("error", request=None, response=resp)

    monkeypatch.setattr("httpx.Client.post", fake_post)

    tool = WebSearchTool()
    result = tool.execute(query="test")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "401" in payload["error"]


def test_build_registry_includes_web_search_when_key_set(monkeypatch):
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    registry = build_registry()
    assert "web_search" in registry


def test_build_registry_excludes_web_search_when_key_missing(monkeypatch):
    monkeypatch.delenv("BOCHA_API_KEY", raising=False)
    registry = build_registry()
    assert "web_search" not in registry
