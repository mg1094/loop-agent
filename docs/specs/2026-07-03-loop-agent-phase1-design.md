# loop-agent Phase 1 Design

## 1. Project Overview

`loop-agent` is a generic, extensible AI agent framework inspired by the architecture of Vibe-Trading. It is **not finance-specific**. The goal of Phase 1 is to build a runnable ReAct-style agent core with pluggable tools, skills, and LLM providers.

### Target Use Case

General research assistant: answer questions, read/write files, execute simple tools, and follow structured workflows documented as skills.

### Delivery Interface (Long-term)

- Python package (`loop-agent`)
- CLI (`loop-agent run ...`)
- FastAPI server (Phase 2)
- MCP server (Phase 2)

Phase 1 focuses on the package + CLI only.

---

## 2. Architecture & Directory Structure

```
D:\code\loop-agent
├── loop_agent/                 # Main package
│   ├── __init__.py
│   ├── agent/                  # Agent core
│   │   ├── __init__.py
│   │   ├── loop.py             # ReAct main loop
│   │   ├── context.py          # ContextBuilder / system prompt
│   │   ├── memory.py           # WorkspaceMemory (per-run state)
│   │   ├── skills.py           # Skill loader
│   │   ├── tools.py            # BaseTool + ToolRegistry
│   │   └── trace.py            # TraceWriter
│   ├── providers/              # LLM provider layer
│   │   ├── __init__.py
│   │   ├── llm.py              # ChatOpenAI factory + env mapping
│   │   └── chat.py             # ChatLLM wrapper (stream/invoke)
│   ├── tools/                  # Built-in tools
│   │   ├── __init__.py         # build_registry auto-discovery
│   │   ├── echo_tool.py
│   │   ├── read_file_tool.py
│   │   ├── write_file_tool.py
│   │   └── load_skill_tool.py
│   ├── skills/                 # Built-in skills
│   │   ├── writing/SKILL.md
│   │   ├── coding/SKILL.md
│   │   └── research/SKILL.md
│   ├── cli/                    # CLI entry point
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── commands.py
│   ├── api_server.py           # Reserved for Phase 2
│   └── mcp_server.py           # Reserved for Phase 2
├── tests/                      # Unit tests
│   ├── test_tools.py
│   ├── test_skills.py
│   ├── test_loop.py
│   └── test_context.py
├── docs/
│   └── specs/
│       └── 2026-07-03-loop-agent-phase1-design.md
├── pyproject.toml
├── README.md
└── .env.example
```

### Design Principles

- Single responsibility per module.
- Automatic discovery for tools and skills.
- Provider-neutral via environment configuration.
- Every core component has unit tests.

---

## 3. Core Components

### 3.1 BaseTool + ToolRegistry (`loop_agent/agent/tools.py`)

```python
class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: dict = {}
    repeatable: bool = True
    is_readonly: bool = True

    @abstractmethod
    def execute(self, **kwargs) -> str:
        ...
```

`ToolRegistry` provides:

- `register(tool)`
- `get(name)`
- `get_definitions()` → OpenAI function schema list
- `execute(name, params)` → executes and returns JSON string

### 3.2 Skill System (`loop_agent/agent/skills.py`)

```python
@dataclass
class Skill:
    name: str
    description: str
    category: str
    body: str
    dir_path: Path
    metadata: dict
```

`SkillsLoader`:

- Scans `loop_agent/skills/` and `~/.loop-agent/skills/user/`.
- Parses YAML frontmatter from `SKILL.md`.
- `get_descriptions()` → one-line summaries for system prompt.
- `get_content(name)` → full skill document wrapped in `<skill>` XML.

### 3.3 ContextBuilder (`loop_agent/agent/context.py`)

Builds the system prompt and message list:

- Injects tool count, skill count, tool descriptions, skill descriptions, memory summary, and current date/time.
- Returns OpenAI-format message list: `[system, ...history, user]`.

System prompt is generic and free of finance-specific content.

### 3.4 WorkspaceMemory (`loop_agent/agent/memory.py`)

Per-run lightweight state:

```python
@dataclass
class WorkspaceMemory:
    run_dir: str | None
    counters: dict
```

### 3.5 AgentLoop (`loop_agent/agent/loop.py`)

