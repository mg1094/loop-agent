# loop-agent Phase 2.1 Design Spec: FastAPI Server

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan after this spec is approved.

**Goal:** Expose the existing `AgentLoop` over HTTP via FastAPI so that web clients, scripts, and other services can call loop-agent without going through the CLI.

**Architecture:** A new `loop_agent/api/` package wraps the existing CLI command helpers in FastAPI route handlers. The handler layer is thin — it parses requests, calls into the same `commands._run_agent()` logic, and returns the dict. No state is shared across requests; each `/chat` call builds a fresh registry / LLM / loop.

**Tech Stack:** `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `httpx>=0.27`, `pydantic>=2.0`.

## Global Constraints

- Python `>=3.11` (project floor, unchanged from Phase 1)
- `langchain>=1.0.0,<2` (project floor, unchanged)
- **All request and response bodies are JSON.**
- **Error semantics:** 4xx = client error (bad input), 5xx = unexpected server failure. Agent errors that the loop catches become `200 OK` with `status: "error"` in the body, so clients have one success path.
- **No shared mutable state across requests.** Every `/chat` call constructs a fresh `AgentLoop`.
- **No streaming in Phase 2.1.** Single-turn only. SSE is a separate phase.
- **No auth / CORS / API key middleware.** Single-tenant local server.
- **No changes to existing CLI or agent code** beyond extracting the shared `_run_agent()` helper.
- **Every task ends with a passing test and a git commit.**

---

## File Structure

```
D:\code\loop-agent
├── loop_agent/
│   ├── api/                  # NEW
│   │   ├── __init__.py
│   │   ├── app.py            # FastAPI app factory
│   │   ├── routes.py         # /chat, /skills, /tools, /health
│   │   └── schemas.py        # Pydantic request/response models
│   ├── cli/
│   │   └── commands.py       # MODIFY: extract _run_agent() and _load_env() to api/_run_agent.py (or keep in cli and import)
│   ├── agent/                # unchanged
│   ├── providers/            # unchanged
│   ├── tools/                # unchanged
│   └── skills/               # unchanged
├── tests/
│   ├── test_api.py           # NEW
│   └── ...                   # existing tests unchanged
├── pyproject.toml            # MODIFY: add fastapi, uvicorn, httpx
└── docs/superpowers/
    ├── specs/2026-07-06-loop-agent-phase2-fastapi-design.md  (this file)
    └── plans/2026-07-06-loop-agent-phase2-fastapi.md          (plan, written next)
```

---

## Components

### `loop_agent/api/schemas.py`

Pydantic models for request / response validation.

```python
class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User prompt")

class ChatResponse(BaseModel):
    status: str
    content: str
    run_id: str
    run_dir: str

class SkillsResponse(BaseModel):
    descriptions: str

class ToolsResponse(BaseModel):
    tools: list[str]

class HealthResponse(BaseModel):
    status: str
    version: str
```

`ChatRequest.prompt` uses `min_length=1` so empty strings are rejected at the Pydantic layer with 422. Whitespace-only prompts are accepted at this layer (Pydantic does not strip) and rejected at the route handler with 400, since whitespace-only is a user-visible error.

### `loop_agent/api/app.py`

Factory function `create_app() -> FastAPI` that returns a configured app. Route handlers live in `routes.py` and are registered via `app.include_router()`. This factory exists so tests can build a fresh app with overridden dependencies.

```python
def create_app() -> FastAPI:
    app = FastAPI(title="loop-agent", version="0.1.0")
    app.include_router(routes.router)
    return app

app = create_app()  # module-level for `uvicorn loop_agent.api.app:app`
```

### `loop_agent/api/routes.py`

```python
from fastapi import APIRouter, HTTPException
from loop_agent.api.schemas import (
    ChatRequest, ChatResponse,
    SkillsResponse, ToolsResponse, HealthResponse,
)

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse: ...

@router.get("/skills", response_model=SkillsResponse)
def list_skills() -> SkillsResponse: ...

@router.get("/tools", response_model=ToolsResponse)
def list_tools() -> ToolsResponse: ...

@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be blank")
    return ChatResponse(**_run_agent(req.prompt))
```

`_run_agent()` is imported from `loop_agent.cli.commands` to avoid duplicating the env-loading / registry / loop wiring. This keeps the CLI and the API in sync — both call into the same code path.

### Refactor: `loop_agent/cli/commands.py`

Move the helper body to a shared location or have `api/routes.py` import it directly. The plan chooses **direct import** — `api/routes.py` does `from loop_agent.cli.commands import _run_agent, list_skills_helper, list_tools_helper`. The CLI keeps its existing public functions (`run_command`, `list_skills`, `list_tools`) which delegate to the same helpers. This is the minimum change.

---

## API Contract

### `GET /health`

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"status": "ok", "version": "0.1.0"}
```

### `GET /skills`

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"descriptions": "\n### writing\n  - writing: Help the user write..."}
```

### `GET /tools`

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"tools": ["echo", "load_skill", "read_file", "write_file"]}
```

Tool order is sorted alphabetically for stable output.

### `POST /chat`

Request:
```json
{"prompt": "Use echo to say hello"}
```

