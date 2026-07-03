# loop-agent Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable generic ReAct agent framework with auto-discovered tools/skills, LangChain ChatOpenAI provider, trace logging, and a CLI.

**Architecture:** Hand-written ReAct loop (`AgentLoop`) drives a `ChatLLM` wrapper around LangChain's `ChatOpenAI`. Tools inherit from `BaseTool` and auto-register via `ToolRegistry`. Skills are Markdown files with YAML frontmatter loaded on demand. `ContextBuilder` assembles the system prompt. `TraceWriter` persists each run.

**Tech Stack:** Python 3.11+, `langchain>=1.0`, `langchain-openai>=1.0`, `pydantic>=2.0`, `python-dotenv`, `pytest`, `rich`.

## Global Constraints

- Python `>=3.11`
- `langchain>=1.0.0,<2`
- `langchain-openai>=1.0.0,<2`
- `pydantic>=2.0.0`
- All tool execution returns a JSON string.
- Messages are OpenAI-format dicts throughout.
- Provider-neutral via `.env` (`LANGCHAIN_PROVIDER`, `LANGCHAIN_MODEL_NAME`, provider-specific `*_API_KEY` / `*_BASE_URL`).
- Every task ends with a passing test and a git commit.

---

## File Structure

```
D:\code\loop-agent
├── loop_agent/
│   ├── __init__.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── tools.py          # BaseTool + ToolRegistry
│   │   ├── skills.py         # Skill + SkillsLoader
│   │   ├── memory.py         # WorkspaceMemory
│   │   ├── context.py        # ContextBuilder
│   │   ├── trace.py          # TraceWriter
│   │   └── loop.py           # AgentLoop
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── llm.py            # ChatOpenAI factory + env mapping
│   │   └── chat.py           # ChatLLM wrapper + LLMResponse
│   ├── tools/
│   │   ├── __init__.py       # build_registry
│   │   ├── echo_tool.py
│   │   ├── read_file_tool.py
│   │   ├── write_file_tool.py
│   │   └── load_skill_tool.py
│   ├── skills/
│   │   ├── writing/SKILL.md
│   │   ├── coding/SKILL.md
│   │   └── research/SKILL.md
│   └── cli/
│       ├── __init__.py
│       ├── main.py
│       └── commands.py
├── tests/
│   ├── test_tools.py
│   ├── test_skills.py
│   ├── test_memory.py
│   ├── test_context.py
│   ├── test_providers.py
│   ├── test_trace.py
│   ├── test_loop.py
│   └── test_cli.py
├── pyproject.toml
├── .env.example
├── README.md
└── docs/superpowers/plans/2026-07-03-loop-agent-phase1.md
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `loop_agent/__init__.py`
- Create: `loop_agent/agent/__init__.py`
- Create: `loop_agent/providers/__init__.py`
- Create: `loop_agent/tools/__init__.py`
- Create: `loop_agent/skills/.gitkeep`
- Create: `tests/__init__.py`
- Test: no test yet; verify install

**Interfaces:**
- Produces: installable package `loop-agent`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "loop-agent"
version = "0.1.0"
description = "Generic ReAct agent framework with skills and tools"
requires-python = ">=3.11"
license = {text = "MIT"}
readme = "README.md"
dependencies = [
    "rich>=13.0.0",
    "langchain>=1.0.0,<2",
    "langchain-openai>=1.0.0,<2",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
]

[project.scripts]
loop-agent = "loop_agent.cli.main:main"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["loop_agent*"]
```

- [ ] **Step 2: Create `.env.example`**

```ini
LANGCHAIN_PROVIDER=openai
LANGCHAIN_MODEL_NAME=gpt-4o-mini
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
MAX_ITERATIONS=30
```

- [ ] **Step 3: Create empty package init files**

```python
# loop_agent/__init__.py
__version__ = "0.1.0"
```

```python
# loop_agent/agent/__init__.py
```

```python
# loop_agent/providers/__init__.py
```

```python
# loop_agent/tools/__init__.py
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Install package in editable mode**

Run:
```bash
cd D:\code\loop-agent
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Expected: install succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example loop_agent/__init__.py loop_agent/agent/__init__.py loop_agent/providers/__init__.py loop_agent/tools/__init__.py tests/__init__.py
git commit -m "chore: project scaffold"
```

---

### Task 2: BaseTool + ToolRegistry

**Files:**
- Create: `loop_agent/agent/tools.py`
- Create: `tests/test_tools.py`

**Interfaces:**
- Produces: `BaseTool`, `ToolRegistry`
- `ToolRegistry.get_definitions()` returns OpenAI function schema list.
- `ToolRegistry.execute(name, params)` returns JSON string.

- [ ] **Step 1: Write failing test**

```python
# tests/test_tools.py
import json
import pytest
from loop_agent.agent.tools import BaseTool, ToolRegistry

class AddTool(BaseTool):
    name = "add"
    description = "Add two numbers."
    parameters = {
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
        },
        "required": ["a", "b"],
    }

    def execute(self, *, a: float, b: float) -> str:
        return json.dumps({"result": a + b})


