from unittest.mock import MagicMock

from loop_agent.agent.compaction import (
    ContextCompactor,
    context_collapse,
    microcompact,
    repair_tool_pairs,
)
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.providers.chat import LLMResponse


def test_microcompact_clears_old_tool_results_only():
    messages = [{"role": "system", "content": "sys"}]
    for idx in range(5):
        messages.append({"role": "tool", "content": f"payload-{idx}-" + ("x" * 150)})

    changed = microcompact(messages)

    assert changed is True
    assert messages[1]["content"] == "[cleared]"
    assert messages[2]["content"] == "[cleared]"
    assert messages[3]["content"].startswith("payload-2")
    assert messages[5]["content"].startswith("payload-4")


def test_context_collapse_preserves_head_and_tail():
    long_text = "a" * 1000 + "b" * 2000 + "c" * 800
    messages = [{"role": "system", "content": "sys"}]
    messages.append({"role": "user", "content": long_text})
    messages.extend({"role": "assistant", "content": f"recent-{idx}"} for idx in range(6))

    changed = context_collapse(messages)

    assert changed is True
    collapsed = messages[1]["content"]
    assert collapsed.startswith("a" * 900)
    assert "chars collapsed" in collapsed
    assert collapsed.endswith("c" * 500)


def test_auto_compact_replaces_old_head_with_summary():
    llm = MagicMock()
    llm.chat.return_value = LLMResponse(content="summary of old context")
    messages = [{"role": "system", "content": "sys"}] + [
        {"role": "user", "content": "old " + ("x" * 100)} for _ in range(8)
    ]
    messages.append({"role": "user", "content": "recent"})

    compactor = ContextCompactor(llm, WorkspaceMemory(), token_threshold=100, tail_token_budget=20)
    changed = compactor.auto_compact(messages)

    assert changed is True
    assert messages[0] == {"role": "system", "content": "sys"}
    assert "summary of old context" in messages[1]["content"]
    assert messages[-1]["content"] == "recent"
    assert compactor.previous_summary == "summary of old context"


def test_repair_tool_pairs_inserts_stub_for_missing_result():
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": "{}"},
                }
            ],
        },
    ]

    repair_tool_pairs(messages)

    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_call_id"] == "call-1"
    assert "summary above" in messages[2]["content"]
