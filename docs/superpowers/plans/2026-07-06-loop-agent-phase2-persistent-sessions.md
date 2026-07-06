# loop-agent Phase 2.2 Implementation Plan: Persistent Sessions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-turn session support so an agent remembers prior conversation context across `/chat` calls, persisted in a local SQLite file.

**Architecture:** A new `SessionStore` wraps stdlib `sqlite3` and persists `user` / `assistant` / `tool` messages keyed by `session_id`. `AgentLoop.run()` accepts an optional `session_id`; when provided, it loads prior messages, runs the ReAct loop as today, then saves the new turn. Long histories are truncated by `truncate_messages()` to keep context bounded — no LLM summarization. The API adds an optional `session_id` to `/chat` and two new endpoints (`GET/DELETE /sessions/{id}`).

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, FastAPI 0.110+, Pydantic v2.

## Global Constraints

- Python `>=3.11`
- `langchain>=1.0.0,<2`, `langchain-openai>=1.0.0,<2`, `pydantic>=2.0.0`
- **No new dependencies.** `sqlite3` is stdlib.
- All request/response bodies are JSON.
- Storage is local SQLite at `<cwd>/.sessions/sessions.db`.
- WorkspaceMemory stays in-memory and per-run; only message history is persisted.
- No LLM summarization — truncation uses a sentinel system message.
- No session expiry / cleanup.
- Backward-compatible: omitting `session_id` produces identical behavior to Phase 2.1.
- Every task ends with a passing test and a git commit.
- Run commands via `.venv/Scripts/python.exe -m` (system Python lacks deps).

---

## File Structure

```
D:\code\loop-agent
├── loop_agent/
│   ├── api/
│   │   ├── routes.py          # MODIFY
│   │   └── schemas.py         # MODIFY
│   ├── agent/
│   │   ├── loop.py            # MODIFY
│   │   └── truncation.py      # NEW
│   ├── cli/
│   │   └── commands.py        # MODIFY
│   └── storage/               # NEW
│       ├── __init__.py
│       └── session_store.py
├── tests/
│   ├── test_session_store.py  # NEW
│   ├── test_truncation.py     # NEW
│   ├── test_loop.py           # MODIFY (add 1 test)
│   └── test_api.py            # MODIFY (add 6 tests)
└── .gitignore                 # MODIFY (add .sessions/)
```

---

### Task 1: Truncation Helper

**Files:**
- Create: `loop_agent/agent/truncation.py`
- Create: `tests/test_truncation.py`

**Interfaces:**
- Produces: `truncate_messages(messages: list[dict], window: int = 20) -> list[dict]`
- Produces: `MAX_HISTORY_MESSAGES = 20`
- Produces: `TRUNCATION_SENTINEL = "[Earlier conversation history truncated for context length]"`

- [ ] **Step 1: Write failing tests**

Create `tests/test_truncation.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_truncation.py -v`
Expected: ImportError (module does not exist).

- [ ] **Step 3: Create `loop_agent/agent/truncation.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_truncation.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/agent/truncation.py tests/test_truncation.py
git commit -m "feat(agent): add truncate_messages() helper"
```

---

### Task 2: SessionStore — Schema and Round-Trip

**Files:**
- Create: `loop_agent/storage/__init__.py`
- Create: `loop_agent/storage/session_store.py`
- Create: `tests/test_session_store.py`

**Interfaces:**
- Produces: `SessionStore(db_path: Path)`
- Produces: `load_messages(session_id: str) -> list[dict]`
- Produces: `save_turn(session_id: str, messages: list[dict]) -> None`

- [ ] **Step 1: Write failing tests (part A — round-trip + load unknown)**

Create `tests/test_session_store.py`:

```python
import json
from pathlib import Path

from loop_agent.storage.session_store import SessionStore


def test_save_and_load_round_trip(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
        {"role": "tool", "tool_call_id": "t1", "name": "echo", "content": "ok"},
    ]
    store.save_turn("s1", msgs)
    loaded = store.load_messages("s1")
    assert loaded == msgs


def test_load_unknown_session_returns_empty(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    assert store.load_messages("nonexistent") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_session_store.py -v`
Expected: ImportError.