def test_registry_register_and_get():
    registry = ToolRegistry()
    tool = AddTool()
    registry.register(tool)
    assert registry.get("add") is tool


def test_registry_get_definitions():
    registry = ToolRegistry()
    registry.register(AddTool())
    defs = registry.get_definitions()
    assert len(defs) == 1
    assert defs[0]["function"]["name"] == "add"


def test_registry_execute():
    registry = ToolRegistry()
    registry.register(AddTool())
    result = registry.execute("add", {"a": 1, "b": 2})
    assert json.loads(result)["result"] == 3


def test_registry_execute_missing_tool():
    registry = ToolRegistry()
    result = registry.execute("missing", {})
    data = json.loads(result)
    assert data["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_tools.py -v
```

Expected: ImportError / module not found.

- [ ] **Step 3: Implement `loop_agent/agent/tools.py`**

```python
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}
    repeatable: bool = True
    is_readonly: bool = True

    @classmethod
    def check_available(cls) -> bool:
        return True

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a JSON string."""

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}, "required": []},
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_definitions(self) -> List[Dict[str, Any]]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute(self, name: str, params: Dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if not tool:
            return json.dumps({"status": "error", "error": f"Tool '{name}' not found"}, ensure_ascii=False)
        try:
            return tool.execute(**params)
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return json.dumps({"status": "error", "tool": name, "error": str(exc)}, ensure_ascii=False)

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/agent/tools.py tests/test_tools.py
git commit -m "feat: add BaseTool and ToolRegistry"
```

---

### Task 3: Frontmatter Parser

**Files:**
- Create: `loop_agent/agent/frontmatter.py`
- Create: `tests/test_frontmatter.py`

**Interfaces:**
- Produces: `parse_frontmatter(text: str) -> tuple[dict, str]`

- [ ] **Step 1: Write failing test**

```python
# tests/test_frontmatter.py
from loop_agent.agent.frontmatter import parse_frontmatter


def test_parse_frontmatter():
    text = """---
name: writing
description: Writing assistant.
category: writing
---

## Workflow
1. Plan
2. Draft
"""
    meta, body = parse_frontmatter(text)
    assert meta["name"] == "writing"
    assert meta["category"] == "writing"
    assert "## Workflow" in body


def test_parse_no_frontmatter():
    text = "# Hello\n\nWorld"
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert body == text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_frontmatter.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `loop_agent/agent/frontmatter.py`**

```python
from __future__ import annotations

from typing import Any


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown text.

    Returns:
        (metadata dict, body text)
    """
    meta: dict[str, Any] = {}
    body = text
    stripped = text.lstrip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                meta = yaml.safe_load(parts[1]) or {}
            except ImportError:
                meta = {}
            body = parts[2].strip("\n")
    return meta, body
```

- [ ] **Step 4: Add PyYAML dependency**

Modify `pyproject.toml` dependencies:

```toml
dependencies = [
    "rich>=13.0.0",
    "langchain>=1.0.0,<2",
    "langchain-openai>=1.0.0,<2",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0.0",
]
```

Reinstall:
```bash
pip install -e ".[dev]"
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_frontmatter.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/agent/frontmatter.py tests/test_frontmatter.py pyproject.toml
git commit -m "feat: add YAML frontmatter parser"
```

---

### Task 4: Skill System

**Files:**
- Create: `loop_agent/agent/skills.py`
- Create: `tests/test_skills.py`

**Interfaces:**
- Produces: `Skill`, `SkillsLoader`
- `SkillsLoader(skills_dir, user_skills_dir)`
- `get_descriptions()` → str
- `get_content(name)` → str

- [ ] **Step 1: Write failing test**

```python
# tests/test_skills.py
import tempfile
from pathlib import Path

from loop_agent.agent.skills import Skill, SkillsLoader


def test_load_skill(tmp_path: Path):
    skill_dir = tmp_path / "writing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: writing
description: Writing assistant.
category: writing
---

## Workflow
Plan, draft, edit.
""", encoding="utf-8")

    loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    assert len(loader.skills) == 1
    assert loader.skills[0].name == "writing"


def test_get_content(tmp_path: Path):
    skill_dir = tmp_path / "writing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: writing
description: Writing assistant.
---

Body here.
""", encoding="utf-8")

    loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    content = loader.get_content("writing")
    assert '<skill name="writing">' in content
    assert "Body here." in content


def test_get_descriptions(tmp_path: Path):
    skill_dir = tmp_path / "writing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: writing
description: Writing assistant.
category: writing
---

