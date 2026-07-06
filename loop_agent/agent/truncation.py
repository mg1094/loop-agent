from __future__ import annotations

from typing import List, Dict, Any

MAX_HISTORY_MESSAGES = 20
TRUNCATION_SENTINEL = "[Earlier conversation history truncated for context length]"


def truncate_messages(
    messages: List[Dict[str, Any]],
    window: int = MAX_HISTORY_MESSAGES,
) -> List[Dict[str, Any]]:
    """Keep all system messages. If non-system messages exceed `window`,
    prepend a sentinel system message and keep only the last `window` non-system
    messages.
    """
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    if len(non_system) <= window:
        return list(messages)

    truncated = list(system_msgs) + [
        {"role": "system", "content": TRUNCATION_SENTINEL}
    ] + non_system[-window:]
    return truncated
