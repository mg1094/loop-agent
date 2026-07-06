# loop-agent Phase 2.1 Implementation Plan: FastAPI Server

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `AgentLoop` over HTTP via FastAPI so web clients and other services can call loop-agent without going through the CLI.

**Architecture:** A new `loop_agent/api/` package wraps the existing CLI helpers in FastAPI route handlers. Each request validates input via Pydantic, then calls into `commands._run_agent()` / `list_skills()` / `list_tools()` — no shared mutable state across requests. Launched with `uvicorn loop_agent.api.app:app`.

**Tech Stack:** Python 3.11+, `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `httpx>=0.27` (TestClient), `pydantic>=2.0`.

## Global Constraints

- Python `>=3.11`
- `langchain>=1.0.0,<2`
- `langchain-openai>=1.0.0,<2`
- `pydantic>=2.0.0`
- All request and response bodies are JSON.
- Error semantics: 4xx = client error (bad input), 5xx = unexpected server failure. Agent errors caught by the loop return 200 with `status: "error"`.
- No shared mutable state across requests. Every `/chat` call constructs a fresh `AgentLoop`.
- No streaming in Phase 2.1. Single-turn only.
- No auth / CORS / API key middleware. Single-tenant local server.
- No changes to existing CLI / agent / provider code beyond extracting helpers for shared use.
- Every task ends with a passing test and a git commit.
- Run commands via `.venv/Scripts/python.exe -m` (system Python lacks deps). See `loop-agent-venv` memory.

---

## File Structure

```
D:\code\loop-agent
├── loop_agent/
│   ├── api/                  # NEW
│   │   ├── __init__.py
│   │   ├── schemas.py        # Pydantic models
│   │   ├── routes.py         # FastAPI endpoints
│   │   └── app.py            # create_app() factory + module-level app
│   └── cli/
│       └── commands.py       # MODIFY: add helper aliases for shared use
├── tests/
│   └── test_api.py           # NEW
├── pyproject.toml            # MODIFY: add fastapi, uvicorn, httpx
└── README.md                 # MODIFY: add HTTP API section
```

---

### Task 1: Add FastAPI Dependencies

**Files:**
- Modify: `pyproject.toml:8-15`

**Interfaces:**
- Produces: installable `fastapi`, `uvicorn[standard]`, `httpx`

- [ ] **Step 1: Add deps to `pyproject.toml`**

Edit `pyproject.toml` dependencies block. New content:

```toml
dependencies = [
    "rich>=13.0.0",
    "langchain>=1.0.0,<2",
    "langchain-openai>=1.0.0,<2",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Install in venv**

Run: `.venv/Scripts/python.exe -m pip install -e ".[dev]"`
Expected: installs fastapi, uvicorn, httpx; no errors.

- [ ] **Step 3: Verify import**

Run: `.venv/Scripts/python.exe -c "import fastapi, uvicorn, httpx; print(fastapi.__version__)"`
Expected: prints a version string (e.g., `0.115.0`).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(deps): add fastapi, uvicorn, httpx"
```

---

### Task 2: Pydantic Schemas

**Files:**
- Create: `loop_agent/api/__init__.py`
- Create: `loop_agent/api/schemas.py`
- Create: `tests/test_api_schemas.py`

**Interfaces:**
- Produces: `ChatRequest`, `ChatResponse`, `SkillsResponse`, `ToolsResponse`, `HealthResponse`

- [ ] **Step 1: Write failing test**

Create `tests/test_api_schemas.py`:

```python
from pydantic import ValidationError
import pytest

from loop_agent.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SkillsResponse,
    ToolsResponse,
)


def test_chat_request_accepts_prompt():
    req = ChatRequest(prompt="hello")
    assert req.prompt == "hello"


def test_chat_request_rejects_empty_string():
    with pytest.raises(ValidationError):
        ChatRequest(prompt="")


def test_chat_request_rejects_missing_prompt():
    with pytest.raises(ValidationError):
        ChatRequest()


def test_chat_response_round_trip():
    resp = ChatResponse(status="success", content="hi", run_id="r1", run_dir="/tmp/r1")
    assert resp.status == "success"
    assert resp.content == "hi"