Body.
""", encoding="utf-8")

    loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    desc = loader.get_descriptions()
    assert "writing" in desc
    assert "Writing assistant." in desc
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_skills.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `loop_agent/agent/skills.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loop_agent.agent.frontmatter import parse_frontmatter


USER_SKILLS_DIR = Path.home() / ".loop-agent" / "skills" / "user"


@dataclass
class Skill:
    name: str
    description: str = ""
    category: str = "other"
    body: str = ""
    dir_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def load_support_file(self, filename: str) -> Optional[str]:
        if not self.dir_path:
            return None
        path = self.dir_path / filename
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None


def _load_skill_dir(dir_path: Path) -> Optional[Skill]:
    skill_file = dir_path / "SKILL.md"
    if not skill_file.exists():
        return None
    try:
        text = skill_file.read_text(encoding="utf-8")
    except Exception:
        return None

    meta, body = parse_frontmatter(text)
    name = meta.get("name", dir_path.name)
    if not name:
        return None

    return Skill(
        name=name,
        description=meta.get("description", ""),
        category=meta.get("category", "other"),
        body=body,
        dir_path=dir_path,
        metadata=meta,
    )


class SkillsLoader:
    _CATEGORY_ORDER = [
        "writing", "coding", "research", "analysis", "tool", "other"
    ]

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        user_skills_dir: Optional[Path] = None,
    ) -> None:
        self.skills_dir = skills_dir or Path(__file__).resolve().parents[1] / "skills"
        self._user_skills_dir = user_skills_dir or USER_SKILLS_DIR
        self.skills: List[Skill] = []
        self._load()

    def _load(self) -> None:
        seen_names: set[str] = set()
        for directory in (self._user_skills_dir, self.skills_dir):
            if not directory or not directory.exists():
                continue
            for path in sorted(directory.iterdir()):
                if path.is_dir() and (path / "SKILL.md").exists():
                    skill = _load_skill_dir(path)
                    if skill and skill.name not in seen_names:
                        self.skills.append(skill)
                        seen_names.add(skill.name)

    def get_descriptions(self) -> str:
        if not self.skills:
            return "(no skills)"

        groups: Dict[str, List[Skill]] = {}
        for skill in self.skills:
            groups.setdefault(skill.category, []).append(skill)

        ordered_cats = [c for c in self._CATEGORY_ORDER if c in groups]
        ordered_cats += [c for c in sorted(groups) if c not in ordered_cats]

        lines: List[str] = []
        for cat in ordered_cats:
            lines.append(f"\n### {cat}")
            for skill in groups[cat]:
                lines.append(f"  - {skill.name}: {skill.description}")
        return "\n".join(lines)

    def get_content(self, name: str) -> str:
        for skill in self.skills:
            if skill.name == name:
                return f'<skill name="{name}">\n{skill.body}\n</skill>'

        if self._user_skills_dir:
            skill = _load_skill_dir(self._user_skills_dir / name)
            if skill:
                self.skills.append(skill)
                return f'<skill name="{name}">\n{skill.body}\n</skill>'

        available = ", ".join(s.name for s in self.skills)
        return f"Error: Unknown skill '{name}'. Available: {available}"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_skills.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/agent/skills.py tests/test_skills.py
git commit -m "feat: add Skill and SkillsLoader"
```

---

### Task 5: WorkspaceMemory

**Files:**
- Create: `loop_agent/agent/memory.py`
- Create: `tests/test_memory.py`

**Interfaces:**
- Produces: `WorkspaceMemory`

- [ ] **Step 1: Write failing test**

```python
# tests/test_memory.py
from loop_agent.agent.memory import WorkspaceMemory


def test_increment_counter():
    mem = WorkspaceMemory()
    assert mem.increment("echo") == 1
    assert mem.increment("echo") == 2


def test_summary():
    mem = WorkspaceMemory(run_dir="/tmp/run")
    mem.increment("echo")
    summary = mem.to_summary()
    assert "/tmp/run" in summary
    assert "echo=1" in summary
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_memory.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `loop_agent/agent/memory.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class WorkspaceMemory:
    run_dir: Optional[str] = None
    counters: Dict[str, int] = field(default_factory=dict)

    def increment(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def to_summary(self) -> str:
        lines: list[str] = []
        if self.run_dir:
            lines.append(f"- run_dir: {self.run_dir}")
        if self.counters:
            counter_parts = [f"{k}={v}" for k, v in self.counters.items()]
            lines.append(f"- counters: {', '.join(counter_parts)}")
        return "\n".join(lines) if lines else "(empty state)"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_memory.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/agent/memory.py tests/test_memory.py
git commit -m "feat: add WorkspaceMemory"
```

---

### Task 6: ContextBuilder

**Files:**
- Create: `loop_agent/agent/context.py`
- Create: `tests/test_context.py`

**Interfaces:**
- Consumes: `ToolRegistry`, `WorkspaceMemory`, `SkillsLoader`
- Produces: `ContextBuilder.build_system_prompt()`, `build_messages()`

- [ ] **Step 1: Write failing test**

```python
# tests/test_context.py
from loop_agent.agent.context import ContextBuilder
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import BaseTool, ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo the input."
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
        },
        "required": ["message"],
    }

    def execute(self, *, message: str) -> str:
        return message


def test_system_prompt_contains_tools_and_skills(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(EchoTool())
    memory = WorkspaceMemory()
    skills_loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    builder = ContextBuilder(registry, memory, skills_loader)
    prompt = builder.build_system_prompt()
    assert "echo" in prompt
    assert "Echo the input" in prompt


def test_build_messages(tmp_path: Path):
    registry = ToolRegistry()
    memory = WorkspaceMemory()
    skills_loader = SkillsLoader(skills_dir=tmp_path, user_skills_dir=None)
    builder = ContextBuilder(registry, memory, skills_loader)
    messages = builder.build_messages("hello")
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "hello" in messages[-1]["content"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_context.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `loop_agent/agent/context.py`**

```python
from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import ToolRegistry

if TYPE_CHECKING:
    pass

_SYSTEM_PROMPT = """You are a helpful research assistant.

