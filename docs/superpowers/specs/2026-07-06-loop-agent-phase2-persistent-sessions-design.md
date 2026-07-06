# loop-agent Phase 2.2 Design Spec: Persistent Sessions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan after this spec is approved.

**Goal:** Add multi-turn session support so an agent remembers prior conversation context across `/chat` calls, persisted in SQLite on disk.

**Architecture:** A new `loop_agent/storage/session_store.py` provides a `SessionStore` class that wraps a local SQLite database. `AgentLoop.run()` gains an optional `session_id` parameter; when provided, it loads prior messages before the run and appends the new turn after. The CLI and HTTP `/chat` surface a new optional `session_id` field. When `session_id` is omitted, behavior is unchanged from Phase 2.1. Long histories are truncated to a fixed window to prevent context-length blowup; LLM summarization is out of scope.

**Tech Stack:** Python 3.11+ stdlib `sqlite3` (no new dependencies), FastAPI 0.110+.

## Global Constraints

- Python `>=3.11`
- `langchain>=1.0.0,<2`
- `langchain-openai>=1.0.0,<2`
- `pydantic>=2.0.0`
- **No new dependencies.** Use Python stdlib `sqlite3`.
- **All request/response bodies are JSON.**
- **Storage is local file SQLite** at `<cwd>/.sessions/sessions.db`. No external DB.
- **Sessions are scoped per working directory.** The DB path is derived from `cwd`, not from `~/.loop-agent/`. Multiple projects on the same machine each have their own session DB.
- **WorkspaceMemory stays in-memory and per-run.** Only message history is persisted (matches the brainstorming decision).
- **No LLM summarization.** When messages exceed the window, truncate with a sentinel system message.
- **No session expiry / cleanup.** Sessions live until explicitly deleted.
- **Backward-compatible.** A `/chat` call without `session_id` behaves identically to Phase 2.1.
- **Every task ends with a passing test and a git commit.**

---

## File Structure

```
D:\code\loop-agent
├── loop_agent/
│   ├── api/
│   │   ├── routes.py          # MODIFY: /chat accepts session_id; new /sessions endpoints
│   │   └── schemas.py         # MODIFY: ChatRequest/Response add session_id
│   ├── agent/
│   │   ├── loop.py            # MODIFY: AgentLoop.run accepts session_id, loads+appends history
│   │   └── truncation.py      # NEW: truncate_messages() helper
│   ├── cli/
│   │   └── commands.py        # MODIFY: _run_agent accepts session_id
│   └── storage/               # NEW
│       ├── __init__.py
│       └── session_store.py   # SessionStore (sqlite3)
├── tests/
│   ├── test_session_store.py  # NEW
│   ├── test_truncation.py     # NEW
│   ├── test_loop.py           # MODIFY: add session-aware test
│   └── test_api.py            # MODIFY: add session-aware API tests
└── docs/superpowers/
    ├── specs/2026-07-06-loop-agent-phase2-persistent-sessions-design.md  (this file)
    └── plans/2026-07-06-loop-agent-phase2-persistent-sessions.md          (plan)
```

---

## Components

### `loop_agent/storage/session_store.py`

```python
class SessionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:  # CREATE TABLE statements above

    def load_messages(self, session_id: str) -> list[dict]:
        """Return all messages for session ordered by seq ASC.
        Unknown session returns []. Each row becomes an OpenAI-format dict.
        """

    def save_turn(self, session_id: str, messages: list[dict]) -> None:
        """Append messages to the session. Creates the session row if new.
        seq is computed as MAX(seq)+1 within the session. Idempotent for empty input.
        """

    def delete_session(self, session_id: str) -> None:
        """Remove session and all its messages."""

    def list_sessions(self) -> list[str]:
        """Return all session_ids, ordered by updated_at DESC."""
```

**Schema:**
```sql
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
```

**`save_turn` contract:**
- Insert/update the `sessions` row with `updated_at = now`.
- For each message: insert a row with `seq = previous_max_seq + i + 1`.
- Only persist `role` in {`user`, `assistant`, `tool`}. The system prompt and the truncation sentinel are **not** persisted.
- `tool_calls` is JSON-encoded when present; `tool_call_id` and `name` populate the `tool` row.

