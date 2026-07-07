# Phase 2.4 / 3 — Supervisor Multi-Agent: Search-then-Write Report

> Status: DRAFT (awaiting user approval)
> Date: 2026-07-07
> Project: `D:\code\loop-agent`
> Predecessor: Phase 2.3 + BoCha web_search tool (commit `96daba2`)

## Goal

Add a **supervisor multi-agent mode** where a coordinator agent delegates
subtasks to specialized worker agents. The first supported workflow is
**research → write report**:

1. User asks for a report on a topic.
2. The supervisor delegates research to a `research` worker equipped with
   `web_search`.
3. The research worker returns a structured summary (title/url/snippet).
4. The supervisor delegates writing to a `writer` worker equipped with
   `read_file` / `write_file`.
5. The writer produces the final report.
6. The supervisor returns the report text to the user.

## Scope

In scope:

- A `Supervisor` class in `loop_agent/orchestration/supervisor.py`.
- Two worker registries:
  - `research`: `web_search` only
  - `writer`: `read_file`, `write_file`, `echo`
- Two supervisor tools:
  - `delegate(task: str, to: str)` — assign a task to a worker
  - `finalize(report: str)` — end the orchestration and return the report
- A new CLI command: `loop-agent run-supervised "..."`
- A new API endpoint: `POST /chat/supervised`
- Session persistence via existing `SessionStore` (supervisor + each worker
  shares the same `session_id` so the full trace is inspectable).
- Tests using mocked worker outputs (no real LLM / search calls).
- README update documenting the feature.

Out of scope (future):

- Dynamic worker creation / arbitrary worker names (only `research` and
  `writer` in MVP).
- Worker-to-worker direct communication (all routing goes through
  supervisor).
- More than one research or writing iteration in a single run (MVP does
  exactly one research → one write → finalize).
- Token streaming for the multi-agent flow.
- Different LLM models per worker (all workers use the same `ChatLLM`
  instance in MVP).

## Design

### Architecture

```
User
 │
 ▼
Supervisor.run(task)
 │
 ├─► Coordinator AgentLoop (tools: delegate, finalize)
 │      │
 │      ▼
 │   delegate(task="search X", to="research")
 │      │
 │      ▼
 │   Research AgentLoop (tools: web_search)
 │      │
 │      ▼
 │   returns structured research summary
 │      │
 │      ▼
 │   delegate(task="write report using ...", to="writer")
 │      │
 │      ▼
 │   Writer AgentLoop (tools: read_file, write_file, echo)
 │      │
 │      ▼
 │   returns final report text
 │      │
 │      ▼
 │   finalize(report="...")
 │
 ▼
{status, content, run_id, run_dir, session_id}
```

### Supervisor class

```python
class Supervisor:
    def __init__(
        self,
        llm: ChatLLM,
        session_store: SessionStore | None = None,
    ):
        self.llm = llm
        self.session_store = session_store
        self.workers = {
            "research": self._build_worker(["web_search"]),
            "writer": self._build_worker(["read_file", "write_file", "echo"]),
        }
        self.coordinator = self._build_coordinator()

    def run(self, task: str, session_id: str = "") -> dict:
        ...
```

### Worker registry construction

Each worker gets a filtered subset of the full registry:

```python
def _build_worker(self, tool_names: list[str]) -> AgentLoop:
    full_registry = build_registry()
    filtered = ToolRegistry()
    for name in tool_names:
        tool = full_registry.get(name)
        if tool:
            filtered.register(tool)
    return AgentLoop(filtered, self.llm, session_store=self.session_store)
```

### Coordinator tools

`delegate`:

```json
{
  "name": "delegate",
  "description": "Assign a subtask to a specialized worker. Workers: research (web search), writer (produce final report).",
  "parameters": {
    "type": "object",
    "properties": {
      "task": {"type": "string", "description": "Clear subtask description"},
      "to": {"type": "string", "enum": ["research", "writer"]}
    },
    "required": ["task", "to"]
  }
}
```

`finalize`:

