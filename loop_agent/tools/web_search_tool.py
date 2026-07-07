import json
import os
from typing import Any, Dict

import httpx

from loop_agent.agent.tools import BaseTool


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web using BoCha AI and return relevant web pages "
        "with title, URL, and snippet."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (1-50). Default 10.",
                "default": 10,
            },
            "freshness": {
                "type": "string",
                "description": (
                    "Time range filter. Options: noLimit (default), oneDay, "
                    "oneWeek, oneMonth, oneYear, YYYY-MM-DD, or YYYY-MM-DD..YYYY-MM-DD."
                ),
                "default": "noLimit",
            },
            "summary": {
                "type": "boolean",
                "description": "Whether to include text summaries. Default false.",
                "default": False,
            },
        },
        "required": ["query"],
    }
    repeatable = True
    is_readonly = True

    @classmethod
    def check_available(cls) -> bool:
        return bool(os.environ.get("BOCHA_API_KEY"))

    def execute(
        self,
        *,
        query: str,
        count: int = 10,
        freshness: str = "noLimit",
        summary: bool = False,
        **kwargs: Any,
    ) -> str:
        api_key = os.environ.get("BOCHA_API_KEY")
        if not api_key:
            return json.dumps(
                {"status": "error", "error": "BOCHA_API_KEY not configured"},
                ensure_ascii=False,
            )

        payload: Dict[str, Any] = {
            "query": query,
            "count": max(1, min(50, int(count))),
            "freshness": freshness,
            "summary": bool(summary),
        }

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    "https://api.bocha.cn/v1/web-search",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            return json.dumps(
                {
                    "status": "error",
                    "error": f"BoCha API returned {exc.response.status_code}",
                    "detail": exc.response.text[:500],
                },
                ensure_ascii=False,
            )
        except httpx.RequestError as exc:
            return json.dumps(
                {"status": "error", "error": f"Request failed: {exc}"},
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {"status": "error", "error": str(exc)},
                ensure_ascii=False,
            )

        if data.get("code") != 200:
            return json.dumps(
                {
                    "status": "error",
                    "error": data.get("msg") or "BoCha API error",
                    "code": data.get("code"),
                },
                ensure_ascii=False,
            )

        web_pages = data.get("data", {}).get("webPages", {}).get("value", [])
        results = [
            {
                "title": page.get("name", ""),
                "url": page.get("url", ""),
                "snippet": page.get("snippet", ""),
            }
            for page in web_pages
        ]

        return json.dumps(
            {
                "status": "ok",
                "query": query,
                "total": data.get("data", {})
                .get("webPages", {})
                .get("totalEstimatedMatches", 0),
                "results": results,
            },
            ensure_ascii=False,
        )
