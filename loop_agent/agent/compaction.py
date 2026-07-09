from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.trace import TraceWriter

DEFAULT_TOKEN_THRESHOLD = 40_000
KEEP_RECENT_TOOL_RESULTS = 3
TOOL_RESULT_CLEAR_MIN_CHARS = 100
COLLAPSE_PRESERVE_RECENT = 6
COLLAPSE_TEXT_MIN_CHARS = 2_400
COLLAPSE_HEAD_CHARS = 900
COLLAPSE_TAIL_CHARS = 500
TAIL_TOKEN_BUDGET = 20_000


class SummaryLLM(Protocol):
    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Any:
        ...


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    return len(json.dumps(messages, default=str, ensure_ascii=False)) // 4


def microcompact(messages: List[Dict[str, Any]]) -> bool:
    """Clear older tool payloads while preserving recent tool results."""
    changed = False
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    if len(tool_msgs) <= KEEP_RECENT_TOOL_RESULTS:
        return False

    for msg in tool_msgs[:-KEEP_RECENT_TOOL_RESULTS]:
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > TOOL_RESULT_CLEAR_MIN_CHARS:
            msg["content"] = "[cleared]"
            changed = True
    return changed


def context_collapse(messages: List[Dict[str, Any]]) -> bool:
    """Fold long older text blocks without an LLM call."""
    if len(messages) <= COLLAPSE_PRESERVE_RECENT + 1:
        return False

    changed = False
    for msg in messages[1:-COLLAPSE_PRESERVE_RECENT]:
        content = msg.get("content")
        if not isinstance(content, str) or len(content) <= COLLAPSE_TEXT_MIN_CHARS:
            continue
        if content == "[cleared]":
            continue
        head = content[:COLLAPSE_HEAD_CHARS]
        tail = content[-COLLAPSE_TAIL_CHARS:]
        trimmed = len(content) - COLLAPSE_HEAD_CHARS - COLLAPSE_TAIL_CHARS
        msg["content"] = f"{head}\n\n...[{trimmed} chars collapsed]...\n\n{tail}"
        changed = True
    return changed


def repair_tool_pairs(messages: List[Dict[str, Any]]) -> None:
    """Keep assistant tool_call messages and tool result messages consistent."""
    call_ids: set[str] = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls", []) or []:
            tc_id = tc.get("id", "")
            if tc_id:
                call_ids.add(tc_id)

    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "tool" and msg.get("tool_call_id") not in call_ids:
            messages.pop(i)
        else:
            i += 1

    result_ids = {
        msg.get("tool_call_id", "")
        for msg in messages
        if msg.get("role") == "tool" and msg.get("tool_call_id")
    }
    inserts: list[tuple[int, Dict[str, Any]]] = []
    for idx, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls", []) or []:
            tc_id = tc.get("id", "")
            if not tc_id or tc_id in result_ids:
                continue
            stub = {
                "role": "tool",
                "tool_call_id": tc_id,
                "name": tc.get("function", {}).get("name", "unknown"),
                "content": "[Result from earlier context - see summary above]",
            }
            inserts.append((idx + 1, stub))
            result_ids.add(tc_id)

    for pos, stub in reversed(inserts):
        messages.insert(pos, stub)


STRUCTURED_SUMMARY_PROMPT = """\
Summarize this conversation for handoff to a fresh context window.
This summary is the ONLY context available - omitted information is lost.

Use this structure:

## Goal
What the user is trying to accomplish.

## Constraints & Preferences
User-stated requirements and preferences.

## Progress
Completed steps, key results, and current work.

## Decisions
Choices made and rationale.

## Relevant Files
File paths, run_dir, and artifacts.

## Pending Work
Unfinished requests still needing action.

## Critical Context
Specific numbers, errors, config values, and tool outputs that matter.

Preserve specific values, paths, and user intent.
{focus_section}
Conversation to summarize:
"""

FOCUS_SECTION = """\

FOCUS TOPIC: {topic}
Allocate most summary detail to this topic and compress unrelated content.
"""

ITERATIVE_UPDATE_PROMPT = """\
Update the existing handoff summary with new conversation turns.

PREVIOUS SUMMARY:
{previous_summary}

NEW TURNS TO INCORPORATE:
{new_turns}

Rules:
- Preserve existing critical information.
- Add new progress, decisions, files, and pending work.
- Keep the same general section structure.
{focus_section}
"""


