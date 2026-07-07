from __future__ import annotations

import argparse
import sys

from loop_agent.cli import commands


def main() -> int:
    parser = argparse.ArgumentParser(prog="loop-agent", description="Generic ReAct agent")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a single prompt")
    run_parser.add_argument("prompt", nargs="+", help="User prompt")

    run_supervised_parser = subparsers.add_parser(
        "run-supervised", help="Run supervised multi-agent report workflow"
    )
    run_supervised_parser.add_argument("prompt", nargs="+", help="Task description")
    run_supervised_parser.add_argument(
        "--session-id", default="", help="Optional session ID"
    )

    subparsers.add_parser("skills", help="List skills")
    subparsers.add_parser("tools", help="List tools")

    args = parser.parse_args()

    if args.command == "run":
        prompt = " ".join(args.prompt)
        result = commands.run_command(prompt)
        print(result.get("content", ""))
        return 0 if result.get("status") == "success" else 1

    if args.command == "run-supervised":
        prompt = " ".join(args.prompt)
        result = commands.run_supervised_command(
            prompt, session_id=args.session_id
        )
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