def test_skills_response_round_trip():
    resp = SkillsResponse(descriptions="### writing\n  - writing: desc")
    assert "writing" in resp.descriptions


def test_tools_response_round_trip():
    resp = ToolsResponse(tools=["echo", "read_file"])
    assert resp.tools == ["echo", "read_file"]


def test_health_response_round_trip():
    resp = HealthResponse(status="ok", version="0.1.0")
    assert resp.status == "ok"
    assert resp.version == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_schemas.py -v`
Expected: ImportError (module `loop_agent.api` does not exist yet).

- [ ] **Step 3: Create `loop_agent/api/__init__.py`**

```python
"""HTTP API for loop-agent."""
```

- [ ] **Step 4: Create `loop_agent/api/schemas.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field


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

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_schemas.py -v`
Expected: all 7 tests pass.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/api/ tests/test_api_schemas.py
git commit -m "feat(api): add Pydantic schemas"
```

---

### Task 3: Refactor `commands.py` for Shared Use

**Files:**
- Modify: `loop_agent/cli/commands.py`

**Interfaces:**
- Produces: `_run_agent`, `_load_env`, `list_skills`, `list_tools`, `run_command` (unchanged signatures; `list_tools` now returns `list[str]` instead of `str` for shared API use)

- [ ] **Step 1: Update `loop_agent/cli/commands.py`**

Replace the file contents with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.providers.chat import ChatLLM
from loop_agent.tools import build_registry


def _load_env() -> None:
    for candidate in [
        Path.home() / ".loop-agent" / ".env",
        Path.cwd() / ".env",
    ]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break


def _run_agent(user_message: str) -> Dict[str, Any]:
    _load_env()
    skills_loader = SkillsLoader()
    registry = build_registry(skills_loader=skills_loader)
    llm = ChatLLM()
    memory = WorkspaceMemory()
    loop = AgentLoop(registry, llm, memory)
    return loop.run(user_message)


def run_command(user_message: str) -> Dict[str, Any]:
    return _run_agent(user_message)


def list_skills() -> str:
    _load_env()
    loader = SkillsLoader()
    return loader.get_descriptions()


def list_tool_names() -> List[str]:
    _load_env()
    registry = build_registry()
    return sorted(registry.tool_names())


def list_tools() -> str:
    return "\n".join(list_tool_names())
```

Note: `list_tool_names()` is a new helper returning a sorted list of names (for the API). `list_tools()` keeps the newline-joined string form for the CLI.

- [ ] **Step 2: Run existing CLI test to verify it still passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli.py -v`
Expected: 1 test passes (`test_run_command_with_mock_loop`).

- [ ] **Step 3: Verify CLI still works**

Run: `.venv/Scripts/python.exe -m loop_agent.cli.main tools`
Expected: prints tool names one per line (`echo`, `load_skill`, `read_file`, `write_file`).

- [ ] **Step 4: Commit**

```bash
git add loop_agent/cli/commands.py
git commit -m "refactor(cli): extract list_tool_names() helper for shared use"
```

---

### Task 4: Routes — `/health`, `/skills`, `/tools`

**Files:**
- Create: `loop_agent/api/routes.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `HealthResponse`, `SkillsResponse`, `ToolsResponse` from `schemas`
- Consumes: `list_skills()`, `list_tool_names()` from `cli.commands`
- Produces: `router` with `GET /health`, `GET /skills`, `GET /tools`

- [ ] **Step 1: Write failing test (part A: `/health`)**

Create `tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from loop_agent.api.app import create_app
from loop_agent import __version__


def test_health():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -v`
Expected: ImportError (no `loop_agent.api.app` yet).

- [ ] **Step 3: Create `loop_agent/api/app.py`**

```python
from __future__ import annotations

from fastapi import FastAPI

from loop_agent import __version__
from loop_agent.api import routes


def create_app() -> FastAPI:
    app = FastAPI(title="loop-agent", version=__version__)
    app.include_router(routes.router)
    return app


app = create_app()
```

- [ ] **Step 4: Create `loop_agent/api/routes.py` (initial — `/health` only)**

```python
from __future__ import annotations