class ContextCompactor:
    def __init__(
        self,
        llm: SummaryLLM,
        memory: WorkspaceMemory,
        token_threshold: int = DEFAULT_TOKEN_THRESHOLD,
        tail_token_budget: int = TAIL_TOKEN_BUDGET,
    ) -> None:
        self.llm = llm
        self.memory = memory
        self.token_threshold = token_threshold
        self.tail_token_budget = tail_token_budget
        self.previous_summary = ""

    @property
    def microcompact_threshold(self) -> int:
        return int(self.token_threshold * 0.5)

    @property
    def collapse_threshold(self) -> int:
        return int(self.token_threshold * 0.7)

    def compact_if_needed(
        self,
        messages: List[Dict[str, Any]],
        trace: Optional[TraceWriter] = None,
        iteration: int = 0,
    ) -> None:
        tokens = estimate_tokens(messages)
        if tokens > self.microcompact_threshold and microcompact(messages):
            tokens = estimate_tokens(messages)
            if trace:
                trace.write({"type": "microcompact", "iter": iteration, "tokens_after": tokens})

        if tokens > self.collapse_threshold and context_collapse(messages):
            tokens = estimate_tokens(messages)
            if trace:
                trace.write({"type": "context_collapse", "iter": iteration, "tokens_after": tokens})

        if tokens > self.token_threshold:
            self.auto_compact(messages, trace=trace, iteration=iteration)

    def auto_compact(
        self,
        messages: List[Dict[str, Any]],
        trace: Optional[TraceWriter] = None,
        focus_topic: str = "",
        iteration: int = 0,
    ) -> bool:
        if len(messages) <= 3:
            return False

        transcript_path = self._write_transcript(messages, trace)
        system_msg = messages[0]
        body = messages[1:]
        cut_idx = self._tail_cut_index(body)
        head = body[:cut_idx]
        tail = body[cut_idx:]
        if not head:
            if len(body) <= 2:
                return False
            cut_idx = max(1, len(body) // 2)
            head = body[:cut_idx]
            tail = body[cut_idx:]

        focus_section = FOCUS_SECTION.format(topic=focus_topic) if focus_topic else ""
        conv_text = json.dumps(head, default=str, ensure_ascii=False)[:80_000]
        if self.previous_summary:
            prompt = ITERATIVE_UPDATE_PROMPT.format(
                previous_summary=self.previous_summary,
                new_turns=conv_text,
                focus_section=focus_section,
            )
        else:
            prompt = STRUCTURED_SUMMARY_PROMPT.format(focus_section=focus_section) + conv_text

        response = self.llm.chat([{"role": "user", "content": prompt}])
        summary = getattr(response, "content", "") or ""
        if not summary.strip():
            return False
        self.previous_summary = summary

        tokens_before = estimate_tokens(messages)
        if trace:
            trace.write({
                "type": "compact",
                "iter": iteration,
                "tokens_before": tokens_before,
                "focus_topic": focus_topic or "(none)",
            })

        compressed = "[Conversation compressed - handoff summary."
        if transcript_path:
            compressed += f" Transcript: {transcript_path}"
        compressed += f"]\n\n{summary}"
        state_summary = self.memory.to_summary()
        if state_summary and state_summary != "(empty state)":
            compressed += f"\n\nCurrent agent state:\n{state_summary}"

        messages.clear()
        messages.append(system_msg)
        messages.append({
            "role": "user",
            "content": f"{compressed}\n\n<system>Continue from the summary above.</system>",
        })
        messages.extend(tail)
        repair_tool_pairs(messages)
        return True

    def _tail_cut_index(self, body: List[Dict[str, Any]]) -> int:
        accumulated = 0
        cut_idx = len(body)
        for i in range(len(body) - 1, -1, -1):
            content = body[i].get("content", "")
            msg_tokens = (len(str(content)) // 4) + 10
            if accumulated + msg_tokens > self.tail_token_budget:
                cut_idx = i + 1
                break
            accumulated += msg_tokens
            cut_idx = i

        while 0 < cut_idx < len(body) and body[cut_idx].get("role") == "tool":
            cut_idx += 1
        return cut_idx

    @staticmethod
    def _write_transcript(messages: List[Dict[str, Any]], trace: Optional[TraceWriter]) -> str:
        if not trace:
            return ""
        path = Path(trace.trace_dir) / f"transcript_{time.time_ns()}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for msg in messages:
                handle.write(json.dumps(msg, default=str, ensure_ascii=False) + "\n")
        return str(path)
