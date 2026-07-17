import asyncio

import pytest

from loop_agent.providers.chat import (
    ChatLLM,
    LLMResponse,
    ProviderStreamError,
    ToolCallRequest,
    _classify_retryable,
    _retry_with_backoff,
)


# ---------------------------------------------------------------------------
# Pure-function unit tests
# ---------------------------------------------------------------------------
class _Boom(Exception):
    def __init__(self, code):
        super().__init__(f"boom {code}")
        self.status_code = code


def test_classify_retryable_429_is_retryable():
    assert _classify_retryable(ProviderStreamError(
        provider="openai", model="gpt-4o", original=_Boom(429)
    )) is True


def test_classify_retryable_408_is_retryable():
    assert _classify_retryable(ProviderStreamError(
        provider="openai", model="gpt-4o", original=_Boom(408)
    )) is True


def test_classify_retryable_503_is_retryable():
    assert _classify_retryable(ProviderStreamError(
        provider="openai", model="gpt-4o", original=_Boom(503)
    )) is True


def test_classify_retryable_401_is_not_retryable():
    assert _classify_retryable(ProviderStreamError(
        provider="openai", model="gpt-4o", original=_Boom(401)
    )) is False


def test_classify_retryable_connection_error_is_retryable():
    assert _classify_retryable(ConnectionError("reset")) is True


def test_classify_retryable_value_error_is_not_retryable():
    assert _classify_retryable(ValueError("not retryable")) is False