**DB path default:** `<cwd>/.sessions/sessions.db`. Module-level constant `DEFAULT_DB_PATH = Path.cwd() / ".sessions" / "sessions.db"`.

### `loop_agent/agent/truncation.py`

```python
MAX_HISTORY_MESSAGES = 20  # overridable via env HISTORY_WINDOW

def truncate_messages(messages: list[dict], window: int = MAX_HISTORY_MESSAGES) -> list[dict]:
    """Keep system messages always. If non-system > window, prepend a truncation sentinel
    and keep only the last `window` non-system messages.
    """
```

**Algorithm:**
1. Split messages into `[system_messages, non_system_messages]`.
2. If `len(non_system_messages) <= window`: return `messages` unchanged.
3. Else: `truncated = system_messages + [SENTINEL] + non_system_messages[-window:]`.
4. SENTINEL: `{"role": "system", "content": "[Earlier conversation history truncated for context length]"}`.

### `loop_agent/agent/loop.py` (modify)

`AgentLoop.__init__` accepts an optional `session_store: Optional[SessionStore] = None` and `session_id: str = ""` (also settable via `run()`).

`AgentLoop.run(user_message, history=None, session_id="")` flow:
1. If `session_id` and `session_store`: load `prior = store.load_messages(session_id)`.
2. Build messages via `ContextBuilder.build_messages(user_message, history=prior)`.
3. Run ReAct loop as today. Capture all assistant and tool messages appended during the loop.
4. After loop completes (success / error / max_iterations / empty): extract the new turn's `user` + `assistant` + `tool` messages (everything after the original system prompt and prior history) and call `store.save_turn(session_id, new_turn_messages)`.
5. Return the result dict unchanged.

The `new_turn_messages` extraction walks the final `messages` list and slices off the prefix equal to `len(system) + len(prior)`.

### `loop_agent/cli/commands.py` (modify)

`_run_agent(user_message: str, session_id: str = "") -> Dict[str, Any]`:
- Build a `SessionStore` at the default DB path.
- Pass it + `session_id` into `AgentLoop`.
- Return the result dict unchanged (no `session_id` in dict yet — the API layer adds it).

### `loop_agent/api/schemas.py` (modify)

```python
class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    session_id: str = Field(default="", max_length=256)

class ChatResponse(BaseModel):
    status: str
    content: str
    run_id: str
    run_dir: str
    session_id: str = ""   # echoed back when caller provided one
```

Validation rules on `session_id`:
- `max_length=256` — too long → 422
- No whitespace-only check at Pydantic layer (allow it for simplicity; loader treats it as unknown session and returns [])
- Leading/trailing whitespace not stripped automatically; clients should send clean IDs

### `loop_agent/api/routes.py` (modify)

`POST /chat`:
- Accept `req.session_id`.
- Call `_run_agent(req.prompt, session_id=req.session_id)`.
- Build response with `session_id=req.session_id` echoed back.

`GET /sessions/{session_id}`:
- Returns `{"session_id": ..., "messages": [...]}` for debugging. Uses the same default DB path.

`DELETE /sessions/{session_id}`:
- Removes the session. Returns `{"deleted": true|false}`.

---

## API Contract

### `POST /chat` (extended)

Request (with session):
```json
{"prompt": "echo hello", "session_id": "user-abc"}
```

Response:
```json
{
  "status": "success",
  "content": "hello",
  "run_id": "20260706_120000_a1b2c3",
  "run_dir": "runs/20260706_120000_a1b2c3",
  "session_id": "user-abc"
}
```

Request (no session, backward compatible):
```json
{"prompt": "echo hello"}
```

Response: same shape as Phase 2.1, `session_id` is `""`.

### `GET /sessions/{session_id}`

```http
GET /sessions/user-abc
```
Response:
```json
{
  "session_id": "user-abc",
  "messages": [
    {"role": "user", "content": "echo hello"},
    {"role": "assistant", "content": "..."},
    {"role": "tool", "tool_call_id": "...", "name": "echo", "content": "..."}
  ]
}
```

