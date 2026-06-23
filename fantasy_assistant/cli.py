"""Command-line entry point for the assistant manager agent.

Usage:
    fantasy-assistant chat                 # interactive REPL
    fantasy-assistant ask "who do I start at flex?"
    fantasy-assistant leagues              # list your leagues for the season
"""

from __future__ import annotations

import argparse
import sys

from .agent import AssistantManager
from .config import Config
from .context import ContextError, resolve_context
from .sleeper_client import SleeperClient, SleeperError


def _build_agent(config: Config) -> AssistantManager:
    if not config.anthropic_api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Export it or add it to a .env file."
        )
    client = SleeperClient()
    ctx = resolve_context(client, config)
    print(
        f"League: {ctx.league_id}  |  Season {ctx.season}, week {ctx.week}  |  "
        f"Manager: {ctx.username}",
        file=sys.stderr,
    )

    def report(name: str, args: dict) -> None:
        detail = ", ".join(f"{k}={v}" for k, v in args.items())
        print(f"  · {name}({detail})", file=sys.stderr)

    return AssistantManager(config, ctx, tool_reporter=report)


def _cmd_leagues(config: Config) -> int:
    if not config.sleeper_username:
        raise SystemExit("SLEEPER_USERNAME is not set.")
    with SleeperClient() as client:
        state = client.get_nfl_state()
        season = config.season or state.get("season")
        user = client.get_user(config.sleeper_username)
        leagues = client.get_user_leagues(user["user_id"], season)
        if not leagues:
            print(f"No NFL leagues found for {config.sleeper_username} in {season}.")
            return 0
        print(f"Leagues for {config.sleeper_username} in {season}:")
        for lg in leagues:
            print(f"  {lg['league_id']}  {lg.get('name', '?')}")
    return 0


def _cmd_ask(config: Config, question: str) -> int:
    agent = _build_agent(config)
    print(agent.send(question))
    return 0


def _cmd_chat(config: Config) -> int:
    agent = _build_agent(config)
    print("Assistant manager ready. Type 'exit' to quit.\n")
    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if question.lower() in ("exit", "quit", ":q"):
            return 0
        if not question:
            continue
        print(f"\n{agent.send(question)}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fantasy-assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("chat", help="interactive chat with the assistant manager")
    ask = sub.add_parser("ask", help="ask a single question and print the answer")
    ask.add_argument("question", help="the question to ask")
    sub.add_parser("leagues", help="list your Sleeper leagues for the season")

    args = parser.parse_args(argv)
    config = Config.from_env()

    try:
        if args.command == "leagues":
            return _cmd_leagues(config)
        if args.command == "ask":
            return _cmd_ask(config, args.question)
        if args.command == "chat":
            return _cmd_chat(config)
    except (ContextError, SleeperError) as exc:
        raise SystemExit(f"error: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
