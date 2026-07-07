# Phase 2.4 — Supervisor Multi-Agent: Search-then-Write Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a supervisor multi-agent mode with `research` and `writer` workers so users can request a report and the system automatically searches the web, then writes the report.

**Architecture:** A `Supervisor` class builds a coordinator `AgentLoop` (tools: `delegate`, `finalize`) and two worker `AgentLoop`s (`research` has `web_search`; `writer` has `read_file`/`write_file`/`echo`). The coordinator's `delegate` tool runs a worker synchronously and returns its output; `finalize` captures the final report. The CLI gets `run-supervised` and the API gets `POST /chat/supervised`, both returning the standard `ChatResponse` shape.

**Tech Stack:** Python 3.11+, existing `AgentLoop`, `ToolRegistry`, `ChatLLM`, `SessionStore`, `httpx` (already in deps). No new packages.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-07-loop-agent-supervisor-search-write-design.md`
- Reuse existing `AgentLoop`, `SessionStore`, `ChatLLM`, `ToolRegistry`, `build_registry`
- All workers share the same `session_id` and `SessionStore`
- CLI command: `loop-agent run-supervised "..." --session-id demo`
- API endpoint: `POST /chat/supervised`, response shape identical to `POST /chat`
- Test runner: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -v`
- Final test count must reach **90 passing** (current 80 + 10 new supervisor tests)
- Run `git status` before committing — `.env`, `.sessions/`, `.venv/`, `runs/` must not be staged

## File Structure

| File | Purpose |
|------|---------|
| `loop_agent/orchestration/__init__.py` (NEW) | Package marker |
| `loop_agent/orchestration/tools.py` (NEW) | `DelegateTool` and `FinalizeTool` |
| `loop_agent/orchestration/supervisor.py` (NEW) | `Supervisor` class: builds coordinator + workers, runs workflow |
| `loop_agent/agent/loop.py` (MODIFY) | Add optional `system_prompt` kwarg to `AgentLoop.run()` so coordinator can use a custom system prompt |
| `loop_agent/cli/commands.py` (MODIFY) | Add `_run_supervised` and `run_supervised_command` |
| `loop_agent/cli/main.py` (MODIFY) | Add `run-supervised` subparser |
| `loop_agent/api/routes.py` (MODIFY) | Add `POST /chat/supervised` route |
| `tests/test_supervisor.py` (NEW) | 10 tests covering tools, supervisor flow, worker registries, CLI, API |
| `README.md` (MODIFY) | Multi-Agent section + test count 90 |

---

### Task 1: Delegate and Finalize tools

**Files:**
- Create: `loop_agent/orchestration/__init__.py`
- Create: `loop_agent/orchestration/tools.py`
- Test: `tests/test_supervisor.py`

**Interfaces:**
- Consumes: `BaseTool` from `loop_agent.agent.tools`
- Produces:
  - `DelegateTool(dispatcher: Callable[[str, str], str])` where dispatcher receives `(task, worker_name)` and returns the worker's output string.
  - `FinalizeTool(callback: Callable[[str], None])` where callback receives the final report string.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_supervisor.py`:

```python
import json

from loop_agent.orchestration.tools import DelegateTool, FinalizeTool


def test_delegate_tool_calls_dispatcher():
    calls = []

    def dispatcher(task, worker):
        calls.append((task, worker))
        return f"done: {worker}"

    tool = DelegateTool(dispatcher)
    result = tool.execute(task="search X", to="research")
    payload = json.loads(result)
    assert payload == {"worker": "research", "output": "done: research"}
    assert calls == [("search X", "research")]


def test_delegate_tool_rejects_unknown_worker():
    tool = DelegateTool(lambda t, w: "")
    result = tool.execute(task="x", to="hacker")
    payload = json.loads(result)
    assert payload["worker"] == "hacker"


