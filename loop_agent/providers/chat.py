from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from loop_agent.providers.llm import build_llm

logger = logging.getLogger(__name__)


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


def _classify_retryable(exc: BaseException) -> bool:
    """Decide whether an LLM provider exception is worth retrying.

    Order:
      1. If the exception exposes ``retryable`` (e.g. ``ProviderStreamError``),
         trust it.
      2. Otherwise, if it has a ``status_code`` attribute (HTTP-shaped
         errors), retry 408/429/5xx, refuse other 4xx.
      3. Finally, treat ``ConnectionError`` / ``TimeoutError`` as retryable;
         everything else propagates.
    """
    flagged = getattr(exc, "retryable", None)
    if flagged is not None:
        return bool(flagged)

    status = getattr(exc, "status_code", None)
    if status is not None:
        if status in (408, 429):
            return True
        if 500 <= status < 600:
            return True
        if 400 <= status < 500:
            return False

    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return False


def _retry_with_backoff(
    fn: Callable[[], Any],
    *,
    provider: str,
    model: str,
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Any:
    """Invoke ``fn`` and retry on classified retryable failures.

    Delays follow exponential backoff with full jitter: ``base_delay *
    2**attempt`` capped at ``max_delay``, randomly drawn up to that
    limit. ``max_retries`` is the number of *additional* attempts after
    the first call, so the total call count is ``1 + max_retries``.

    Cancellation is honored between attempts: ``should_cancel()`` is
    checked before each sleep; if it returns True, the most recent
    retryable exception is re-raised so callers see a clean exit.

    ``sleep`` is injectable so tests can run with zero wall-clock time.
    """
    attempt = 0
    while True:
        if should_cancel and should_cancel():
            raise RuntimeError("cancelled before retry")
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001
            if not _classify_retryable(exc):
                raise
            if attempt >= max_retries:
                logger.warning(
                    "%s/%s gave up after %d retries: %s",
                    provider, model, attempt, exc,
                )
                raise
            attempt += 1
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            jitter = random.uniform(0, delay)
            if on_retry:
                on_retry(attempt, exc, jitter)
            logger.info(
                "%s/%s attempt %d failed (%s); retrying in %.2fs",
                provider, model, attempt, type(exc).__name__, jitter,
            )
            time.sleep(jitter)


class ChatLLM:
    def __init__(self, llm: Optional[Any] = None) -> None:
        self._llm = llm or build_llm()
        self.model_name = getattr(
            self._llm, "model_name", os.getenv("LANGCHAIN_MODEL_NAME", "")
        )

    @staticmethod
    def _provider_info() -> tuple[str, str]:
        return (
            os.getenv("LANGCHAIN_PROVIDER", "openai"),
            os.getenv("LANGCHAIN_MODEL_NAME", ""),
        )

    # ------------------------------------------------------------------
    # Tool-call parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_tool_calls(
        raw_tool_calls: Any,
    ) -> List[ToolCallRequest]:
        tool_calls: List[ToolCallRequest] = []
        for tc in raw_tool_calls or []:
            args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
            if isinstance(args, str):
                args = json.loads(args) if args else {}
            tool_calls.append(
                ToolCallRequest(
                    id=tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", ""),
                    name=tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", ""),
                    arguments=args or {},
                )
            )
        return tool_calls

    # ------------------------------------------------------------------
    # Non-streaming chat with retry
    # ------------------------------------------------------------------
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
        on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> LLMResponse:
        provider, model = self._provider_info()
        llm = self._llm.bind_tools(tools) if tools else self._llm

        def call() -> LLMResponse:
            response = llm.invoke(messages)
            content = response.content or ""
            tool_calls = self._parse_tool_calls(
                getattr(response, "tool_calls", []) or []
            )
            return LLMResponse(
                content=content if not tool_calls else None,
                tool_calls=tool_calls,
                finish_reason=(
                    "tool_calls" if tool_calls
                    else getattr(response, "finish_reason", "stop")
                ),
                usage_metadata=getattr(response, "usage_metadata", None),
            )

        if max_retries <= 0:
            return call()
        return _retry_with_backoff(
            call,
            provider=provider,
            model=model or self.model_name,
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            on_retry=on_retry,
            should_cancel=should_cancel,
        )

    # ------------------------------------------------------------------
    # Streaming chat with retry-on-cold-start
    # ------------------------------------------------------------------
    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        on_reasoning_chunk: Optional[Callable[[str], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
    ) -> LLMResponse:
        provider, model = self._provider_info()
        llm = self._llm.bind_tools(tools) if tools else self._llm

        def call() -> LLMResponse:
            full_content = ""
            usage_metadata = None
            try:
                last_chunk = None
                for chunk in llm.stream(messages):
                    last_chunk = chunk
                    if should_cancel and should_cancel():
                        break
                    delta = chunk.content or ""
                    if delta:
                        full_content += delta
                        if on_text_chunk:
                            on_text_chunk(delta)
                    if getattr(chunk, "usage_metadata", None):
                        usage_metadata = dict(chunk.usage_metadata)
            except Exception as exc:
                raise ProviderStreamError(
                    provider=provider, model=model or self.model_name, original=exc
                )

            tool_calls: List[ToolCallRequest] = []
            if last_chunk is not None and getattr(last_chunk, "tool_calls", None):
                tool_calls = self._parse_tool_calls(last_chunk.tool_calls)
            return LLMResponse(
                content=full_content if not tool_calls else None,
                tool_calls=tool_calls,
                finish_reason="tool_calls" if tool_calls else "stop",
                usage_metadata=usage_metadata,
            )

        if max_retries <= 0:
            return call()
        return _retry_with_backoff(
            call,
            provider=provider,
            model=model or self.model_name,
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            should_cancel=should_cancel,
        )
