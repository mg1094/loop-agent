from loop_agent.agent.truncation import (
    MAX_HISTORY_MESSAGES,
    TRUNCATION_SENTINEL,
    truncate_messages,
)


def test_no_truncation_when_under_window():
    msgs = [{"role": "system", "content": "sys"}] + [
        {"role": "user", "content": f"m{i}"} for i in range(5)
    ]
    result = truncate_messages(msgs)
    assert result == msgs


def test_truncate_when_over_window():
    msgs = [{"role": "system", "content": "sys"}] + [
        {"role": "user", "content": f"m{i}"} for i in range(25)
    ]
    result = truncate_messages(msgs, window=20)
    # system + sentinel + last 20 user msgs
    assert len(result) == 1 + 1 + 20
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "system"
    assert TRUNCATION_SENTINEL in result[1]["content"]


def test_system_messages_preserved():
    msgs = [
        {"role": "system", "content": "sys1"},
        {"role": "system", "content": "sys2"},
    ] + [{"role": "user", "content": f"m{i}"} for i in range(25)]
    result = truncate_messages(msgs, window=20)
    assert result[0] == {"role": "system", "content": "sys1"}
    assert result[1] == {"role": "system", "content": "sys2"}
    assert result[2]["role"] == "system"  # sentinel
    assert TRUNCATION_SENTINEL in result[2]["content"]
    # last 20 user msgs follow
    user_msgs = [m for m in result[3:] if m["role"] == "user"]
    assert len(user_msgs) == 20
    assert user_msgs[0]["content"] == "m5"
    assert user_msgs[-1]["content"] == "m24"


def test_truncation_sentinel_content():
    assert "[Earlier conversation history truncated for context length]" in TRUNCATION_SENTINEL
    assert MAX_HISTORY_MESSAGES == 20


def test_truncate_keeps_exact_window_last_messages():
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(30)]
    result = truncate_messages(msgs, window=10)
    # no system msgs, so just sentinel + last 10
    assert len(result) == 1 + 10
    user_msgs = [m for m in result if m["role"] == "user"]
    assert user_msgs[0]["content"] == "m20"
    assert user_msgs[-1]["content"] == "m29"