```json
{
  "name": "finalize",
  "description": "Return the final report to the user and end the session.",
  "parameters": {
    "type": "object",
    "properties": {
      "report": {"type": "string"}
    },
    "required": ["report"]
  }
}
```

### Coordinator system prompt

```
You are a supervisor coordinating two workers:
- research: searches the web and returns a structured summary
- writer: writes the final report based on research summary

Rules:
1. First call delegate(task=..., to="research") to gather information.
2. Then call delegate(task=..., to="writer") with the research summary.
3. Finally call finalize(report=...) with the writer's output.
4. Do not answer the user directly.
```

### Worker outputs

Workers are standard `AgentLoop.run()` calls. Their `content` is returned to
the supervisor as a plain string. The supervisor includes that string in the
next `delegate` task prompt.

Example:

```
Research result:
- Title: ...
- URL: ...
- Snippet: ...

Now write a 500-word report.
```

### State / session

- Supervisor uses a single `session_id` for the entire run.
- Each worker call appends its user/assistant/tool messages to the same
  `SessionStore` (they all share `session_store`).
- This lets `GET /sessions/{id}` show the full multi-agent trace.

### Return shape

Same as `/chat`:

```json
{
  "status": "success",
  "content": "<final report>",
  "run_id": "...",
  "run_dir": "...",
  "session_id": ""
}
```

## CLI

```bash
loop-agent run-supervised "Write a report on Alibaba's 2024 ESG progress"
```

Optional flags to align with existing CLI:

```bash
loop-agent run-supervised "..." --session-id demo
```

## API

```bash
POST /chat/supervised
Content-Type: application/json

{
  "prompt": "Write a report on Alibaba's 2024 ESG progress",
  "session_id": "demo"
}
```

Response shape identical to `POST /chat`.

## Testing

`tests/test_supervisor.py` — no real LLM calls. Use monkeypatched
`AgentLoop.run` for coordinator and workers.

Test cases:

1. `test_supervisor_delegates_research_then_writer_then_finalizes` —
   mock both workers, assert coordinator calls them in order and returns
   final report.
2. `test_supervisor_worker_registry_has_only_allowed_tools` — assert
   research worker only has `web_search`, writer only has
   `read_file`/`write_file`/`echo`.
3. `test_supervisor_uses_session_store` — mock session store, assert
   `save_turn` is called for worker turns.
4. `test_supervisor_invalid_worker_name_returns_error` — if coordinator
   somehow calls unknown worker, return error status.
5. `test_cli_run_supervised_command` — CLI dispatches to supervisor.
6. `test_api_chat_supervised_endpoint` — `POST /chat/supervised` returns
   200 with correct shape.

## Files

Create:

- `loop_agent/orchestration/__init__.py`
- `loop_agent/orchestration/supervisor.py`
- `loop_agent/orchestration/tools.py` — `DelegateTool`, `FinalizeTool`
- `tests/test_supervisor.py`

Modify:

- `loop_agent/cli/commands.py` — add `run_supervised_command` / `_run_supervised`
- `loop_agent/cli/main.py` — add `run-supervised` subcommand
- `loop_agent/api/routes.py` — add `POST /chat/supervised`
- `loop_agent/api/schemas.py` — add `SupervisedChatRequest` / reuse
  `ChatRequest`, add response reuse `ChatResponse`
- `README.md` — add Multi-Agent section

No changes to:

- `AgentLoop` core (reuse as-is)
- `SessionStore` (reuse as-is)
- Existing `/chat`, `/chat/stream` endpoints

## Risks

| Risk | Mitigation |
|------|------------|
| Coordinator calls delegate twice to same worker or skips writer | Strong system prompt + max_iterations; MVP tests verify happy path |
| Worker output too long for next prompt | Truncate worker output to 4 KiB before passing to next delegate |
| Endless loop | Coordinator loop capped at `MAX_ITERATIONS` |
| SessionStore mixed messages from multiple agents | Each agent appends its own role-labeled messages; supervisor does not add extra user messages between workers (it passes results via prompt context) |

## Open questions

None blocking for MVP. Future enhancements: more workers, dynamic worker
selection, worker-specific LLM models, streaming supervisor events.