Success response (200):
```json
{
  "status": "success",
  "content": "hello",
  "run_id": "20260706_120000_a1b2c3",
  "run_dir": "runs/20260706_120000_a1b2c3"
}
```

The response body is the full dict from `AgentLoop.run()`. Possible `status` values: `success`, `empty`, `max_iterations`, `cancelled`, `error`. Clients branch on `status`.

Empty-prompt validation (400):
```json
{"detail": "prompt must not be blank"}
```

Missing-field validation (422, FastAPI default):
```json
{"detail": [{"loc": ["body", "prompt"], "msg": "field required", ...}]}
```

Agent-loop caught errors (e.g., provider 401) return 200 with `status: "error"` so the HTTP layer stays thin:
```json
{
  "status": "error",
  "content": "provider_stream_error provider=dashscope model=qwen-plus-latest: AuthenticationError: ...",
  "run_id": "...",
  "run_dir": "..."
}
```

---

## Data Flow

```
HTTP Request
    │
    ▼
FastAPI route handler (routes.py)
    │   validates request body (Pydantic → 422 on bad shape)
    │   validates business rules (blank check → 400)
    ▼
_run_agent(prompt)  [imported from cli.commands]
    │   loads .env
    │   builds SkillsLoader, ToolRegistry, ChatLLM, WorkspaceMemory, AgentLoop
    │   calls loop.run(prompt) → dict
    ▼
ChatResponse(status, content, run_id, run_dir)
    │
    ▼
HTTP 200 + JSON
```

---

## Error Handling

| Failure | HTTP | Body shape |
|---------|------|------------|
| Missing `prompt` field | 422 | FastAPI default validation error |
| `prompt` is empty string | 422 | Pydantic `min_length=1` |
| `prompt` is whitespace only | 400 | `{"detail": "prompt must not be blank"}` |
| LLM provider failure (caught by loop) | 200 | `{"status": "error", "content": "...", ...}` |
| Unexpected exception in route handler | 500 | `{"detail": "..."}` |

The split between 400 (whitespace) and 422 (empty string) is intentional: Pydantic's `min_length=1` already rejects empty strings at the schema layer with 422, so the 400 path only catches whitespace which Pydantic does not see as invalid.

---

## Testing

`tests/test_api.py` uses `fastapi.testclient.TestClient` (which wraps `httpx`). All tests mock `_run_agent` / `_load_env` via `monkeypatch` to avoid LLM calls.

| # | Test | What it verifies |
|---|------|------------------|
| 1 | `test_health` | `GET /health` returns 200, `status=ok`, `version=0.1.0` |
| 2 | `test_list_skills` | `GET /skills` returns 200, descriptions mention `writing` |
| 3 | `test_list_tools` | `GET /tools` returns 200, contains `echo` |
| 4 | `test_chat_success` | `POST /chat` with mocked `_run_agent` returns full dict shape |
| 5 | `test_chat_blank_prompt_returns_400` | whitespace-only prompt → 400 |
| 6 | `test_chat_missing_prompt_returns_422` | body `{}` → 422 |

Mock pattern:
```python
def fake_run(prompt: str) -> dict:
    return {"status": "success", "content": f"Echo: {prompt}",
            "run_id": "r1", "run_dir": "/tmp/r1"}

monkeypatch.setattr("loop_agent.api.routes._run_agent", fake_run)
```

---

## Dependencies

`pyproject.toml` `[project.dependencies]` add:
```toml
"fastapi>=0.110",
"uvicorn[standard]>=0.27",
"httpx>=0.27",
```

`httpx` is required because `fastapi.testclient` depends on it. `uvicorn[standard]` pulls in `websockets`, `watchfiles` (for `--reload`), `python-dotenv`, etc.

---

## Running the Server

```bash
uvicorn loop_agent.api.app:app --host 0.0.0.0 --port 8000
```

Then in another shell:
```bash
curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Use the echo tool to say hello"}'

curl http://localhost:8000/tools
curl http://localhost:8000/skills
curl http://localhost:8000/health
```

---

## Out of Scope (Phase 2.1)

- ❌ SSE streaming (`/chat/stream`) — separate phase, requires real AgentLoop refactor
- ❌ Multi-turn sessions / `session_id` — needs persistent memory phase first
- ❌ Auth / API keys / rate limiting
- ❌ CORS configuration (add when a web frontend exists)
- ❌ Async endpoints (`/chat` blocks until loop completes; acceptable for single-user local server)
- ❌ Persistent memory across requests
- ❌ Multi-agent orchestration

---

## Success Criteria

1. `uvicorn loop_agent.api.app:app` starts without error
2. `curl /health` returns `{"status": "ok", ...}`
3. `curl -X POST /chat -d '{"prompt": "echo hello"}'` (with valid `.env`) returns `{"status": "success", "content": "hello", ...}`
4. `curl -X POST /chat -d '{}'` returns 422
5. `curl -X POST /chat -d '{"prompt": "   "}'` returns 400
6. `pytest tests/ -v` shows all 22 existing tests + 6 new API tests passing
7. README updated with a "HTTP API" section showing curl examples