Unknown session → 200 with `{"session_id": "...", "messages": []}`.

### `DELETE /sessions/{session_id}`

```http
DELETE /sessions/user-abc
```
Response:
```json
{"session_id": "user-abc", "deleted": true}
```

Unknown session → `{"session_id": "...", "deleted": false}`.

---

## Data Flow

```
POST /chat {prompt, session_id}
    │
    ▼
route handler
    │
    ├─→ SessionStore.load_messages(session_id)         [if session_id given]
    │       ↓
    │   prior_messages
    │
    ├─→ AgentLoop.run(prompt, session_id=...)
    │       ├─→ ContextBuilder.build_messages(prompt, history=prior_messages)
    │       ├─→ ReAct loop (existing)
    │       ├─→ Slice off new turn from final messages
    │       └─→ SessionStore.save_turn(session_id, new_turn)  [if session_id]
    │
    └─→ ChatResponse(status, content, run_id, run_dir, session_id)
```

For truncation: applied inside `AgentLoop` after build_messages, before first LLM call.

---

## Error Handling

| Failure | HTTP | Body |
|---------|------|------|
| `session_id` longer than 256 chars | 422 | FastAPI default |
| Unknown session_id on `GET /sessions/{id}` | 200 | `{"messages": []}` (not 404) |
| Unknown session_id on `DELETE` | 200 | `{"deleted": false}` |
| sqlite error (disk full, permission) | 500 | FastAPI default |

---

## Testing

`tests/test_session_store.py` uses `tmp_path` for the DB:

| # | Test |
|---|------|
| 1 | `test_save_and_load_round_trip` |
| 2 | `test_load_unknown_session_returns_empty` |
| 3 | `test_save_turn_appends` |
| 4 | `test_delete_session_removes_messages` |
| 5 | `test_list_sessions` |
| 6 | `test_save_turn_skips_system_role` |

`tests/test_truncation.py`:

| # | Test |
|---|------|
| 1 | `test_no_truncation_when_under_window` |
| 2 | `test_truncate_when_over_window` |
| 3 | `test_system_messages_preserved` |
| 4 | `test_truncation_sentinel_content` |

`tests/test_loop.py` (add):

| # | Test |
|---|------|
| 1 | `test_loop_persists_messages_when_session_store_provided` |

`tests/test_api.py` (add):

| # | Test |
|---|------|
| 1 | `test_chat_with_session_id_passes_to_run_agent` |
| 2 | `test_chat_response_includes_session_id` |
| 3 | `test_chat_without_session_id_backward_compatible` |
| 4 | `test_get_session_returns_messages` |
| 5 | `test_delete_session_removes_messages` |
| 6 | `test_chat_session_id_too_long_returns_422` |

Mock pattern for API tests: `monkeypatch.setattr("loop_agent.cli.commands._run_agent", lambda prompt, session_id="": {...})`.

---

## Storage Location & Cleanup

- DB path: `<cwd>/.sessions/sessions.db` (auto-created).
- `.sessions/` should be added to `.gitignore` so test artifacts don't get committed.
- `.gitignore` update: add `.sessions/`.

---

## Out of Scope (Phase 2.2)

- ❌ LLM summarization
- ❌ Workspace counters persistence
- ❌ Session metadata (rename, tag, ttl)
- ❌ Cross-session search
- ❌ Redis / Postgres / external DB backends
- ❌ Auto-expiry / cleanup
- ❌ Authentication / per-user session isolation
- ❌ Streaming with sessions (SSE phase)

---

## Success Criteria

1. `pytest tests/ -v` shows all 35 existing + ~17 new tests passing
2. CLI: two consecutive `loop-agent run --session-id X "echo a"` and `loop-agent run --session-id X "echo b"` — second run sees the first user message in context (verified via `--debug` flag or trace file, optional)
3. API: two consecutive `POST /chat {prompt, session_id: "X"}` calls — second response references first turn's content
4. `GET /sessions/X` returns the accumulated messages
5. `DELETE /sessions/X` removes them
6. No `session_id` → identical to Phase 2.1 behavior
7. `.sessions/` is git-ignored