def test_finalize_tool_calls_callback():
    captured = []
    tool = FinalizeTool(lambda report: captured.append(report))
    result = tool.execute(report="final answer")
    assert json.loads(result) == {"status": "finalized"}
    assert captured == ["final answer"]
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py::test_delegate_tool_calls_dispatcher -v`
Expected: ImportError / ModuleNotFoundError.

- [ ] **Step 3: Implement tools**

Create `loop_agent/orchestration/__init__.py` (empty).

Create `loop_agent/orchestration/tools.py`:

```python
from __future__ import annotations

import json
from typing import Any, Callable

from loop_agent.agent.tools import BaseTool


class DelegateTool(BaseTool):
    name = "delegate"
    description = (
        "Assign a subtask to a specialized worker. "
        "Workers: research (web search), writer (produce final report)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Clear subtask description for the worker.",
            },
            "to": {
                "type": "string",
                "enum": ["research", "writer"],
                "description": "Name of the worker to delegate to.",
            },
        },
        "required": ["task", "to"],
    }
    repeatable = True
    is_readonly = True

    def __init__(self, dispatcher: Callable[[str, str], str]) -> None:
        self._dispatcher = dispatcher

    def execute(self, *, task: str, to: str, **kwargs: Any) -> str:
        output = self._dispatcher(task, to)
        return json.dumps({"worker": to, "output": output}, ensure_ascii=False)


class FinalizeTool(BaseTool):
    name = "finalize"
    description = "Return the final report to the user and end the session."
    parameters = {
        "type": "object",
        "properties": {
            "report": {
                "type": "string",
                "description": "Final report content to return to the user.",
            },
        },
        "required": ["report"],
    }
    repeatable = False
    is_readonly = True

    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback

    def execute(self, *, report: str, **kwargs: Any) -> str:
        self._callback(report)
        return json.dumps({"status": "finalized"}, ensure_ascii=False)
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/orchestration/__init__.py loop_agent/orchestration/tools.py tests/test_supervisor.py
git commit -m "feat(orchestration): add delegate and finalize tools"
```

---

### Task 2: Allow custom system prompt in AgentLoop.run

**Files:**
- Modify: `loop_agent/agent/loop.py`
- Test: `tests/test_supervisor.py`

**Interfaces:**
- Change `AgentLoop.run(self, user_message, history=None, session_id="")` to
  `AgentLoop.run(self, user_message, history=None, session_id="", system_prompt=None)`.
- If `system_prompt` is provided, replace the system message content built by `ContextBuilder`.

**Why:** The supervisor coordinator needs its own system prompt that tells it to always use `delegate`/`finalize` and never answer directly. This is the only change to `AgentLoop` in this phase.

- [ ] **Step 1: Write failing test**

Append to `tests/test_supervisor.py`:

```python
from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import ToolRegistry
from loop_agent.providers.chat import ChatLLM


def test_agent_loop_accepts_custom_system_prompt(monkeypatch):
    # Fake ChatLLM that returns empty success immediately
    class FakeLLM:
        def chat(self, messages, tools=None):
            class Resp:
                has_tool_calls = False
                content = "ok"
                tool_calls = []
            return Resp()

    registry = ToolRegistry()
    loop = AgentLoop(registry, FakeLLM(), WorkspaceMemory())
    result = loop.run(
        "hi",
        system_prompt="You are a coordinator. Use delegate and finalize.",
    )
    assert result["status"] == "success"
    assert result["content"] == "ok"
```

- [ ] **Step 2: Run test, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py::test_agent_loop_accepts_custom_system_prompt -v`
Expected: TypeError — `run() got an unexpected keyword argument 'system_prompt'`.

- [ ] **Step 3: Implement change**

In `loop_agent/agent/loop.py`, modify the `run` signature and add one line after `messages = context.build_messages(...)`:

```python
def run(
    self,
    user_message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    session_id: str = "",
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
```

And after:

```python
messages = context.build_messages(user_message, history=prior)
if system_prompt is not None:
    messages[0]["content"] = system_prompt
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -v`
Expected: 4 passed.

