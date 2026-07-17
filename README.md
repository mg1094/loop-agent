# loop-agent

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![LangChain](https://img.shields.io/badge/LangChain-1.0+-green.svg)](https://python.langchain.com/)
[![Tests](https://img.shields.io/badge/tests-201%20passed-brightgreen.svg)](#test)
[![Code style](https://img.shields.io/badge/code%20style-clean-orange.svg)](#)

A lightweight, provider-agnostic **ReAct agent framework** in Python — hand-written agent loop, auto-discovered tools, on-demand skill loading, and a pluggable LLM layer. Inspired by [Vibe-Trading](https://github.com), distilled down to the core building blocks for any agent use case, not just finance.

## Why loop-agent?

Most agent frameworks are either too heavy (LangGraph complexity, vendor lock-in) or too thin (DIY from scratch every time). `loop-agent` sits in the middle: a transparent, readable implementation of the **ReAct pattern** you can extend in an afternoon.

- **No graph engine** — just a `while` loop and a trace log you can inspect
- **Tools are auto-discovered** — subclass `BaseTool`, drop the file in, done
- **Skills are Markdown** — write instructions in YAML + body, load on demand
- **Provider-neutral** — works with OpenAI, DeepSeek, DashScope/Qwen, Moonshot, Gemini, Groq, Ollama, anything OpenAI-compatible
- **Built-in tracing** — every run writes a JSONL trace you can replay

## Features

- 🤖 **ReAct loop** (`AgentLoop`) — custom while-loop, not LangGraph StateGraph
- 🛠️ **Tools** (`BaseTool` + `ToolRegistry`) — subclass and auto-discover
- 📚 **Skills** (`SkillsLoader`) — Markdown + YAML frontmatter, loaded on demand
- 🧠 **ContextBuilder** — assembles the system prompt with tool + skill descriptions
- 🔌 **Providers** — LangChain `ChatOpenAI` works with any OpenAI-compatible API
- 📝 **TraceWriter** — per-run JSONL trace under `runs/<run_id>/trace.jsonl`
- 💾 **WorkspaceMemory** — per-run counters and state
- ⌨️ **CLI** — `loop-agent run ...`, `loop-agent skills`, `loop-agent tools`
- 🌐 **HTTP API** — FastAPI server exposing `/chat`, `/chat/stream`, `/skills`, `/tools`, `/health`
- 🔍 **Web search** — built-in `web_search` tool powered by BoCha AI (opt-in via `BOCHA_API_KEY`)

## Install

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # Linux/macOS
pip install -e ".[dev]"
```

## Configure

Copy `.env.example` to `.env` and set your provider credentials:

```ini
LANGCHAIN_PROVIDER=dashscope
LANGCHAIN_MODEL_NAME=qwen-plus-latest
DASHSCOPE_API_KEY=sk-your-key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
BOCHA_API_KEY=your-bocha-api-key  # optional, enables web_search tool
```

Supported providers: `openai`, `deepseek`, `dashscope`/`qwen`, `moonshot`, `gemini`, `groq`, `ollama`.

### CORS for browser clients

The HTTP server ships with a CORS middleware that defaults to **localhost only**:

- `http://localhost:*`
- `http://127.0.0.1:*`
- `https://localhost:*`
- `https://127.0.0.1:*`

This is enough for a local Vite / Next.js dev server to call `/chat` and `/chat/stream`. To allow a deployed origin, set:

```bash
export LOOP_AGENT_CORS_ORIGINS="https://app.example.com,https://admin.example.com"
```

Credentials and SSE headers are already enabled. Unknown origins receive a `400 Bad Request` on preflight.

## Usage

```bash
loop-agent run "Use the echo tool to say hello"
loop-agent skills
loop-agent tools
```

Additional CLI commands:

```bash
loop-agent --version

# Sessions
loop-agent sessions list
loop-agent sessions search serverless --limit 10
loop-agent sessions delete demo

# Run a single tool for quick debugging
loop-agent tools run echo --arg message=hello

# Replay a run trace in human-readable form
loop-agent trace 20260709_120000_abcdef
# or just the suffix if it's unique
loop-agent trace abcdef
```

The `trace` command reads `runs/<run_id>/trace.jsonl` and prints each entry on one line. `tool_error` entries are highlighted so failed tool calls stand out from ordinary `tool_result` lines.

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
  "run_dir": "runs/20260706_120000_a1b2c3",
  "session_id": ""
}
```

`status` may be `success`, `empty`, `max_iterations`, `cancelled`, or `error`. Clients branch on `status`.

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

Sessions are stored in a local SQLite database at `<cwd>/.sessions/sessions.db`. Runtime context is compacted under token pressure: old tool results are pruned, long older messages are folded, and large histories are summarized into a handoff block while preserving recent context. The model can also call `compact(focus_topic=...)` to request compression explicitly. Omit `session_id` for stateless single-turn requests.

### Session list & search

```bash
# All sessions, most-recently-updated first
curl http://localhost:8000/sessions
# -> {"sessions": [{"session_id": "demo", "created_at": "...", "updated_at": "...", "message_count": 4}, ...]}

# Substring search across all session messages
curl 'http://localhost:8000/sessions/search?q=serverless&limit=10'
# -> {"query": "serverless", "hits": [{"session_id": "beta", "updated_at": "...", "match_count": 2}, ...]}
```

`limit` is clamped to `[1, 200]` server-side. Matches are case-insensitive (`LIKE`) and ranked by `match_count` then `updated_at`. Future versions may upgrade to SQLite FTS5 without breaking the API surface.

## Sandbox (file tools)

`read_file` and `write_file` are sandboxed by default to two roots:

- `<cwd>` — wherever you launched the agent from
- `<cwd>/runs` — agent output, one folder per `run_id`

Paths are resolved symlink-aware before the check, so `../` escapes and bind-mount attempts both fail with `"path X is outside allowed roots: ..."`. A small built-in deny-list also blocks reads against `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.loop-agent/.env`, `/etc/`, and `/var/run/`. To opt back into legacy unbounded behaviour, set:

```bash
export LOOP_AGENT_UNRESTRICTED_FILES=1
```

Custom registries (e.g. inside your own scripts) can pass their own allow-list:

```python
from pathlib import Path
from loop_agent.tools import build_registry

registry = build_registry(allowed_roots=[Path("/data/projects")])
```

## LLM retries

`ChatLLM.chat()` and `stream_chat()` retry transient failures with exponential backoff + full jitter:

- Retryable: HTTP `408`, `429`, `5xx`, no-status network errors, `ConnectionError`, `TimeoutError`
- Not retried: other `4xx` (auth, bad request, etc.) — surfaced immediately
- Defaults: 3 retries, base delay 0.5s, max delay 8s
- Honors `should_cancel` between attempts; forwards an `on_retry(attempt, exc, jitter)` hook for observability
- Override per call: `llm.chat(messages, max_retries=5, base_delay=1.0, max_delay=16.0)`
## Streaming

`/chat/stream` returns `text/event-stream` so clients see per-iteration progress instead of waiting for the full run.

```bash
curl -N -X POST http://localhost:8000/chat/stream \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Use the echo tool to say hello", "session_id": "demo"}'
```

Events emitted (one `data: <json>\n\n` line each, envelope fields at top level):

| `type`            | When                                |
|-------------------|-------------------------------------|
| `run_start`       | First event                         |
| `iteration_start` | Each ReAct loop iteration begins    |
| `tool_result`     | Each tool call finishes             |
| `tool_progress`   | Per-phase progress from a long tool |
| `final`           | Run finished — mirrors `/chat`      |
| `error`           | Only on unrecoverable exception     |

`final` always carries `status`, `content`, `run_id`, `run_dir`, and `session_id` — same shape as `POST /chat`'s JSON response. Session persistence behavior matches `/chat`: pass `session_id`, prior messages are loaded and the new turn is saved.

`tool_progress` is emitted by tools that take more than a fraction of a second — currently `web_search` (sending query / response received / parsed N results), and `read_file` / `write_file` (opening / N chars / rejected). Short tools stay silent. Each event carries `{name: "<tool>", phase: "<message>"}`.

Concurrent `/chat/stream` clients see only their own events: each request gets its own queue and worker thread, not a shared module-level FIFO (which used to busy-spin on foreign events).

## Multi-Agent Orchestration

Run a supervised research → write workflow:

```bash
loop-agent run-supervised "Write a report on Alibaba's 2024 ESG progress" --session-id demo
```

The supervisor coordinates two workers:

- `research` — searches the web with `web_search` (requires `BOCHA_API_KEY`)
- `writer` — produces the final report with `read_file` / `write_file`

The supervisor itself uses two tools: `delegate(task, to)` and `finalize(report)`. It always delegates research first, then writing, then returns the final report.

HTTP API:

```bash
curl -X POST http://localhost:8000/chat/supervised \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Write a report on Alibaba's 2024 ESG progress", "session_id": "demo"}'
```

Workers share the same `session_id`, so the full multi-agent trace is available via `GET /sessions/{session_id}`.

Custom workflows: pass `WorkerSpec` and `WorkflowStep` to `Supervisor(...)`. See `docs/superpowers/specs/2026-07-08-loop-agent-phase3-supervisor-config-design.md` for the contract.

## Test

```bash
pytest -v
```

201 tests cover tools, skills, context assembly, providers, trace writer, the agent loop, CLI commands, the HTTP API, persistent sessions, message truncation, streaming SSE, the BoCha web search tool, supervisor multi-agent orchestration, DAG fan-out/fan-in orchestration, the file-tools sandbox, session list/search, ChatLLM retry/backoff, tool-progress emission, tool_error trace records, CLI session/tool/trace commands, and CORS handling for browser clients.

## Architecture

```
┌──────────────────────────────────────────────────┐
│  CLI (loop_agent.cli.main)                       │
│      │                                           │
│      ▼                                           │
│  AgentLoop.run()                                 │
│      ├─→ ContextBuilder.build_messages()         │
│      ├─→ TraceWriter.write()                     │
│      ├─→ ChatLLM.chat() ──→ LangChain ChatOpenAI  │
│      │      └─→ bind_tools(definitions)          │
│      ├─→ ToolRegistry.execute()                  │
│      │      └─→ BaseTool subclasses (auto)       │
│      └─→ WorkspaceMemory.increment()             │
└──────────────────────────────────────────────────┘
```

### Component map

| File | Purpose |
|------|---------|
| `loop_agent/agent/tools.py` | `BaseTool` ABC + `ToolRegistry` |
| `loop_agent/agent/skills.py` | `Skill` + `SkillsLoader` |
| `loop_agent/agent/memory.py` | `WorkspaceMemory` |
| `loop_agent/agent/context.py` | `ContextBuilder` |
| `loop_agent/agent/trace.py` | `TraceWriter` |
| `loop_agent/agent/loop.py` | `AgentLoop` ReAct core |
| `loop_agent/providers/llm.py` | `build_llm()` env mapping |
| `loop_agent/providers/chat.py` | `ChatLLM` wrapper, `LLMResponse` |
| `loop_agent/tools/` | Built-in tools (echo, read/write file, load_skill) |
| `loop_agent/skills/` | Built-in skill Markdown files |

## Quick start: write your own tool

```python
from loop_agent.agent.tools import BaseTool

class GreetTool(BaseTool):
    name = "greet"
    description = "Greet a person by name."
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    def execute(self, *, name: str) -> str:
        return f"Hello, {name}!"
```

Drop this in `loop_agent/tools/`, and it's auto-registered. No central config to edit.

## Quick start: write your own skill

Create `~/.loop-agent/skills/user/my-skill/SKILL.md`:

```markdown
---
name: my-skill
description: Help with my domain.
category: tool
---

## Workflow
1. Step one
2. Step two
```

The agent can now call `load_skill("my-skill")` to read the full body.

## Roadmap

- [x] Streaming responses with proper SSE
- [ ] MCP server entry
- [x] File-tool sandbox with allow-list + deny-list
- [x] Session list + substring search API
- [x] LLM retry/backoff for transient failures
- [x] Tool-progress events for long-running tools
- [x] Multi-agent orchestration
- [x] CLI session / tool / trace ergonomics
- [x] tool_error trace records for failed tool calls

## License

MIT