- [ ] **Step 3: Create `loop_agent/storage/__init__.py`**

```python
"""Persistence layer for loop-agent."""
```

- [ ] **Step 4: Create `loop_agent/storage/session_store.py`**

```python
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_DB_PATH = Path.cwd() / ".sessions" / "sessions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    name TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session_seq
    ON session_messages(session_id, seq);
"""


def _row_to_message(row: sqlite3.Row) -> Dict[str, Any]:
    role = row["role"]
    msg: Dict[str, Any] = {"role": role}
    if row["content"] is not None:
        msg["content"] = row["content"]
    if row["tool_calls"] is not None:
        msg["tool_calls"] = json.loads(row["tool_calls"])
    if row["tool_call_id"] is not None:
        msg["tool_call_id"] = row["tool_call_id"]
    if row["name"] is not None:
        msg["name"] = row["name"]
    return msg


class SessionStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def load_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT role, content, tool_calls, tool_call_id, name "
                "FROM session_messages WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            )
            return [_row_to_message(row) for row in cur.fetchall()]

    def save_turn(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        if not messages:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id, created_at, updated_at) "
                "VALUES(?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET updated_at = excluded.updated_at",
                (session_id, now, now),
            )
            cur = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM session_messages WHERE session_id = ?",
                (session_id,),
            )
            next_seq = cur.fetchone()["max_seq"] + 1
            rows = []
            for msg in messages:
                role = msg.get("role", "")
                if role not in ("user", "assistant", "tool"):
                    continue
                rows.append((
                    session_id,
                    next_seq,
                    role,
                    msg.get("content"),
                    json.dumps(msg["tool_calls"], ensure_ascii=False) if msg.get("tool_calls") is not None else None,
                    msg.get("tool_call_id"),
                    msg.get("name"),
                ))
                next_seq += 1
            if rows:
                conn.executemany(
                    "INSERT INTO session_messages(session_id, seq, role, content, tool_calls, tool_call_id, name) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
            conn.commit()

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return cur.rowcount > 0

    def list_sessions(self) -> List[str]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT session_id FROM sessions ORDER BY updated_at DESC"
            )
            return [row["session_id"] for row in cur.fetchall()]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_session_store.py -v`
Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/storage/ tests/test_session_store.py
git commit -m "feat(storage): add SessionStore with sqlite backend"
```

---

### Task 3: SessionStore — Append, Delete, List, Skip System

**Files:**
- Modify: `tests/test_session_store.py`

**Interfaces:**
- Consumes: `SessionStore` from Task 2

- [ ] **Step 1: Append tests**

Append to `tests/test_session_store.py`:

```python
def test_save_turn_appends(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    store.save_turn("s1", [{"role": "user", "content": "first"}])
    store.save_turn("s1", [{"role": "user", "content": "second"}])
    loaded = store.load_messages("s1")
    assert [m["content"] for m in loaded] == ["first", "second"]


def test_delete_session_removes_messages(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    store.save_turn("s1", [{"role": "user", "content": "hi"}])
    assert store.delete_session("s1") is True
    assert store.load_messages("s1") == []
    # second delete returns False
    assert store.delete_session("s1") is False


def test_list_sessions(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    store.save_turn("a", [{"role": "user", "content": "1"}])
    store.save_turn("b", [{"role": "user", "content": "2"}])
    sessions = store.list_sessions()
    assert "a" in sessions
    assert "b" in sessions


def test_save_turn_skips_system_role(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    store.save_turn("s1", [
        {"role": "system", "content": "should not persist"},
        {"role": "user", "content": "kept"},
    ])
    loaded = store.load_messages("s1")
    assert loaded == [{"role": "user", "content": "kept"}]
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_session_store.py -v`
Expected: 6 tests pass (2 from Task 2 + 4 new).

The implementation from Task 2 already covers these behaviors (`save_turn` filters by role, `delete_session` returns rowcount, `list_sessions` queries the table).

- [ ] **Step 3: Commit**

```bash
git add tests/test_session_store.py
git commit -m "test(storage): cover append, delete, list, system-skip"
```

---

### Task 4: AgentLoop Session Integration

**Files:**
- Modify: `loop_agent/agent/loop.py`
- Modify: `tests/test_loop.py`

**Interfaces:**
- Consumes: `SessionStore` from `loop_agent.storage.session_store`
- Consumes: `truncate_messages` from `loop_agent.agent.truncation`
- Produces: `AgentLoop(session_store=..., ...)` (optional kwarg)
- Produces: `AgentLoop.run(user_message, history=None, session_id="")` — loads prior when session_id + store present, saves new turn after

- [ ] **Step 1: Add a session-aware loop test (failing first)**

Append to `tests/test_loop.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import BaseTool, ToolRegistry
from loop_agent.providers.chat import ChatLLM, LLMResponse
from loop_agent.storage.session_store import SessionStore


class GreeterTool(BaseTool):
    name = "greet"
    description = "Greet"
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    def execute(self, *, name: str) -> str:
        return json.dumps({"result": f"hello {name}"})


def test_loop_persists_messages_when_session_store_provided(tmp_path: Path):
    registry = ToolRegistry()
    memory = WorkspaceMemory()
    store = SessionStore(tmp_path / "sessions.db")

    llm = MagicMock(spec=ChatLLM)
    llm.chat.side_effect = [
        LLMResponse(content="first reply", finish_reason="stop"),
        LLMResponse(content="second reply", finish_reason="stop"),
    ]

    loop = AgentLoop(registry, llm, memory, session_store=store)
    r1 = loop.run("first prompt", session_id="sess1")
    assert r1["status"] == "success"

    r2 = loop.run("second prompt", session_id="sess1")
    assert r2["status"] == "success"

    # store should contain both user messages and both assistant replies
    loaded = store.load_messages("sess1")
    assert [m["content"] for m in loaded if m["role"] == "user"] == [
        "first prompt", "second prompt"
    ]
    assert [m["content"] for m in loaded if m["role"] == "assistant"] == [
        "first reply", "second reply"
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_loop.py::test_loop_persists_messages_when_session_store_provided -v`
Expected: TypeError (`session_store` kwarg not supported).

- [ ] **Step 3: Update `loop_agent/agent/loop.py`**

Replace the file contents with:

```python
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from loop_agent.agent.context import ContextBuilder
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import ToolRegistry
from loop_agent.agent.trace import TraceWriter
from loop_agent.agent.truncation import truncate_messages
from loop_agent.providers.chat import ChatLLM

if TYPE_CHECKING:
    from loop_agent.storage.session_store import SessionStore

logger = logging.getLogger(__name__)
RUNS_DIR = Path("runs")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "30"))


def _estimate_tokens(messages: list) -> int:
    return len(json.dumps(messages, default=str, ensure_ascii=False)) // 4


class AgentLoop:
    def __init__(
        self,
        registry: ToolRegistry,
        llm: ChatLLM,
        memory: Optional[WorkspaceMemory] = None,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        max_iterations: int = MAX_ITERATIONS,
        session_store: Optional["SessionStore"] = None,
    ) -> None:
        self.registry = registry
        self.llm = llm
        self.memory = memory or WorkspaceMemory()
        self._event_callback = event_callback
        self.max_iterations = max_iterations
        self._cancel_event = threading.Event()
        self.session_store = session_store

    def cancel(self) -> None:
        self._cancel_event.set()

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if self._event_callback:
            self._event_callback(event_type, data)

    def _persist_new_turn(
        self,
        session_id: str,
        full_messages: List[Dict[str, Any]],
        prefix_len: int,
    ) -> None:
        if not self.session_store:
            return
        new_turn = [m for m in full_messages[prefix_len:] if m.get("role") in ("user", "assistant", "tool")]
        if new_turn:
            self.session_store.save_turn(session_id, new_turn)

    def run(
        self,
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        session_id: str = "",
    ) -> Dict[str, Any]:
        self._cancel_event.clear()

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self.memory.run_dir = str(run_dir)

        context = ContextBuilder(self.registry, self.memory)

        prior: List[Dict[str, Any]] = []
        if history:
            prior.extend(history)
        if session_id and self.session_store:
            loaded = self.session_store.load_messages(session_id)
            # existing history wins over loaded when both provided; otherwise use loaded
            if not prior:
                prior = loaded

        messages = context.build_messages(user_message, history=prior)
        prefix_len = len(messages)
        messages = truncate_messages(messages)

        trace = TraceWriter(run_dir)
        trace.write({"type": "start", "run_id": run_id, "prompt": user_message, "session_id": session_id})
        trace.write({"type": "message", "role": "user", "content": user_message})

        iteration = 0
        final_content = ""

        try:
            while iteration < self.max_iterations:
                if self._cancel_event.is_set():
                    trace.write({"type": "cancelled", "iter": iteration + 1})
                    self._persist_new_turn(session_id, messages, prefix_len)
                    return {"status": "cancelled", "content": "", "run_id": run_id, "run_dir": str(run_dir)}

                iteration += 1
                logger.info("ReAct iteration %d/%d", iteration, self.max_iterations)

                is_last = iteration == self.max_iterations
                tool_defs = None if is_last else self.registry.get_definitions()

                if is_last:
                    trace.write({"type": "forced_text_only", "iter": iteration})

                response = self.llm.chat(
                    messages,
                    tools=tool_defs,
                )

                if not response.has_tool_calls:
                    final_content = response.content or ""
                    if not final_content:
                        trace.write({"type": "empty_model_response", "iter": iteration})
                        self._persist_new_turn(session_id, messages, prefix_len)
                        return {"status": "empty", "content": "", "run_id": run_id, "run_dir": str(run_dir)}
                    messages.append({"role": "assistant", "content": final_content})
                    trace.write({"type": "final", "iter": iteration, "content": final_content})
                    self._persist_new_turn(session_id, messages, prefix_len)
                    return {"status": "success", "content": final_content, "run_id": run_id, "run_dir": str(run_dir)}

                assistant_msg = context.format_assistant_tool_calls(response.tool_calls)
                messages.append(assistant_msg)
                trace.write({"type": "assistant", "iter": iteration, "tool_calls": assistant_msg.get("tool_calls", [])})

                for tc in response.tool_calls:
                    result = self.registry.execute(tc.name, tc.arguments)
                    tool_msg = context.format_tool_result(tc.id, tc.name, result)
                    messages.append(tool_msg)
                    trace.write({"type": "tool_result", "iter": iteration, "name": tc.name, "content": result})
                    self.memory.increment(tc.name)
                    self._emit("tool_result", {"name": tc.name, "result": result})

            self._persist_new_turn(session_id, messages, prefix_len)
            return {"status": "max_iterations", "content": final_content, "run_id": run_id, "run_dir": str(run_dir)}

        except Exception as exc:
            logger.exception("AgentLoop failed")
            trace.write({"type": "error", "error": str(exc)})
            self._persist_new_turn(session_id, messages, prefix_len)
            return {"status": "error", "content": str(exc), "run_id": run_id, "run_dir": str(run_dir)}
```

Key changes:
- `__init__` accepts `session_store: Optional["SessionStore"] = None`
- `run` reads prior from `session_store.load_messages(session_id)` when both are set; explicit `history` arg wins if also provided
- After every return path (success / empty / cancelled / max_iterations / error), persist the new turn (user + assistant + tool messages) via `_persist_new_turn`
- Truncation applied to full `messages` before the loop starts (defensive: keeps prior + new bounded)

- [ ] **Step 4: Run loop tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_loop.py -v`
Expected: 2 tests pass (original + new session-aware one).

- [ ] **Step 5: Run full suite to confirm no regressions**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 41 tests pass (35 from Phase 2.1 + 5 truncation + 6 session store + 1 loop session = 47 total). Note: exact total is 35 + 5 + 6 + 1 = 47; existing loop test still 1, schemas 7, CLI 1, etc.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/agent/loop.py tests/test_loop.py
git commit -m "feat(loop): persist session messages via SessionStore"
```

---

### Task 5: CLI `_run_agent` Accepts `session_id`

**Files:**
- Modify: `loop_agent/cli/commands.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `_run_agent(user_message: str, session_id: str = "") -> Dict[str, Any]`

- [ ] **Step 1: Add CLI test for session_id passthrough**

Append to `tests/test_cli.py`:

```python
def test_run_command_with_session_id(monkeypatch):
    captured = []

    def fake_run(user_message, session_id=""):
        captured.append((user_message, session_id))
        return {"status": "success", "content": "ok", "run_id": "r", "run_dir": "/tmp"}

    monkeypatch.setattr("loop_agent.cli.commands._run_agent", fake_run)
    result = run_command("hi", session_id="sess-1")
    assert result["content"] == "ok"
    assert captured == [("hi", "sess-1")]
```

Note: this also requires updating `run_command` signature to accept and pass through `session_id`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli.py::test_run_command_with_session_id -v`
Expected: TypeError (run_command does not accept session_id).

- [ ] **Step 3: Update `loop_agent/cli/commands.py`**

Replace contents with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.providers.chat import ChatLLM
from loop_agent.storage.session_store import SessionStore
from loop_agent.tools import build_registry


def _load_env() -> None:
    for candidate in [
        Path.home() / ".loop-agent" / ".env",
        Path.cwd() / ".env",
    ]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break


def _run_agent(user_message: str, session_id: str = "") -> Dict[str, Any]:
    _load_env()
    skills_loader = SkillsLoader()
    registry = build_registry(skills_loader=skills_loader)
    llm = ChatLLM()
    memory = WorkspaceMemory()
    store = SessionStore()
    loop = AgentLoop(registry, llm, memory, session_store=store)
    return loop.run(user_message, session_id=session_id)


def run_command(user_message: str, session_id: str = "") -> Dict[str, Any]:
    return _run_agent(user_message, session_id=session_id)


def list_skills() -> str:
    _load_env()
    loader = SkillsLoader()
    return loader.get_descriptions()


def list_tool_names() -> List[str]:
    _load_env()
    registry = build_registry()
    return sorted(registry.tool_names)


def list_tools() -> str:
    return "\n".join(list_tool_names())
```

- [ ] **Step 4: Run CLI tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli.py -v`
Expected: 2 tests pass (original + new).

- [ ] **Step 5: Commit**

```bash
git add loop_agent/cli/commands.py tests/test_cli.py
git commit -m "feat(cli): _run_agent accepts session_id"
```

---

### Task 6: API Schemas — `session_id` field

**Files:**
- Modify: `loop_agent/api/schemas.py`
- Modify: `tests/test_api_schemas.py`

**Interfaces:**
- Produces: `ChatRequest(prompt, session_id="")`
- Produces: `ChatResponse(status, content, run_id, run_dir, session_id="")`

- [ ] **Step 1: Update schemas test**

Append to `tests/test_api_schemas.py`:

```python
from pydantic import ValidationError

from loop_agent.api.schemas import ChatRequest, ChatResponse


def test_chat_request_accepts_session_id():
    req = ChatRequest(prompt="hi", session_id="abc")
    assert req.session_id == "abc"


def test_chat_request_session_id_defaults_to_empty():
    req = ChatRequest(prompt="hi")
    assert req.session_id == ""


def test_chat_request_session_id_too_long():
    with pytest.raises(ValidationError):
        ChatRequest(prompt="hi", session_id="x" * 257)


def test_chat_response_session_id_field():
    resp = ChatResponse(
        status="success", content="hi", run_id="r1",
        run_dir="/tmp/r1", session_id="abc",
    )
    assert resp.session_id == "abc"
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_schemas.py -v`
Expected: TypeError or AssertionError on the new tests.

- [ ] **Step 3: Update `loop_agent/api/schemas.py`**

Replace contents with:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User prompt")
    session_id: str = Field(default="", max_length=256, description="Optional session ID")


class ChatResponse(BaseModel):
    status: str
    content: str
    run_id: str
    run_dir: str
    session_id: str = ""


class SkillsResponse(BaseModel):
    descriptions: str


class ToolsResponse(BaseModel):
    tools: list[str]


class HealthResponse(BaseModel):
    status: str
    version: str
```

- [ ] **Step 4: Run schema tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_schemas.py -v`
Expected: all 11 schema tests pass.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/api/schemas.py tests/test_api_schemas.py
git commit -m "feat(api): add session_id to ChatRequest/ChatResponse"
```

---

### Task 7: `/chat` Accepts `session_id`

**Files:**
- Modify: `loop_agent/api/routes.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces: `/chat` echoes `session_id` in response

- [ ] **Step 1: Update existing /chat test, add new session tests**

In `tests/test_api.py`, modify the existing `test_chat_success` to expect `session_id` in the response. Replace it with:

```python
def test_chat_success(monkeypatch):
    def fake_run(prompt: str, session_id: str = "") -> dict:
        return {
            "status": "success",
            "content": f"Echo: {prompt}",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
        }

    monkeypatch.setattr("loop_agent.cli.commands._run_agent", fake_run)
    client = TestClient(create_app())
    resp = client.post("/chat", json={"prompt": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["content"] == "Echo: hello"
    assert body["run_id"] == "r1"
    assert body["run_dir"] == "/tmp/r1"
    assert body["session_id"] == ""


def test_chat_with_session_id(monkeypatch):
    captured = []

    def fake_run(prompt: str, session_id: str = "") -> dict:
        captured.append((prompt, session_id))
        return {"status": "success", "content": "ok", "run_id": "r1", "run_dir": "/tmp/r1"}

    monkeypatch.setattr("loop_agent.cli.commands._run_agent", fake_run)
    client = TestClient(create_app())
    resp = client.post("/chat", json={"prompt": "hi", "session_id": "sess-1"})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "sess-1"
    assert captured == [("hi", "sess-1")]


def test_chat_session_id_too_long_returns_422():
    client = TestClient(create_app())
    resp = client.post("/chat", json={"prompt": "hi", "session_id": "x" * 257})
    assert resp.status_code == 422
```

Note: keep all other existing API tests unchanged.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -v`
Expected: existing `test_chat_success` fails (response shape changed); new tests fail.

- [ ] **Step 3: Update `loop_agent/api/routes.py`**

Replace contents with:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from loop_agent import __version__
from loop_agent.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SkillsResponse,
    ToolsResponse,
)
from loop_agent.cli.commands import _run_agent, list_skills, list_tool_names

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get("/skills", response_model=SkillsResponse)
def skills() -> SkillsResponse:
    return SkillsResponse(descriptions=list_skills())


@router.get("/tools", response_model=ToolsResponse)
def tools() -> ToolsResponse:
    return ToolsResponse(tools=list_tool_names())


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be blank")
    result = _run_agent(req.prompt, session_id=req.session_id)
    return ChatResponse(
        status=result["status"],
        content=result["content"],
        run_id=result["run_id"],
        run_dir=result["run_dir"],
        session_id=req.session_id,
    )
```

- [ ] **Step 4: Run API tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -v`
Expected: 8 tests pass (6 original + 2 new session-related).

- [ ] **Step 5: Commit**

```bash
git add loop_agent/api/routes.py tests/test_api.py
git commit -m "feat(api): /chat accepts and echoes session_id"
```

---

### Task 8: `GET /sessions/{id}` and `DELETE /sessions/{id}`

**Files:**
- Modify: `loop_agent/api/schemas.py`
- Modify: `loop_agent/api/routes.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces: `SessionMessagesResponse(session_id, messages)`
- Produces: `SessionDeleteResponse(session_id, deleted)`
- Produces: `GET /sessions/{session_id}`, `DELETE /sessions/{session_id}`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api.py`:

```python
from loop_agent.storage.session_store import SessionStore


def test_get_session_returns_messages(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    store = SessionStore(db)
    store.save_turn("sess-x", [{"role": "user", "content": "remember me"}])
    client = TestClient(create_app())
    resp = client.get("/sessions/sess-x")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "sess-x"
    assert body["messages"][0]["content"] == "remember me"


def test_get_unknown_session_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH",
        Path(tempfile.mkdtemp()) / "sessions.db",
    )
    client = TestClient(create_app())
    resp = client.get("/sessions/never-existed")
    assert resp.status_code == 200
    assert resp.json() == {"session_id": "never-existed", "messages": []}


def test_delete_session_removes_messages(tmp_path: Path, monkeypatch):
    db = tmp_path / "sessions.db"
    monkeypatch.setattr(
        "loop_agent.api.routes.DEFAULT_DB_PATH", db
    )
    store = SessionStore(db)
    store.save_turn("sess-del", [{"role": "user", "content": "x"}])
    client = TestClient(create_app())
    resp = client.delete("/sessions/sess-del")
    assert resp.status_code == 200
    assert resp.json() == {"session_id": "sess-del", "deleted": True}
    # second delete is False
    resp2 = client.delete("/sessions/sess-del")
    assert resp2.json()["deleted"] is False
```

Add the necessary imports at the top of `tests/test_api.py`:

```python
import tempfile
from pathlib import Path
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -k "session" -v`
Expected: ImportError or AttributeError (endpoints don't exist).

- [ ] **Step 3: Extend `loop_agent/api/schemas.py`**

Append:

```python
class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: list[dict]


class SessionDeleteResponse(BaseModel):
    session_id: str
    deleted: bool
```

- [ ] **Step 4: Extend `loop_agent/api/routes.py`**

Add imports and two endpoints. Replace contents with:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from loop_agent import __version__
from loop_agent.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SessionDeleteResponse,
    SessionMessagesResponse,
    SkillsResponse,
    ToolsResponse,
)
from loop_agent.cli.commands import _run_agent, list_skills, list_tool_names
from loop_agent.storage.session_store import DEFAULT_DB_PATH, SessionStore

router = APIRouter()


def _store() -> SessionStore:
    return SessionStore(DEFAULT_DB_PATH)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get("/skills", response_model=SkillsResponse)
def skills() -> SkillsResponse:
    return SkillsResponse(descriptions=list_skills())


@router.get("/tools", response_model=ToolsResponse)
def tools() -> ToolsResponse:
    return ToolsResponse(tools=list_tool_names())


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be blank")
    result = _run_agent(req.prompt, session_id=req.session_id)
    return ChatResponse(
        status=result["status"],
        content=result["content"],
        run_id=result["run_id"],
        run_dir=result["run_dir"],
        session_id=req.session_id,
    )


@router.get("/sessions/{session_id}", response_model=SessionMessagesResponse)
def get_session(session_id: str) -> SessionMessagesResponse:
    messages = _store().load_messages(session_id)
    return SessionMessagesResponse(session_id=session_id, messages=messages)


@router.delete("/sessions/{session_id}", response_model=SessionDeleteResponse)
def delete_session(session_id: str) -> SessionDeleteResponse:
    deleted = _store().delete_session(session_id)
    return SessionDeleteResponse(session_id=session_id, deleted=deleted)
```

- [ ] **Step 5: Run API tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -v`
Expected: 11 tests pass (8 from Task 7 + 3 new session-endpoint tests).

- [ ] **Step 6: Run full suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 35 (Phase 2.1) + 5 (truncation) + 6 (session_store) + 1 (loop) + 1 (cli) + 4 (schemas) + 3 (api session endpoints) = 55 tests pass.

- [ ] **Step 7: Commit**

```bash
git add loop_agent/api/ tests/test_api.py
git commit -m "feat(api): add GET/DELETE /sessions/{id} endpoints"
```

---

### Task 9: `.gitignore` for `.sessions/`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add `.sessions/` to gitignore**

Append to `.gitignore`:

```
.sessions/
```

- [ ] **Step 2: Verify untracked**

Run: `git status`
Expected: `.sessions/` does not appear as a candidate new file (or shows as ignored).

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore .sessions/"
```

---

### Task 10: README — Sessions Section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add Sessions section after HTTP API**

Insert after the `## HTTP API` section's response shape example (before `## Test`):

```markdown
## Sessions

Pass `session_id` on `/chat` to keep conversation history across requests. The agent sees prior user / assistant / tool messages from the same session.

```bash
# First turn
curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"prompt": "echo hello", "session_id": "demo"}'

# Second turn — agent sees the first prompt in context
curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"prompt": "now echo world", "session_id": "demo"}'

# Inspect
curl http://localhost:8000/sessions/demo

# Delete
curl -X DELETE http://localhost:8000/sessions/demo
```

Sessions are stored in a local SQLite database at `<cwd>/.sessions/sessions.db`. Histories beyond 20 messages are truncated with a sentinel marker — older context is dropped, not summarized. Omit `session_id` for stateless single-turn requests.
```

Also update the **Roadmap** section: remove the persistent-memory item:

```markdown
## Roadmap

- [ ] Streaming responses with proper SSE
- [ ] MCP server entry
- [ ] Multi-agent orchestration
```

- [ ] **Step 2: Update test count in README**

Change `35 tests cover...` to `55 tests cover tools, skills, context assembly, providers, trace writer, the agent loop, CLI commands, the HTTP API, persistent sessions, and message truncation.`

- [ ] **Step 3: Verify**

Run: `.venv/Scripts/python.exe -c "import re; t=open('README.md',encoding='utf-8').read(); assert '/sessions/' in t and 'session_id' in t; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add Sessions section, update test count"
```

---

## Self-Review

### Spec Coverage

| Spec Section | Plan Task |
|--------------|-----------|
| `truncate_messages` helper + constants | Task 1 |
| `SessionStore` class + schema | Tasks 2, 3 |
| `load_messages` / `save_turn` / `delete_session` / `list_sessions` | Tasks 2, 3 |
| System messages not persisted | Task 3 |
| `AgentLoop` accepts session_store + session_id | Task 4 |
| `AgentLoop` loads prior + persists new turn | Task 4 |
| Truncation applied in AgentLoop | Task 4 |
| CLI `_run_agent` accepts session_id | Task 5 |
| `ChatRequest.session_id` field (max_length=256) | Task 6 |
| `ChatResponse.session_id` field | Task 6 |
| `/chat` echoes session_id | Task 7 |
| `GET /sessions/{id}` | Task 8 |
| `DELETE /sessions/{id}` | Task 8 |
| Error handling (422 on too-long, 500 on sqlite, 200 on unknown session) | Tasks 6, 8 |
| `.gitignore` `.sessions/` | Task 9 |
| README sessions section | Task 10 |

### Placeholder Scan

- No TBD/TODO.
- Every code step includes complete code.
- Every test step includes complete test code.
- Exact file paths provided.

### Type Consistency

- `SessionStore(db_path: Path = DEFAULT_DB_PATH)` — Task 2
- `truncate_messages(messages: list[dict], window: int = 20) -> list[dict]` — Task 1
- `_run_agent(user_message: str, session_id: str = "") -> Dict[str, Any]` — Task 5 (matches what API calls)
- `AgentLoop(session_store: Optional["SessionStore"] = None, ...)` — Task 4
- `ChatRequest(prompt, session_id="")` — Task 6
- `ChatResponse(status, content, run_id, run_dir, session_id="")` — Task 6
- `SessionMessagesResponse(session_id, messages)` — Task 8
- `SessionDeleteResponse(session_id, deleted)` — Task 8

### Out-of-Scope Confirmed

- ❌ LLM summarization (not in plan)
- ❌ Workspace counters persistence (not in plan)
- ❌ Session metadata/tags/ttl (not in plan)
- ❌ Cross-session search (not in plan)
- ❌ Redis/Postgres (only sqlite, not in plan)
- ❌ Auto-cleanup (not in plan)