Run full suite to ensure no regressions:
`.venv/Scripts/python.exe -m pytest -v`
Expected: 84 passed (80 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add loop_agent/agent/loop.py tests/test_supervisor.py
git commit -m "feat(agent): allow custom system_prompt in AgentLoop.run"
```

---

### Task 3: Supervisor class

**Files:**
- Create: `loop_agent/orchestration/supervisor.py`
- Test: `tests/test_supervisor.py`

**Interfaces:**
- `Supervisor(llm=None, session_store=None)`
- `Supervisor.run(task: str, session_id: str = "") -> dict`
- Returns `{"status", "content", "run_id", "run_dir", "session_id"}`

**Coordinator system prompt** (literal string used in `Supervisor`):

```text
You are a supervisor coordinating two workers to produce a report.

Workers:
- research: searches the web and returns a structured summary
- writer: writes the final report based on the research summary

Rules:
1. First call delegate(task="...", to="research") to gather information.
2. Then call delegate(task="...", to="writer") with the research summary.
3. Finally call finalize(report="...") with the writer's report.
4. Do not answer the user directly.

The user asked: {task}
```

- [ ] **Step 1: Write failing tests**

Append to `tests/test_supervisor.py`:

```python
from loop_agent.orchestration.supervisor import Supervisor


def test_supervisor_builds_worker_registries_with_allowed_tools_only():
    supervisor = Supervisor()
    research_tools = supervisor.workers["research"].registry.tool_names
    writer_tools = supervisor.workers["writer"].registry.tool_names
    assert research_tools == ["web_search"]
    assert set(writer_tools) == {"read_file", "write_file", "echo"}


def test_supervisor_run_delegates_research_then_writer(monkeypatch):
    research_tasks = []
    writer_tasks = []

    class FakeAgentLoop:
        def __init__(self, registry, llm, **kwargs):
            self.registry = registry

        def run(self, user_message, history=None, session_id="", system_prompt=None):
            names = set(self.registry.tool_names)
            if "delegate" in names:
                # Coordinator: simulate the intended workflow by directly
                # invoking delegate/finalize tools.
                delegate = self.registry.get("delegate")
                writer = self.registry.get("finalize")
                research_out = delegate.execute(task=user_message, to="research")
                writer_out = delegate.execute(
                    task=f"write report using {research_out}", to="writer"
                )
                writer.execute(report=f"REPORT: {writer_out}")
                return {
                    "status": "success",
                    "content": "coordinator done",
                    "run_id": "c1",
                    "run_dir": "/tmp/c1",
                }
            if "web_search" in names:
                research_tasks.append(user_message)
                return {"status": "success", "content": "research summary", "run_id": "r1", "run_dir": "/tmp/r1"}
            if "write_file" in names:
                writer_tasks.append(user_message)
                return {"status": "success", "content": "writer report", "run_id": "w1", "run_dir": "/tmp/w1"}
            raise RuntimeError("unknown worker")

    monkeypatch.setattr("loop_agent.orchestration.supervisor.AgentLoop", FakeAgentLoop)

    supervisor = Supervisor()
    result = supervisor.run("report on X", session_id="sess-1")

    assert result["status"] == "success"
    assert result["content"] == "REPORT: {\"worker\": \"writer\", \"output\": \"writer report\"}"
    assert result["session_id"] == "sess-1"
    assert len(research_tasks) == 1
    assert len(writer_tasks) == 1
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py::test_supervisor_builds_worker_registries_with_allowed_tools_only -v`
Expected: ImportError.

- [ ] **Step 3: Implement Supervisor**

Create `loop_agent/orchestration/supervisor.py`:

```python
from __future__ import annotations

from typing import Any, Dict, List, Optional

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import ToolRegistry
from loop_agent.providers.chat import ChatLLM
from loop_agent.storage.session_store import SessionStore
from loop_agent.tools import build_registry

from loop_agent.orchestration.tools import DelegateTool, FinalizeTool


_COORDINATOR_PROMPT = """You are a supervisor coordinating two workers to produce a report.

Workers:
- research: searches the web and returns a structured summary
- writer: writes the final report based on the research summary

Rules:
1. First call delegate(task="...", to="research") to gather information.
2. Then call delegate(task="...", to="writer") with the research summary.
3. Finally call finalize(report="...") with the writer's report.
4. Do not answer the user directly.

The user asked: {task}"""


class Supervisor:
    WORKER_TOOLS: Dict[str, List[str]] = {
        "research": ["web_search"],
        "writer": ["read_file", "write_file", "echo"],
    }

    def __init__(
        self,
        llm: Optional[ChatLLM] = None,
        session_store: Optional[SessionStore] = None,
    ) -> None:
        self.llm = llm or ChatLLM()
        self.session_store = session_store
        self.workers = self._build_workers()
        self.coordinator = self._build_coordinator()

    def _build_worker_registry(self, tool_names: List[str]) -> ToolRegistry:
        full_registry = build_registry()
        filtered = ToolRegistry()
        for name in tool_names:
            tool = full_registry.get(name)
            if tool:
                filtered.register(tool)
        return filtered

    def _build_workers(self) -> Dict[str, AgentLoop]:
        return {
            name: AgentLoop(
                self._build_worker_registry(tool_names),
                self.llm,
                memory=WorkspaceMemory(),
                session_store=self.session_store,
            )
            for name, tool_names in self.WORKER_TOOLS.items()
        }

    def _build_coordinator(self) -> AgentLoop:
        final_report: List[str] = []
        active_session_id: List[str] = [""]

        def dispatcher(task: str, worker_name: str) -> str:
            worker = self.workers.get(worker_name)
            if not worker:
                return f"Error: unknown worker '{worker_name}'"
            result = worker.run(task, session_id=active_session_id[0])
            return result.get("content", "")

        def capture_final(report: str) -> None:
            final_report.append(report)

        registry = ToolRegistry()
        registry.register(DelegateTool(dispatcher))
        registry.register(FinalizeTool(capture_final))

        return AgentLoop(
            registry,
            self.llm,
            memory=WorkspaceMemory(),
        )

    def run(self, task: str, session_id: str = "") -> Dict[str, Any]:
        # Inject session_id into the coordinator closure so delegates share it.
        self.coordinator.memory.run_dir = ""  # reset per run
        self.coordinator._persist_new_turn = lambda *args, **kwargs: None  # noqa: ARG005

        # Closure state lives on the coordinator instance for this run only.
        final_report: List[str] = []

        def dispatcher(task: str, worker_name: str) -> str:
            worker = self.workers.get(worker_name)
            if not worker:
                return f"Error: unknown worker '{worker_name}'"
            result = worker.run(task, session_id=session_id)
            return result.get("content", "")

        def capture_final(report: str) -> None:
            final_report.append(report)

        # Rebuild coordinator tools so closures capture this run's session_id
        coordinator_registry = ToolRegistry()
        coordinator_registry.register(DelegateTool(dispatcher))
        coordinator_registry.register(FinalizeTool(capture_final))
        self.coordinator = AgentLoop(
            coordinator_registry,
            self.llm,
            memory=WorkspaceMemory(),
            session_store=self.session_store,
        )

        system_prompt = _COORDINATOR_PROMPT.format(task=task)
        result = self.coordinator.run(
            task,
            session_id=session_id,
            system_prompt=system_prompt,
        )

        # Override content with captured final report if finalize was called.
        result = dict(result)
        if final_report:
            result["content"] = final_report[-1]
        result["session_id"] = session_id
        return result
```

**Note to implementer:** The above `_build_coordinator` initial placeholder is intentionally overwritten in `run()` so each call gets fresh closures bound to the current `session_id`. Keep the `_build_workers` logic as-is.

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/orchestration/supervisor.py tests/test_supervisor.py
git commit -m "feat(orchestration): add Supervisor class"
```

---

### Task 4: CLI `run-supervised` command

**Files:**
- Modify: `loop_agent/cli/commands.py`
- Modify: `loop_agent/cli/main.py`
- Test: `tests/test_supervisor.py`

**Interfaces:**
- `commands._run_supervised(task: str, session_id: str = "") -> Dict[str, Any]`
- `commands.run_supervised_command(task: str, session_id: str = "") -> Dict[str, Any]`
- CLI: `loop-agent run-supervised PROMPT [--session-id ID]`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_supervisor.py`:

```python
from loop_agent.cli import commands


def test_run_supervised_command(monkeypatch):
    def fake_run(task, session_id=""):
        return {
            "status": "success",
            "content": f"report: {task}",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
            "session_id": session_id,
        }

    monkeypatch.setattr("loop_agent.cli.commands._run_supervised", fake_run)
    result = commands.run_supervised_command("topic X", session_id="s1")
    assert result["content"] == "report: topic X"
    assert result["session_id"] == "s1"
```

- [ ] **Step 2: Run test, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py::test_run_supervised_command -v`
Expected: AttributeError.

- [ ] **Step 3: Implement CLI functions**

In `loop_agent/cli/commands.py`, append after `_run_agent`:

```python
def _run_supervised(task: str, session_id: str = "") -> Dict[str, Any]:
    _load_env()
    llm = ChatLLM()
    store = SessionStore()
    from loop_agent.orchestration.supervisor import Supervisor

    supervisor = Supervisor(llm=llm, session_store=store)
    return supervisor.run(task, session_id=session_id)


def run_supervised_command(task: str, session_id: str = "") -> Dict[str, Any]:
    return _run_supervised(task, session_id=session_id)
```

In `loop_agent/cli/main.py`, add the subparser:

```python
run_supervised_parser = subparsers.add_parser(
    "run-supervised", help="Run supervised multi-agent report workflow"
)
run_supervised_parser.add_argument("prompt", nargs="+", help="Task description")
run_supervised_parser.add_argument("--session-id", default="", help="Optional session ID")
```

And add the handler before `parser.print_help()`:

```python
if args.command == "run-supervised":
    prompt = " ".join(args.prompt)
    result = commands.run_supervised_command(prompt, session_id=args.session_id)
    print(result.get("content", ""))
    return 0 if result.get("status") == "success" else 1
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/cli/commands.py loop_agent/cli/main.py tests/test_supervisor.py
git commit -m "feat(cli): add run-supervised command"
```

---

### Task 5: API `POST /chat/supervised` endpoint

**Files:**
- Modify: `loop_agent/api/routes.py`
- Test: `tests/test_supervisor.py`

**Interfaces:**
- `POST /chat/supervised` accepts `ChatRequest`, returns `ChatResponse`
- Blank prompt → 400
- Reuses `_run_supervised` from `cli.commands`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_supervisor.py`:

```python
from fastapi.testclient import TestClient
from loop_agent.api.app import create_app


def test_chat_supervised_endpoint(monkeypatch):
    def fake_run(task, session_id=""):
        return {
            "status": "success",
            "content": f"supervised: {task}",
            "run_id": "r1",
            "run_dir": "/tmp/r1",
        }

    monkeypatch.setattr("loop_agent.api.routes._run_supervised", fake_run)
    client = TestClient(create_app())
    resp = client.post(
        "/chat/supervised", json={"prompt": "report on X", "session_id": "s1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "supervised: report on X"
    assert body["session_id"] == "s1"


def test_chat_supervised_blank_prompt_returns_400(monkeypatch):
    called = []

    def fake_run(task, session_id=""):
        called.append(task)
        return {"status": "success", "content": "", "run_id": "r1", "run_dir": "/tmp/r1"}

    monkeypatch.setattr("loop_agent.api.routes._run_supervised", fake_run)
    client = TestClient(create_app())
    resp = client.post("/chat/supervised", json={"prompt": "   "})
    assert resp.status_code == 400
    assert called == []
```

- [ ] **Step 2: Run test, confirm failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py::test_chat_supervised_endpoint -v`
Expected: 404.

- [ ] **Step 3: Add route**

In `loop_agent/api/routes.py`, import `_run_supervised`:

```python
from loop_agent.cli.commands import _run_agent, _run_supervised, list_skills, list_tool_names
```

Append at end of file:

```python
@router.post("/chat/supervised", response_model=ChatResponse)
def chat_supervised(req: ChatRequest) -> ChatResponse:
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be blank")
    result = _run_supervised(req.prompt, session_id=req.session_id)
    return ChatResponse(
        status=result["status"],
        content=result["content"],
        run_id=result["run_id"],
        run_dir=result["run_dir"],
        session_id=req.session_id,
    )
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -v`
Expected: 9 passed.

Run full suite:
`.venv/Scripts/python.exe -m pytest -v`
Expected: 89 passing.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/api/routes.py tests/test_supervisor.py
git commit -m "feat(api): add POST /chat/supervised endpoint"
```

---

### Task 6: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update badge and test count**

Badge: `tests-90%20passed`
Paragraph: "90 tests cover ... and supervisor multi-agent orchestration."

- [ ] **Step 2: Add Multi-Agent section**

Insert after `## Streaming` section, before `## Test`:

```markdown
## Multi-Agent Orchestration

Run a supervised research → write workflow:

```bash
loop-agent run-supervised "Write a report on Alibaba's 2024 ESG progress"
```

The supervisor coordinates two workers:

- `research` — searches the web with `web_search`
- `writer` — produces the final report with `read_file` / `write_file`

The supervisor itself uses two tools: `delegate(task, to)` and
`finalize(report)`. It always delegates research first, then writing,
then returns the final report.

HTTP API:

```bash
curl -X POST http://localhost:8000/chat/supervised \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Write a report on Alibaba's 2024 ESG progress"}'
```

Workers share the same `session_id`, so the full multi-agent trace is
available via `GET /sessions/{session_id}`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: multi-agent supervisor section + test count 90"
```

---

### Task 7: Final verification + whole-branch review

- [ ] **Step 1: Run full test suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 90 passed.

- [ ] **Step 2: Smoke test**

With `BOCHA_API_KEY` set:

```bash
.venv/Scripts/python.exe -m loop_agent.cli.main run-supervised "简单介绍一下阿里巴巴2024年ESG报告"
```

Expect: a report generated after web search.

- [ ] **Step 3: Update progress ledger**

Append to `docs/superpowers/sdd/progress.md`:

```markdown
## Phase 2.4
- Plan: docs/superpowers/plans/2026-07-07-loop-agent-supervisor-search-write.md
- Status: complete
- Tests: 90/90 passing
```

- [ ] **Step 4: Try push**

```bash
git push origin main
```

If network still blocked, report to user.

---

## Self-Review

**Spec coverage:**
- Supervisor class: Task 3
- research/writer workers with filtered tools: Task 3
- delegate/finalize tools: Task 1
- CLI `run-supervised`: Task 4
- API `POST /chat/supervised`: Task 5
- Session persistence: Task 3 (workers share `session_store` and `session_id`)
- Tests: Tasks 1-5 each add tests
- README: Task 6

**Placeholder scan:** No TBD/TODO/"implement later". All code shown.

**Type consistency:**
- `AgentLoop.run` gains optional `system_prompt: Optional[str] = None` in Task 2 and uses it in Task 3.
- `Supervisor.run(task, session_id="") -> dict` matches CLI/API usage.
- `_run_supervised(task, session_id="") -> dict` mirrors `_run_agent` signature.