from fastapi import APIRouter

from loop_agent import __version__
from loop_agent.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py::test_health -v`
Expected: 1 test passes.

- [ ] **Step 6: Add `/skills` and `/tools` routes — write failing test**

Append to `tests/test_api.py`:

```python
def test_list_skills(monkeypatch):
    monkeypatch.setattr(
        "loop_agent.api.routes.list_skills",
        lambda: "### writing\n  - writing: test",
    )
    client = TestClient(create_app())
    resp = client.get("/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert "writing" in body["descriptions"]


def test_list_tools(monkeypatch):
    monkeypatch.setattr(
        "loop_agent.api.routes.list_tool_names",
        lambda: ["echo", "load_skill", "read_file", "write_file"],
    )
    client = TestClient(create_app())
    resp = client.get("/tools")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tools"] == ["echo", "load_skill", "read_file", "write_file"]
```

- [ ] **Step 7: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py::test_list_skills tests/test_api.py::test_list_tools -v`
Expected: ImportError or AttributeError (the routes don't exist yet).

- [ ] **Step 8: Extend `loop_agent/api/routes.py`**

Replace contents with:

```python
from __future__ import annotations

from fastapi import APIRouter

from loop_agent import __version__
from loop_agent.api.schemas import HealthResponse, SkillsResponse, ToolsResponse
from loop_agent.cli.commands import list_skills, list_tool_names

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
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -v`
Expected: 3 tests pass.

- [ ] **Step 10: Commit**

```bash
git add loop_agent/api/routes.py loop_agent/api/app.py tests/test_api.py
git commit -m "feat(api): add /health, /skills, /tools routes"
```

---

### Task 5: `/chat` Route

**Files:**
- Modify: `loop_agent/api/routes.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `ChatRequest`, `ChatResponse`
- Consumes: `_run_agent` from `cli.commands`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api.py`:

```python
def test_chat_success(monkeypatch):
    def fake_run(prompt: str) -> dict:
        return {
            "status": "success",
            "content": f"Echo: {prompt}",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
        }

    monkeypatch.setattr("loop_agent.api.routes._run_agent", fake_run)
    client = TestClient(create_app())
    resp = client.post("/chat", json={"prompt": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["content"] == "Echo: hello"
    assert body["run_id"] == "r1"
    assert body["run_dir"] == "/tmp/r1"


def test_chat_blank_prompt_returns_400(monkeypatch):
    called = []
    monkeypatch.setattr(
        "loop_agent.api.routes._run_agent",
        lambda p: called.append(p) or {"status": "success", "content": "", "run_id": "r", "run_dir": "/tmp/r"},
    )
    client = TestClient(create_app())
    resp = client.post("/chat", json={"prompt": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "prompt must not be blank"
    assert called == []  # run_agent NOT called for blank prompt


def test_chat_missing_prompt_returns_422():
    client = TestClient(create_app())
    resp = client.post("/chat", json={})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py::test_chat_success tests/test_api.py::test_chat_blank_prompt_returns_400 tests/test_api.py::test_chat_missing_prompt_returns_422 -v`
Expected: ImportError (no `/chat` route yet).

- [ ] **Step 3: Extend `loop_agent/api/routes.py` with `/chat`**

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
    result = _run_agent(req.prompt)
    return ChatResponse(
        status=result["status"],
        content=result["content"],
        run_id=result["run_id"],
        run_dir=result["run_dir"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Run full suite to confirm no regressions**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 22 existing tests + 7 schema tests + 6 API tests = 35 tests pass.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/api/routes.py tests/test_api.py
git commit -m "feat(api): add /chat route with validation"
```

---

### Task 6: README — HTTP API Section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add HTTP API section after the "Usage" section**

Insert this content after the `## Usage` section's closing `loop-agent tools` code block and before `## Test`:

```markdown
## HTTP API

Start the server:

```bash
uvicorn loop_agent.api.app:app --host 0.0.0.0 --port 8000
```

Endpoints:

```bash
# Health check
curl http://localhost:8000/health

# List available skills
curl http://localhost:8000/skills

# List available tools
curl http://localhost:8000/tools

# Run a single prompt
curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Use the echo tool to say hello"}'
```

Response shape for `/chat`:
```json
{
  "status": "success",
  "content": "hello",
  "run_id": "20260706_120000_a1b2c3",
  "run_dir": "runs/20260706_120000_a1b2c3"
}
```

`status` may be `success`, `empty`, `max_iterations`, `cancelled`, or `error`. Clients branch on `status`.
```

Also update the **Features** list to add a new bullet:

```markdown
- 🌐 **HTTP API** — FastAPI server exposing `/chat`, `/skills`, `/tools`, `/health`
```

And update the **Roadmap** section to remove the FastAPI item (now done):

```markdown
## Roadmap

- [ ] Streaming responses with proper SSE
- [ ] MCP server entry
- [ ] Persistent memory across runs
- [ ] Multi-agent orchestration
```

- [ ] **Step 2: Verify README renders**

Run: `.venv/Scripts/python.exe -c "import re; t=open('README.md',encoding='utf-8').read(); assert '/chat' in t and '/health' in t and 'uvicorn loop_agent.api.app:app' in t; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add HTTP API section to README"
```

---

### Task 7: End-to-End Smoke Test with Real LLM

**Files:**
- none (verification only)

- [ ] **Step 1: Start server in background**

Run: `.venv/Scripts/python.exe -m uvicorn loop_agent.api.app:app --host 127.0.0.1 --port 8765`
Expected: prints `Uvicorn running on http://127.0.0.1:8765` and stays running.
Run with `run_in_background: true`.

- [ ] **Step 2: Verify /health**

Run (in a new shell): `curl http://127.0.0.1:8765/health`
Expected: `{"status":"ok","version":"0.1.0"}`

- [ ] **Step 3: Verify /tools**

Run: `curl http://127.0.0.1:8765/tools`
Expected: `{"tools":["echo","load_skill","read_file","write_file"]}`

- [ ] **Step 4: Verify /chat with real LLM**

Run:
```bash
curl -X POST http://127.0.0.1:8765/chat \
     -H "Content-Type: application/json" \
     -d "{\"prompt\": \"使用 echo 工具回复 hello\"}"
```
Expected: JSON with `"status": "success"` and `"content": "hello"` (or similar reply).

- [ ] **Step 5: Verify blank prompt returns 400**

Run:
```bash
curl -X POST http://127.0.0.1:8765/chat \
     -H "Content-Type: application/json" \
     -d '{"prompt": "   "}'
```
Expected: HTTP 400 with `{"detail":"prompt must not be blank"}`.

- [ ] **Step 6: Stop the background server**

Use `TaskStop` on the background server task. Or kill the process by port if needed.

- [ ] **Step 7: Final full test suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 35 tests pass.

---

## Self-Review

### Spec Coverage

| Spec Section | Plan Task |
|--------------|-----------|
| File structure (api package) | Tasks 2, 4, 5 |
| `schemas.py` Pydantic models | Task 2 |
| `app.py` factory + module-level app | Task 4 |
| `routes.py` with /health, /skills, /tools, /chat | Tasks 4, 5 |
| Refactor `commands.py` for shared use | Task 3 |
| 4xx/5xx error semantics | Task 5 (blank → 400; missing → 422; agent error → 200) |
| `/chat` returns full dict | Task 5 |
| TestClient + mock tests | Tasks 2, 4, 5 |
| pyproject.toml deps | Task 1 |
| Running the server | Task 7 |
| README updates | Task 6 |

### Placeholder Scan

- No TBD/TODO.
- Every code step includes complete code.
- Every test step includes complete test code.
- Exact file paths provided.

### Type Consistency

- `_run_agent(prompt: str) -> Dict[str, Any]` — same signature in CLI and API.
- `list_tool_names() -> List[str]` — new helper, same return shape used in API.
- `ChatResponse(status, content, run_id, run_dir)` — fields match `AgentLoop.run()` dict keys.
- `HealthResponse(version)` — sourced from `loop_agent.__version__`.

### Out-of-Scope Confirmed

Phase 2.1 spec excludes SSE, multi-turn sessions, auth, CORS, async, persistent memory, multi-agent. None of these are in the plan.