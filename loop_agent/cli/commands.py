from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def _default_allowed_roots() -> list[Path]:
    """Sandbox file tools to ``cwd`` and ``cwd/runs`` by default."""
    import os

    if os.environ.get("LOOP_AGENT_UNRESTRICTED_FILES"):
        return []
    roots = [Path.cwd().resolve()]
    runs_dir = (Path.cwd() / "runs").resolve()
    # Always include the runs dir even if it doesn't exist yet — agents
    # create their own output subdirs under runs/<run_id>/.
    roots.append(runs_dir)
    return roots


def _build_streaming_components() -> Tuple[Any, ChatLLM, WorkspaceMemory, SessionStore]:
    """Build the agent's collaborators. Shared by CLI + streaming SSE path."""
    _load_env()
    skills_loader = SkillsLoader()
    registry = build_registry(
        skills_loader=skills_loader,
        allowed_roots=_default_allowed_roots(),
    )
    llm = ChatLLM()
    memory = WorkspaceMemory()
    store = SessionStore()
    return registry, llm, memory, store


def _run_agent(user_message: str, session_id: str = "") -> Dict[str, Any]:
    registry, llm, memory, store = _build_streaming_components()
    loop = AgentLoop(registry, llm, memory, session_store=store)
    return loop.run(user_message, session_id=session_id)


def run_command(user_message: str, session_id: str = "") -> Dict[str, Any]:
    return _run_agent(user_message, session_id=session_id)


def _run_supervised(task: str, session_id: str = "") -> Dict[str, Any]:
    _load_env()
    llm = ChatLLM()
    store = SessionStore()
    from loop_agent.orchestration.supervisor import Supervisor

    supervisor = Supervisor(llm=llm, session_store=store)
    return supervisor.run(task, session_id=session_id)


def run_supervised_command(task: str, session_id: str = "") -> Dict[str, Any]:
    return _run_supervised(task, session_id=session_id)


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


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
def _store() -> SessionStore:
    _load_env()
    return SessionStore()


def list_sessions() -> List[Dict[str, Any]]:
    return _store().list_sessions_with_meta()


def search_sessions(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    return _store().search_sessions(query, limit=limit)


def delete_session(session_id: str) -> bool:
    return _store().delete_session(session_id)


def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    return _store().load_messages(session_id)


# ---------------------------------------------------------------------------
# Ad-hoc tool execution
# ---------------------------------------------------------------------------
def run_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """Run a single tool by name with raw arguments.

    Used by ``loop-agent tools run <name> --key value`` for quick
    tool debugging without spinning up an AgentLoop.
    """
    _load_env()
    registry = build_registry(allowed_roots=_default_allowed_roots())
    if tool_name not in registry:
        raise KeyError(f"Tool '{tool_name}' not found")
    return registry.execute(tool_name, args)


# ---------------------------------------------------------------------------
# Trace replay
# ---------------------------------------------------------------------------
def replay_trace(run_id: str, runs_dir: Path | str = "runs") -> None:
    """Print a ``trace.jsonl`` file in a human-readable form.

    ``run_id`` may be the full ``YYYYMMDD_HHMMSS_abcdef`` directory name
    or just the 6-char suffix; the function looks for a unique match
    under ``runs_dir``.
    """
    root = Path(runs_dir)
    if not root.exists():
        raise FileNotFoundError(f"No runs directory: {root.resolve()}")

    candidates = [
        p for p in root.iterdir()
        if p.is_dir() and p.name.endswith(run_id) or p.name == run_id
    ]
    if not candidates:
        raise FileNotFoundError(f"No run matching '{run_id}' in {root.resolve()}")
    if len(candidates) > 1:
        raise ValueError(
            f"Ambiguous run id '{run_id}'; matches: {[p.name for p in candidates]}"
        )

    trace_file = candidates[0] / "trace.jsonl"
    if not trace_file.exists():
        raise FileNotFoundError(f"No trace.jsonl in {candidates[0]}")

    for line in trace_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        _print_trace_entry(entry)


def _print_trace_entry(entry: Dict[str, Any]) -> None:
    """Render one trace line as readable text."""
    kind = entry.get("type", "unknown")
    ts = entry.get("ts", "")
    prefix = f"[{ts}] " if ts else ""
    if kind == "start":
        print(f"{prefix}Run started: {entry.get('prompt', '')}")
    elif kind == "message":
        print(f"{prefix}[{entry.get('role')}] {entry.get('content', '')}")
    elif kind == "assistant":
        tool_calls = entry.get("tool_calls", [])
        names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
        print(f"{prefix}Assistant calls: {', '.join(names) if names else '(text)'}")
    elif kind == "tool_result":
        print(f"{prefix}Tool '{entry.get('name')}' -> {entry.get('content', '')[:200]}")
    elif kind == "tool_error":
        print(
            f"{prefix}Tool '{entry.get('name')}' FAILED "
            f"({entry.get('exception_type')}): {entry.get('error')}"
        )
    elif kind == "final":
        print(f"{prefix}Final ({entry.get('status')}): {entry.get('content', '')}")
    elif kind == "error":
        print(f"{prefix}ERROR: {entry.get('error', '')}")
    else:
        print(f"{prefix}{kind}: {json.dumps(entry, ensure_ascii=False)}")