# ---------------------------------------------------------------------------
# _retry_with_backoff behavior
# ---------------------------------------------------------------------------
def test_retry_succeeds_on_retryable_failure(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(_retry_with_backoff, "__defaults__", ())  # no-op
    # Patch time.sleep inside the module
    import loop_agent.providers.chat as chat_mod
    monkeypatch.setattr(chat_mod.time, "sleep", lambda s: sleeps.append(s))

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _Boom(429)
        return "ok"

    result = _retry_with_backoff(
        flaky,
        provider="openai",
        model="gpt-4o",
        max_retries=5,
        base_delay=0.5,
        max_delay=8.0,
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2  # slept between attempts, not after success


def test_retry_gives_up_after_max_retries(monkeypatch):
    import loop_agent.providers.chat as chat_mod
    monkeypatch.setattr(chat_mod.time, "sleep", lambda s: None)

    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise _Boom(503)

    with pytest.raises(_Boom):
        _retry_with_backoff(
            always_fail,
            provider="openai",
            model="gpt-4o",
            max_retries=2,
        )
    # 1 initial + 2 retries = 3 calls
    assert calls["n"] == 3


def test_retry_does_not_retry_non_retryable(monkeypatch):
    import loop_agent.providers.chat as chat_mod
    monkeypatch.setattr(chat_mod.time, "sleep", lambda s: None)

    calls = {"n": 0}

    def fail_4xx():
        calls["n"] += 1
        raise _Boom(401)

    with pytest.raises(_Boom):
        _retry_with_backoff(
            fail_4xx, provider="openai", model="gpt-4o", max_retries=5
        )
    assert calls["n"] == 1  # didn't retry


def test_retry_honors_should_cancel(monkeypatch):
    import loop_agent.providers.chat as chat_mod
    monkeypatch.setattr(chat_mod.time, "sleep", lambda s: None)

    calls = {"n": 0}

    def fail():
        calls["n"] += 1
        raise _Boom(429)

    cancelled = {"yes": False}

    def should_cancel() -> bool:
        return cancelled["yes"]

    # First retry succeeds at canceling mid-loop
    calls_orig = lambda: fail()  # noqa
    triggered = {"yes": False}

    def fail_then_signal():
        nonlocal_triggered[0] = True
        raise _Boom(429)

    triggered_marker = {"first_done": False}

    def decide_cancel() -> bool:
        # Cancel *after* the first failure but before the next retry sleep
        return triggered_marker["first_done"]

    # Capture cancellation state with a shared dict
    state = {"cancel_after_first_failure": False}

    def should_cancel2() -> bool:
        return state["cancel_after_first_failure"]

    sleeps: list[float] = []
    monkeypatch.setattr(chat_mod.time, "sleep", lambda s: sleeps.append(s))

    def flaky2():
        # First call fails then marks cancellation for subsequent retries
        state["cancel_after_first_failure"] = True
        raise _Boom(429)

    with pytest.raises(RuntimeError, match="cancelled before retry"):
        _retry_with_backoff(
            flaky2,
            provider="openai",
            model="gpt-4o",
            max_retries=5,
            should_cancel=should_cancel2,
        )


def test_retry_calls_on_retry_callback(monkeypatch):
    import loop_agent.providers.chat as chat_mod
    monkeypatch.setattr(chat_mod.time, "sleep", lambda s: None)

    seen: list[tuple[int, BaseException, float]] = []

    def record(attempt, exc, jitter):
        seen.append((attempt, exc, jitter))

    calls = {"n": 0}

    def fail_then_ok():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _Boom(429)
        return "ok"

    _retry_with_backoff(
        fail_then_ok,
        provider="openai",
        model="gpt-4o",
        max_retries=3,
        on_retry=record,
    )
    assert len(seen) == 1
    attempt, exc, jitter = seen[0]
    assert attempt == 1
    assert isinstance(exc, _Boom)
    assert jitter >= 0


# ---------------------------------------------------------------------------
# ChatLLM.chat integration
# ---------------------------------------------------------------------------
class _StubLLM:
    """Minimal fake that mimics enough of ChatOpenAI for ChatLLM to drive retry."""

    def __init__(self, *, model_name: str = "stub-model"):
        self.model_name = model_name
        self.invoke_calls = 0
        self.bind_tools_calls: list[Any] = []

    def bind_tools(self, tools):
        self.bind_tools_calls.append(tools)
        return self

    def invoke(self, messages):
        self.invoke_calls += 1
        if self.invoke_calls < 3:
            raise _Boom(429)
        # Final-success response shape mimics what ChatOpenAI returns
        return _Resp(content="hello", tool_calls=[])


class _Resp:
    def __init__(self, content="", tool_calls=None, finish_reason="stop"):
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.usage_metadata = None


def test_chat_retries_until_success(monkeypatch):
    import loop_agent.providers.chat as chat_mod
    monkeypatch.setattr(chat_mod.time, "sleep", lambda s: None)

    stub = _StubLLM()
    llm = ChatLLM(llm=stub)
    resp = llm.chat(
        [{"role": "user", "content": "hi"}],
        max_retries=5,
        base_delay=0.5,
        max_delay=8.0,
    )
    assert isinstance(resp, LLMResponse)
    assert resp.content == "hello"
    assert stub.invoke_calls == 3


def test_chat_zero_max_retries_calls_once(monkeypatch):
    import loop_agent.providers.chat as chat_mod
    monkeypatch.setattr(chat_mod.time, "sleep", lambda s: None)

    stub = _StubLLM()
    llm = ChatLLM(llm=stub)
    with pytest.raises(_Boom):
        llm.chat(
            [{"role": "user", "content": "hi"}],
            max_retries=0,
        )
    assert stub.invoke_calls == 1


def test_chat_does_not_retry_4xx(monkeypatch):
    import loop_agent.providers.chat as chat_mod
    monkeypatch.setattr(chat_mod.time, "sleep", lambda s: None)

    stub = _StubLLM()
    # Override to always raise 401
    def always_401(messages):
        stub.invoke_calls += 1
        raise _Boom(401)
    stub.invoke = always_401  # type: ignore[assignment]

    llm = ChatLLM(llm=stub)
    with pytest.raises(_Boom):
        llm.chat([{"role": "user", "content": "hi"}], max_retries=5)
    assert stub.invoke_calls == 1
