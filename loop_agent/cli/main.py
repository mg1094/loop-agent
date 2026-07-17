from __future__ import annotations

import argparse
import sys

from loop_agent import __version__
from loop_agent.cli import commands


def _add_run_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    run_parser = subparsers.add_parser("run", help="Run a single prompt")
    run_parser.add_argument("prompt", nargs="+", help="User prompt")
    run_parser.add_argument("--session-id", default="", help="Optional session ID")
    return run_parser


def _add_run_supervised_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    run_supervised_parser = subparsers.add_parser(
        "run-supervised", help="Run supervised multi-agent report workflow"
    )
    run_supervised_parser.add_argument("prompt", nargs="+", help="Task description")
    run_supervised_parser.add_argument(
        "--session-id", default="", help="Optional session ID"
    )
    return run_supervised_parser


def _add_sessions_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    sessions_parser = subparsers.add_parser("sessions", help="Manage sessions")
    sessions_sub = sessions_parser.add_subparsers(dest="sessions_command")

    sessions_sub.add_parser("list", help="List sessions")

    search_parser = sessions_sub.add_parser("search", help="Search session messages")
    search_parser.add_argument("query", help="Search substring")
    search_parser.add_argument(
        "--limit", type=int, default=25, help="Max sessions to return (default 25)"
    )

    delete_parser = sessions_sub.add_parser("delete", help="Delete a session")
    delete_parser.add_argument("session_id", help="Session ID to delete")

    return sessions_parser


def _add_tools_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    tools_parser = subparsers.add_parser("tools", help="Tool commands")
    tools_sub = tools_parser.add_subparsers(dest="tools_command")

    tools_sub.add_parser("list", help="List tools")

    run_parser = tools_sub.add_parser("run", help="Run a tool by name")
    run_parser.add_argument("tool_name", help="Tool name")
    run_parser.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Tool argument as key=value (repeatable)",
    )
    return tools_parser


def _add_trace_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    trace_parser = subparsers.add_parser("trace", help="Replay a run trace")
    trace_parser.add_argument("run_id", help="Run id or suffix")
    return trace_parser


def _parse_tool_args(raw_args: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in raw_args:
        if "=" not in item:
            raise argparse.ArgumentTypeError(
                f"Tool argument must be key=value, got: {item!r}"
            )
        key, value = item.split("=", 1)
        out[key] = value
    return out


def _print_sessions_table(rows: list[dict]) -> None:
    if not rows:
        print("No sessions.")
        return
    # Header
    print(f"{'session_id':<32} {'messages':>8}  {'updated_at':<25}")
    for row in rows:
        print(
            f"{row['session_id']:<32} {row['message_count']:>8}  {row['updated_at']:<25}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="loop-agent",
        description="Generic ReAct agent framework",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"loop-agent {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")
    _add_run_parser(subparsers)
    _add_run_supervised_parser(subparsers)
    subparsers.add_parser("skills", help="List skills")
    _add_tools_parser(subparsers)
    _add_sessions_parser(subparsers)
    _add_trace_parser(subparsers)

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------
    if args.command == "run":
        prompt = " ".join(args.prompt)
        result = commands.run_command(prompt, session_id=args.session_id)
        print(result.get("content", ""))
        return 0 if result.get("status") == "success" else 1

    # ------------------------------------------------------------------
    # run-supervised
    # ------------------------------------------------------------------
    if args.command == "run-supervised":
        prompt = " ".join(args.prompt)
        result = commands.run_supervised_command(
            prompt, session_id=args.session_id
        )
        print(result.get("content", ""))
        return 0 if result.get("status") == "success" else 1

    # ------------------------------------------------------------------
    # skills
    # ------------------------------------------------------------------
    if args.command == "skills":
        print(commands.list_skills())
        return 0

    # ------------------------------------------------------------------
    # tools
    # ------------------------------------------------------------------
    if args.command == "tools":
        if args.tools_command == "list" or args.tools_command is None:
            print(commands.list_tools())
            return 0
        if args.tools_command == "run":
            tool_args = _parse_tool_args(args.arg)
            try:
                output = commands.run_tool(args.tool_name, tool_args)
            except KeyError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            print(output)
            return 0
        return 0

    # ------------------------------------------------------------------
    # sessions
    # ------------------------------------------------------------------
    if args.command == "sessions":
        if args.sessions_command == "list" or args.sessions_command is None:
            rows = commands.list_sessions()
            _print_sessions_table(rows)
            return 0
        if args.sessions_command == "search":
            rows = commands.search_sessions(args.query, limit=args.limit)
            _print_sessions_table(rows)
            return 0
        if args.sessions_command == "delete":
            deleted = commands.delete_session(args.session_id)
            print("deleted" if deleted else "not found")
            return 0 if deleted else 1
        return 0

    # ------------------------------------------------------------------
    # trace
    # ------------------------------------------------------------------
    if args.command == "trace":
        try:
            commands.replay_trace(args.run_id)
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