You have access to {tool_count} tools and {skill_count} skills.

## Tools

{tool_descriptions}

## Skills

Use `load_skill(name)` to read full documentation before starting a complex task.

{skill_descriptions}

## Current State

{memory_summary}

## Guidelines

- Load the relevant skill first when starting a new type of task.
- Ask the user if critical info is missing.
- Respond in the same language the user used.
- Today is {current_datetime}.
"""


class ContextBuilder:
    def __init__(
        self,
        registry: ToolRegistry,
        memory: WorkspaceMemory,
        skills_loader: Optional[SkillsLoader] = None,
    ) -> None:
        self.registry = registry
        self.memory = memory
        self.skills_loader = skills_loader or SkillsLoader()

    def build_system_prompt(self, user_message: str = "") -> str:
        now = datetime.now()
        return _SYSTEM_PROMPT.format(
            tool_count=len(self.registry),
            skill_count=len(self.skills_loader.skills),
            tool_descriptions=self._format_tool_descriptions(),
            skill_descriptions=self.skills_loader.get_descriptions(),
            memory_summary=self.memory.to_summary(),
            current_datetime=now.strftime("%A, %B %d, %Y %H:%M (local)"),
        )

    def _format_tool_descriptions(self) -> str:
        lines = []
        for tool in self.registry._tools.values():
            params = tool.parameters.get("properties", {})
            required = tool.parameters.get("required", [])
            param_parts = []
            for pname, pschema in params.items():
                req = " (required)" if pname in required else ""
                param_parts.append(
                    f"    - {pname}: {pschema.get('description', pschema.get('type', ''))}{req}"
                )
            param_text = "\n".join(param_parts) if param_parts else "    (no params)"
            lines.append(f"### {tool.name}\n{tool.description}\n  Params:\n{param_text}")
        return "\n\n".join(lines)

    def build_messages(
        self,
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.build_system_prompt(user_message)},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    @staticmethod
    def format_tool_result(tool_call_id: str, tool_name: str, result: str) -> Dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        }

    @staticmethod
    def format_assistant_tool_calls(
        tool_calls: list,
        content: Optional[str] = None,
    ) -> Dict[str, Any]:
        formatted = []
        for tc in tool_calls:
            formatted.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            })
        msg: Dict[str, Any] = {"role": "assistant", "content": content or ""}
        if formatted:
            msg["tool_calls"] = formatted
        return msg
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_context.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/agent/context.py tests/test_context.py
git commit -m "feat: add ContextBuilder"
```

---

### Task 7: Provider Layer

**Files:**
- Create: `loop_agent/providers/llm.py`
- Create: `loop_agent/providers/chat.py`
- Create: `tests/test_providers.py`

**Interfaces:**
- Produces: `build_llm()` → `ChatOpenAIWithReasoning`
- Produces: `ChatLLM.stream_chat()` → `LLMResponse`

- [ ] **Step 1: Write failing test**

```python
# tests/test_providers.py
import os

from loop_agent.providers.llm import build_llm, _sync_provider_env
from loop_agent.providers.chat import ChatLLM, LLMResponse


def test_sync_provider_env_openai(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    _sync_provider_env()
    assert os.getenv("OPENAI_API_KEY") == "sk-test"


def test_llm_response_has_tool_calls():
    response = LLMResponse(
        content="hello",
        finish_reason="stop",
    )
    assert not response.has_tool_calls
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_providers.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `loop_agent/providers/llm.py`**

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None  # type: ignore

AGENT_DIR = Path(__file__).resolve().parents[1]
_ENV_CANDIDATES = [
    Path.home() / ".loop-agent" / ".env",
    AGENT_DIR / ".env",
    Path.cwd() / ".env",
]
_dotenv_loaded = False


def _ensure_dotenv() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    for candidate in _ENV_CANDIDATES:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break
    _dotenv_loaded = True


_PROVIDER_CONFIG: dict[str, tuple[Optional[str], str]] = {
    "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
    "dashscope": ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"),
    "qwen": ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"),
    "moonshot": ("MOONSHOT_API_KEY", "MOONSHOT_BASE_URL"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_BASE_URL"),
    "groq": ("GROQ_API_KEY", "GROQ_BASE_URL"),
    "ollama": (None, "OLLAMA_BASE_URL"),
}


def _sync_provider_env() -> None:
    _ensure_dotenv()
    provider = os.getenv("LANGCHAIN_PROVIDER", "openai").lower()
    key_env, base_env = _PROVIDER_CONFIG.get(provider, ("OPENAI_API_KEY", "OPENAI_BASE_URL"))

    if key_env is not None:
        api_key = os.getenv(key_env, "") or os.getenv("OPENAI_API_KEY", "")
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

    base_url = os.getenv(base_env, "")
    if base_url:
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        os.environ["OPENAI_API_BASE"] = base_url
        os.environ["OPENAI_BASE_URL"] = base_url


def build_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_retries: Optional[int] = None,
    timeout: Optional[int] = None,
) -> Any:
    if ChatOpenAI is None:
        raise RuntimeError("langchain-openai is not installed")

    _sync_provider_env()

    model_name = model or os.getenv("LANGCHAIN_MODEL_NAME", "gpt-4o-mini")
    temp = temperature if temperature is not None else float(os.getenv("LANGCHAIN_TEMPERATURE", "0.0"))
    retries = max_retries if max_retries is not None else int(os.getenv("MAX_RETRIES", "2"))
    to = timeout if timeout is not None else int(os.getenv("TIMEOUT_SECONDS", "120"))

    kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": temp,
        "max_retries": retries,
        "timeout": to,
    }

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    return ChatOpenAI(**kwargs)
```

- [ ] **Step 4: Implement `loop_agent/providers/chat.py`**

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from loop_agent.providers.llm import build_llm


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    content: Optional[str] = None
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage_metadata: Optional[Dict[str, int]] = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class ProviderStreamError(RuntimeError):
    def __init__(self, *, provider: str, model: str, original: Exception) -> None:
        self.provider = provider
        self.model = model
        self.original = original
        self.status_code: Optional[int] = getattr(original, "status_code", None)
        super().__init__(
            f"provider_stream_error provider={provider} model={model}: "
            f"{type(original).__name__}: {original}"
        )

    @property
    def retryable(self) -> bool:
        if self.status_code is None:
            return True
        if self.status_code in (408, 429):
            return True
        return not 400 <= self.status_code < 500


class ChatLLM:
    def __init__(self, llm: Optional[Any] = None) -> None:
        self._llm = llm or build_llm()
        self.model_name = getattr(self._llm, "model_name", os.getenv("LANGCHAIN_MODEL_NAME", ""))

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        on_reasoning_chunk: Optional[Callable[[str], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> LLMResponse:
        llm = self._llm.bind_tools(tools) if tools else self._llm
        full_content = ""
        usage_metadata = None

        try:
            for chunk in llm.stream(messages):
                if should_cancel and should_cancel():
                    break

                delta = chunk.content or ""
                if delta:
                    full_content += delta
                    if on_text_chunk:
                        on_text_chunk(delta)

                if getattr(chunk, "usage_metadata", None):
                    usage_metadata = dict(chunk.usage_metadata)

            # Parse tool calls if present
            tool_calls: List[ToolCallRequest] = []
            if full_content.strip().startswith("{"):
                # Some providers may inline tool calls; normal OpenAI tool_calls come via additional_kwargs
                pass

            # Collect tool_calls from the last chunk if available
            if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                for tc in chunk.tool_calls:
                    args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    if isinstance(args, str):
                        args = json.loads(args) if args else {}
                    tool_calls.append(ToolCallRequest(
                        id=tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", ""),
                        name=tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", ""),
                        arguments=args or {},
                    ))

            return LLMResponse(
                content=full_content if not tool_calls else None,
                tool_calls=tool_calls,
                finish_reason="tool_calls" if tool_calls else "stop",
                usage_metadata=usage_metadata,
            )
        except Exception as exc:
            provider = os.getenv("LANGCHAIN_PROVIDER", "openai")
            raise ProviderStreamError(provider=provider, model=self.model_name, original=exc)

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        llm = self._llm.bind_tools(tools) if tools else self._llm
        response = llm.invoke(messages)
        content = response.content or ""

        tool_calls: List[ToolCallRequest] = []
        for tc in getattr(response, "tool_calls", []) or []:
            args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
            if isinstance(args, str):
                args = json.loads(args) if args else {}
            tool_calls.append(ToolCallRequest(
                id=tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", ""),
                name=tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", ""),
                arguments=args or {},
            ))

        return LLMResponse(
            content=content if not tool_calls else None,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else getattr(response, "finish_reason", "stop"),
            usage_metadata=getattr(response, "usage_metadata", None),
        )
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_providers.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/providers/llm.py loop_agent/providers/chat.py tests/test_providers.py
git commit -m "feat: add LLM provider layer"
```

---

### Task 8: TraceWriter

**Files:**
- Create: `loop_agent/agent/trace.py`
- Create: `tests/test_trace.py`

**Interfaces:**
- Produces: `TraceWriter(trace_dir)`
- `write(entry)`
- `write_text_entry(...)`

- [ ] **Step 1: Write failing test**

```python
# tests/test_trace.py
import json
import tempfile
from pathlib import Path

from loop_agent.agent.trace import TraceWriter


def test_trace_write(tmp_path: Path):
    writer = TraceWriter(tmp_path)
    writer.write({"type": "start", "iter": 1})
    writer.write({"type": "final", "content": "done"})

    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "start"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_trace.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `loop_agent/agent/trace.py`**

```python
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class TraceWriter:
    def __init__(self, trace_dir: Path) -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / "trace.jsonl"

    def write(self, entry: Dict[str, Any]) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.warning("Trace write failed: %s", exc)

    def write_text_entry(
        self,
        entry: Dict[str, Any],
        field: str,
        value: str,
        offload_kind: str = "",
    ) -> None:
        entry[field] = value
        self.write(entry)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_trace.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/agent/trace.py tests/test_trace.py
git commit -m "feat: add TraceWriter"
```

---

### Task 9: Built-in Tools

**Files:**
- Create: `loop_agent/tools/echo_tool.py`
- Create: `loop_agent/tools/read_file_tool.py`
- Create: `loop_agent/tools/write_file_tool.py`
- Create: `loop_agent/tools/load_skill_tool.py`
- Modify: `loop_agent/tools/__init__.py`
- Create: `tests/test_builtin_tools.py`

**Interfaces:**
- Produces: `echo`, `read_file`, `write_file`, `load_skill` tools
- `build_registry()` returns fully populated `ToolRegistry`

- [ ] **Step 1: Write failing test**

```python
# tests/test_builtin_tools.py
import json
import tempfile
from pathlib import Path

from loop_agent.tools import build_registry


def test_build_registry_has_echo():
    registry = build_registry()
    assert "echo" in registry


def test_echo_tool():
    registry = build_registry()
    result = registry.execute("echo", {"message": "hello"})
    assert json.loads(result)["result"] == "hello"


def test_write_and_read_file(tmp_path: Path):
    registry = build_registry()
    path = tmp_path / "test.txt"
    result = registry.execute("write_file", {"path": str(path), "content": "hello world"})
    assert json.loads(result)["status"] == "ok"

    result = registry.execute("read_file", {"path": str(path)})
    assert json.loads(result)["content"] == "hello world"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_builtin_tools.py -v
```

Expected: ImportError / missing tools.

- [ ] **Step 3: Implement tools**

```python
# loop_agent/tools/echo_tool.py
import json
from loop_agent.agent.tools import BaseTool


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo the input message back. Useful for testing the tool loop."
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to echo"},
        },
        "required": ["message"],
    }

    def execute(self, *, message: str) -> str:
        return json.dumps({"result": message}, ensure_ascii=False)
```

```python
# loop_agent/tools/read_file_tool.py
import json
from pathlib import Path
from loop_agent.agent.tools import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a text file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
        },
        "required": ["path"],
    }

    def execute(self, *, path: str) -> str:
        try:
            content = Path(path).read_text(encoding="utf-8")
            return json.dumps({"status": "ok", "content": content}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
```

```python
# loop_agent/tools/write_file_tool.py
import json
from pathlib import Path
from loop_agent.agent.tools import BaseTool


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a text file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    }
    is_readonly = False

    def execute(self, *, path: str, content: str) -> str:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return json.dumps({"status": "ok", "path": str(p)}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
```

```python
# loop_agent/tools/load_skill_tool.py
import json
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import BaseTool


class LoadSkillTool(BaseTool):
    name = "load_skill"
    description = "Load full documentation for a named skill."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name"},
        },
        "required": ["name"],
    }
    repeatable = True

    def __init__(self, skills_loader: SkillsLoader | None = None) -> None:
        self._loader = skills_loader or SkillsLoader()

    def execute(self, *, name: str) -> str:
        content = self._loader.get_content(name)
        return json.dumps({"status": "ok", "content": content}, ensure_ascii=False)
```

- [ ] **Step 4: Implement `loop_agent/tools/__init__.py`**

```python
from __future__ import annotations

import importlib
import logging
import pkgutil
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from loop_agent.agent.tools import BaseTool, ToolRegistry

if TYPE_CHECKING:
    from loop_agent.agent.skills import SkillsLoader

logger = logging.getLogger(__name__)

_SUBCLASSES_CACHE: list[type[BaseTool]] | None = None


def _discover_subclasses() -> list[type[BaseTool]]:
    global _SUBCLASSES_CACHE
    if _SUBCLASSES_CACHE is not None:
        return _SUBCLASSES_CACHE

    pkg_dir = str(Path(__file__).parent)
    for _, module_name, _ in pkgutil.iter_modules([pkg_dir]):
        if module_name.startswith("_"):
            continue
        try:
            importlib.import_module(f"loop_agent.tools.{module_name}")
        except Exception as exc:
            logger.warning("Skipped loop_agent.tools.%s: %s", module_name, exc)

    classes: list[type[BaseTool]] = []
    queue = deque(BaseTool.__subclasses__())
    while queue:
        cls = queue.popleft()
        if cls.name:
            classes.append(cls)
        queue.extend(cls.__subclasses__())

    _SUBCLASSES_CACHE = classes
    return classes


def build_registry(
    *,
    skills_loader: "SkillsLoader | None" = None,
    event_callback: Callable[[str, dict], None] | None = None,
) -> ToolRegistry:
    from loop_agent.tools.load_skill_tool import LoadSkillTool

    registry = ToolRegistry()
    for cls in _discover_subclasses():
        try:
            if not cls.check_available():
                logger.info("Tool %s unavailable, skipping", cls.name)
                continue
            if cls is LoadSkillTool:
                registry.register(cls(skills_loader=skills_loader))
            else:
                registry.register(cls())
        except Exception as exc:
            logger.warning("Failed to register tool %s: %s", cls.name, exc)

    return registry
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_builtin_tools.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/tools/__init__.py loop_agent/tools/echo_tool.py loop_agent/tools/read_file_tool.py loop_agent/tools/write_file_tool.py loop_agent/tools/load_skill_tool.py tests/test_builtin_tools.py
git commit -m "feat: add built-in tools"
```

---

### Task 10: AgentLoop

**Files:**
- Create: `loop_agent/agent/loop.py`
- Create: `tests/test_loop.py`

**Interfaces:**
- Consumes: `ToolRegistry`, `ChatLLM`, `WorkspaceMemory`, `ContextBuilder`, `TraceWriter`
- Produces: `AgentLoop.run()` returns dict

- [ ] **Step 1: Write failing test**

```python
# tests/test_loop.py
import json
from unittest.mock import MagicMock

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import BaseTool, ToolRegistry
from loop_agent.providers.chat import ChatLLM, LLMResponse, ToolCallRequest


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo"
    parameters = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    def execute(self, *, message: str) -> str:
        return json.dumps({"result": message})


def test_loop_runs_tool_then_finishes(tmp_path):
    registry = ToolRegistry()
    registry.register(EchoTool())
    memory = WorkspaceMemory()

    llm = MagicMock(spec=ChatLLM)
    llm.stream_chat.side_effect = [
        LLMResponse(
            tool_calls=[ToolCallRequest(id="1", name="echo", arguments={"message": "hello"})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="Done", finish_reason="stop"),
    ]

    loop = AgentLoop(registry, llm, memory, max_iterations=5)
    result = loop.run("say hello")

    assert result["status"] == "success"
    assert result["content"] == "Done"
    assert llm.stream_chat.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_loop.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `loop_agent/agent/loop.py`**

```python
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loop_agent.agent.context import ContextBuilder
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.tools import ToolRegistry
from loop_agent.agent.trace import TraceWriter
from loop_agent.providers.chat import ChatLLM, LLMResponse, ToolCallRequest

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
    ) -> None:
        self.registry = registry
        self.llm = llm
        self.memory = memory or WorkspaceMemory()
        self._event_callback = event_callback
        self.max_iterations = max_iterations
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if self._event_callback:
            self._event_callback(event_type, data)

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
        messages = context.build_messages(user_message, history)

        trace = TraceWriter(run_dir)
        trace.write({"type": "start", "run_id": run_id, "prompt": user_message})
        trace.write({"type": "message", "role": "user", "content": user_message})

        iteration = 0
        final_content = ""

        try:
            while iteration < self.max_iterations:
                if self._cancel_event.is_set():
                    trace.write({"type": "cancelled", "iter": iteration + 1})
                    return {"status": "cancelled", "content": "", "run_id": run_id, "run_dir": str(run_dir)}

                iteration += 1
                logger.info("ReAct iteration %d/%d", iteration, self.max_iterations)

                is_last = iteration == self.max_iterations
                tool_defs = None if is_last else self.registry.get_definitions()

                if is_last:
                    trace.write({"type": "forced_text_only", "iter": iteration})

                response = self.llm.stream_chat(
                    messages,
                    tools=tool_defs,
                    should_cancel=self._cancel_event.is_set,
                )

                if not response.has_tool_calls:
                    final_content = response.content or ""
                    if not final_content:
                        trace.write({"type": "empty_model_response", "iter": iteration})
                        return {"status": "empty", "content": "", "run_id": run_id, "run_dir": str(run_dir)}
                    trace.write({"type": "final", "iter": iteration, "content": final_content})
                    return {"status": "success", "content": final_content, "run_id": run_id, "run_dir": str(run_dir)}

                # Execute tool calls
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

            # Exceeded max iterations
            return {"status": "max_iterations", "content": final_content, "run_id": run_id, "run_dir": str(run_dir)}

        except Exception as exc:
            logger.exception("AgentLoop failed")
            trace.write({"type": "error", "error": str(exc)})
            return {"status": "error", "content": str(exc), "run_id": run_id, "run_dir": str(run_dir)}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_loop.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add loop_agent/agent/loop.py tests/test_loop.py
git commit -m "feat: add AgentLoop ReAct core"
```

---

### Task 11: CLI

**Files:**
- Create: `loop_agent/cli/commands.py`
- Create: `loop_agent/cli/main.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Produces: `loop-agent` console script

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli.py
from loop_agent.cli.commands import run_command


def test_run_command_with_mock_loop(monkeypatch):
    calls = []

    def fake_run(user_message, history=None, session_id=""):
        calls.append(user_message)
        return {"status": "success", "content": f"Echo: {user_message}", "run_id": "r1", "run_dir": "/tmp/r1"}

    monkeypatch.setattr("loop_agent.cli.commands._run_agent", fake_run)
    result = run_command("hello")
    assert result["content"] == "Echo: hello"
    assert calls == ["hello"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_cli.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `loop_agent/cli/commands.py`**

```python
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from loop_agent.agent.loop import AgentLoop
from loop_agent.agent.memory import WorkspaceMemory
from loop_agent.agent.skills import SkillsLoader
from loop_agent.agent.tools import ToolRegistry
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


def list_tools() -> str:
    _load_env()
    registry = build_registry()
    return "\n".join(registry.tool_names)
```

- [ ] **Step 4: Implement `loop_agent/cli/main.py`**

```python
from __future__ import annotations

import argparse
import sys

from loop_agent.cli import commands


def main() -> int:
    parser = argparse.ArgumentParser(prog="loop-agent", description="Generic ReAct agent")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a single prompt")
    run_parser.add_argument("prompt", nargs="+", help="User prompt")

    subparsers.add_parser("skills", help="List skills")
    subparsers.add_parser("tools", help="List tools")

    args = parser.parse_args()

    if args.command == "run":
        prompt = " ".join(args.prompt)
        result = commands.run_command(prompt)
        print(result.get("content", ""))
        return 0 if result.get("status") == "success" else 1

    if args.command == "skills":
        print(commands.list_skills())
        return 0

    if args.command == "tools":
        print(commands.list_tools())
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_cli.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/cli/commands.py loop_agent/cli/main.py loop_agent/cli/__init__.py tests/test_cli.py
git commit -m "feat: add CLI"
```

---

### Task 12: Built-in Skills

**Files:**
- Create: `loop_agent/skills/writing/SKILL.md`
- Create: `loop_agent/skills/coding/SKILL.md`
- Create: `loop_agent/skills/research/SKILL.md`
- Modify: `pyproject.toml` to include package data
- Create: `tests/test_builtin_skills.py`

**Interfaces:**
- Produces: `writing`, `coding`, `research` skills

- [ ] **Step 1: Write failing test**

```python
# tests/test_builtin_skills.py
from loop_agent.agent.skills import SkillsLoader


def test_builtin_skills_loaded():
    loader = SkillsLoader()
    names = {s.name for s in loader.skills}
    assert "writing" in names
    assert "coding" in names
    assert "research" in names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_builtin_skills.py -v
```

Expected: AssertionError (skills missing).

- [ ] **Step 3: Create skill files**

```markdown
<!-- loop_agent/skills/writing/SKILL.md -->
---
name: writing
description: Help the user write, edit, and improve text.
category: writing
---

## Workflow

1. Understand the user's intent, audience, and tone.
2. Produce a draft.
3. Offer to revise based on feedback.
```

```markdown
<!-- loop_agent/skills/coding/SKILL.md -->
---
name: coding
description: Help the user write, review, and run code.
category: coding
---

## Workflow

1. Read existing files if needed.
2. Write minimal, correct code.
3. Suggest how to test or run it.
```

```markdown
<!-- loop_agent/skills/research/SKILL.md -->
---
name: research
description: Answer questions by reasoning and using available tools.
category: research
---

## Workflow

1. Break the question into sub-questions.
2. Use tools to gather facts if needed.
3. Synthesize a clear answer with sources.
```

- [ ] **Step 4: Ensure package data includes skill files**

Modify `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"loop_agent" = ["skills/**/SKILL.md"]
```

Reinstall:
```bash
pip install -e ".[dev]"
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_builtin_skills.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add loop_agent/skills/ pyproject.toml tests/test_builtin_skills.py
git commit -m "feat: add built-in skills"
```

---

### Task 13: Final Integration

**Files:**
- Create: `README.md`
- Modify: none
- Test: run actual CLI command

- [ ] **Step 1: Create `README.md`**

```markdown
# loop-agent

Generic ReAct agent framework with skills and tools.

## Install

```bash
pip install -e ".[dev]"
```

## Configure

Copy `.env.example` to `.env` and set your LLM key.

## Run

```bash
loop-agent run "Use echo to say hello"
loop-agent skills list
loop-agent tools list
```

## Test

```bash
pytest
```
```

- [ ] **Step 2: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Test CLI with echo**

Configure `.env` with a real key, then run:

```bash
loop-agent run "Use the echo tool to reply with hello"
```

Expected: final answer contains "hello".

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

## Self-Review

### Spec Coverage

| Spec Section | Plan Task |
|--------------|-----------|
| Project scaffold | Task 1 |
| BaseTool + ToolRegistry | Task 2 |
| Skill system | Task 3, 4 |
| WorkspaceMemory | Task 5 |
| ContextBuilder | Task 6 |
| Provider layer | Task 7 |
| TraceWriter | Task 8 |
| Built-in tools | Task 9 |
| AgentLoop | Task 10 |
| CLI | Task 11 |
| Built-in skills | Task 12 |
| Integration / README | Task 13 |

### Placeholder Scan

- No TBD/TODO.
- Every code step includes complete code.
- Every test step includes complete test code.
- Exact file paths provided.

### Type Consistency

- `ToolRegistry.execute(name, params)` signature consistent across tasks.
- `ChatLLM.stream_chat()` signature consistent.
- `AgentLoop.run()` return dict keys consistent.

### Decomposition Note

Phase 1 is scoped to a single runnable package. API server and MCP server are explicitly out of scope and reserved for Phase 2.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-03-loop-agent-phase1.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach do you want?
