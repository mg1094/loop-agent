# loop-agent

Generic ReAct agent framework with skills and tools.

Inspired by [Vibe-Trading](https://github.com) and similar agent systems, this is a stripped-down, domain-agnostic implementation focused on the core building blocks: a hand-written ReAct loop, auto-discovered tools, on-demand skill loading, and a provider-neutral LLM layer.

## Features

- **ReAct loop** (`AgentLoop`): custom while-loop, not LangGraph StateGraph
- **Tools** (`BaseTool` + `ToolRegistry`): subclass and auto-discover
- **Skills** (`SkillsLoader`): Markdown + YAML frontmatter, loaded on demand
- **ContextBuilder**: assembles the system prompt with tool + skill descriptions
- **Providers**: LangChain `ChatOpenAI` works with any OpenAI-compatible API (OpenAI, DeepSeek, DashScope/Qwen, Moonshot, Gemini, Groq, Ollama)
- **TraceWriter**: per-run JSONL trace under `runs/<run_id>/trace.jsonl`
- **WorkspaceMemory**: per-run counters and state
- **CLI**: `loop-agent run ...`, `loop-agent skills`, `loop-agent tools`

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
```

Supported providers: `openai`, `deepseek`, `dashscope`/`qwen`, `moonshot`, `gemini`, `groq`, `ollama`.

## Usage

```bash
loop-agent run "Use the echo tool to say hello"
loop-agent skills
loop-agent tools
```

## Test

```bash
pytest -v
```

## Architecture

```
┌──────────────────────────────────────────────────┐
│  CLI (loop_agent.cli.main)                       │
│      │                                           │
│      ▼                                           │
│  AgentLoop.run()                                 │
│      ├─→ ContextBuilder.build_messages()         │
│      ├─→ TraceWriter.write()                     │
│      ├─→ ChatLLM.stream_chat() ──→ LangChain      │
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

## License

MIT
