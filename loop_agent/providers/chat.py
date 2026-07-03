from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from loop_agent.providers.llm import build_llm


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    content: Optional[str] = None
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage_metadata: Optional[Dict[str, int]] = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class ProviderStreamError(RuntimeError):
    def __init__(self, *, provider: str, model: str, original: Exception) -> None:
        self.provider = provider
        self.model = model
        self.original = original
        self.status_code: Optional[int] = getattr(original, "status_code", None)
        super().__init__(
            f"provider_stream_error provider={provider} model={model}: "
            f"{type(original).__name__}: {original}"
        )

    @property
    def retryable(self) -> bool:
        if self.status_code is None:
            return True
        if self.status_code in (408, 429):
            return True
        return not 400 <= self.status_code < 500


class ChatLLM:
    def __init__(self, llm: Optional[Any] = None) -> None:
        self._llm = llm or build_llm()
        self.model_name = getattr(self._llm, "model_name", os.getenv("LANGCHAIN_MODEL_NAME", ""))

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        on_reasoning_chunk: Optional[Callable[[str], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> LLMResponse:
        llm = self._llm.bind_tools(tools) if tools else self._llm
        full_content = ""
        usage_metadata = None

        try:
            for chunk in llm.stream(messages):
                if should_cancel and should_cancel():
                    break

                delta = chunk.content or ""
                if delta:
                    full_content += delta
                    if on_text_chunk:
                        on_text_chunk(delta)

                if getattr(chunk, "usage_metadata", None):
                    usage_metadata = dict(chunk.usage_metadata)

            tool_calls: List[ToolCallRequest] = []
            if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                for tc in chunk.tool_calls:
                    args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    if isinstance(args, str):
                        args = json.loads(args) if args else {}
                    tool_calls.append(ToolCallRequest(
                        id=tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", ""),
                        name=tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", ""),
                        arguments=args or {},
                    ))

            return LLMResponse(
                content=full_content if not tool_calls else None,
                tool_calls=tool_calls,
                finish_reason="tool_calls" if tool_calls else "stop",
                usage_metadata=usage_metadata,
            )
        except Exception as exc:
            provider = os.getenv("LANGCHAIN_PROVIDER", "openai")
            raise ProviderStreamError(provider=provider, model=self.model_name, original=exc)

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        llm = self._llm.bind_tools(tools) if tools else self._llm
        response = llm.invoke(messages)
        content = response.content or ""

        tool_calls: List[ToolCallRequest] = []
        for tc in getattr(response, "tool_calls", []) or []:
            args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
            if isinstance(args, str):
                args = json.loads(args) if args else {}
            tool_calls.append(ToolCallRequest(
                id=tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", ""),
                name=tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", ""),
                arguments=args or {},
            ))

        return LLMResponse(
            content=content if not tool_calls else None,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else getattr(response, "finish_reason", "stop"),
            usage_metadata=getattr(response, "usage_metadata", None),
        )