Hand-written ReAct loop:

1. Create `run_dir`.
2. Build messages via `ContextBuilder`.
3. For each iteration (up to `max_iterations`):
   - Call `ChatLLM.stream_chat(messages, tools=registry.get_definitions())`.
   - If no tool calls, return text as final answer.
   - Otherwise execute tools and append results to messages.
4. Write trace.
5. Return result dict.

Phase 1 includes basic token estimation and a simple microcompact layer only.

### 3.6 Provider Layer

- `loop_agent/providers/llm.py`: reads `.env` and constructs `ChatOpenAI`, mapping provider-specific env vars to `OPENAI_API_KEY` / `OPENAI_BASE_URL`.
- `loop_agent/providers/chat.py`: `ChatLLM` wrapper exposing `stream_chat()` / `chat()` returning `LLMResponse`.

### 3.7 TraceWriter (`loop_agent/agent/trace.py`)

Persists run transcript to `runs/<run_id>/trace.jsonl`:

- `start`
- `message`
- `llm_request`
- `tool_call`
- `tool_result`
- `final`

---

## 4. Data Flow

```
User input
  │
  ▼
ContextBuilder.build_messages()
  │   ├── system prompt
  │   └── user message
  ▼
AgentLoop.run()
  │
  ├── Create run_dir: runs/<run_id>/
  │
  ├── Iterate up to max_iterations:
  │     │
  │     ├── ChatLLM.stream_chat(messages, tools)
  │     │     └── LangChain ChatOpenAI.bind_tools()
  │     │
  │     ├── Parse LLMResponse
  │     │     ├── tool_calls → execute tools → JSON results
  │     │     └── no tool_calls → final answer
  │     │
  │     └── Append results to messages
  │
  ├── Write trace.jsonl
  │
  └── Return {status, content, run_id, run_dir}
```

### Loop Details

- Messages are OpenAI-format dicts throughout.
- Tool calls are matched by ID and appended as `role: tool` messages.
- On the last iteration, tools are dropped to force a text response.
- Cancellation is cooperative via `AgentLoop.cancel()`.

---

## 5. Error Handling

| Scenario | Behavior |
|----------|----------|
| Tool execution exception | Return `{"status": "error", "tool": name, "error": str}`; loop continues. |
| LLM stream exception | Wrap in `ProviderStreamError`; retry once if transient; 4xx fails fast. |
| Empty model response | Log `empty_model_response` and end run. |
| Iteration limit reached | Force text-only final turn and return best result. |
| User cancellation | `AgentLoop.cancel()` sets event; loop exits at next checkpoint. |

---

## 6. Testing Strategy

| Test File | Coverage |
|-----------|----------|
| `test_tools.py` | ToolRegistry registration, schema generation, tool execution. |
| `test_skills.py` | SkillsLoader scanning, frontmatter parsing, content retrieval. |
| `test_context.py` | System prompt assembly, message list construction. |
| `test_loop.py` | ReAct loop with a mock LLM: tool call → result → final text. |
| `test_providers.py` | Env mapping and ChatOpenAI construction. |

---

## 7. CLI & Configuration

### Commands

```bash
loop-agent run "Hello"
loop-agent run -p "Use the echo tool to reply"
loop-agent skills list
loop-agent tools list
```

### Environment Variables

```ini
LANGCHAIN_PROVIDER=openai
LANGCHAIN_MODEL_NAME=gpt-4o-mini
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
MAX_ITERATIONS=30
```

---

## 8. Out of Scope for Phase 1

The following are reserved for later phases:

- REST API server (`api_server.py`)
- MCP server (`mcp_server.py`)
- Persistent cross-session memory
- Session management
- SSE streaming for web clients
- Research goals
- Background tasks
- Multi-agent swarm
- Advanced context compression (L2-L5)
- MCP remote tool integration

---

## 9. Success Criteria

Phase 1 is complete when:

1. `pip install -e .` succeeds.
2. `loop-agent run "Use echo to say hello"` executes the echo tool and returns a final answer.
3. `loop-agent skills list` shows built-in skills.
4. `loop-agent tools list` shows built-in tools.
5. All unit tests pass.
6. A new tool/skill can be added by creating a file in `loop_agent/tools/` or `loop_agent/skills/` without modifying registry code.
