"""The assistant manager agent: a manual tool-use loop over Claude.

We drive the agentic loop ourselves (rather than the SDK tool runner) so the
caller keeps full control of conversation history for multi-turn chat and can
surface which tools were called.
"""

from __future__ import annotations

from typing import Any, Callable

import anthropic

from .config import Config
from .context import ToolContext
from .tools import Tool, build_tools

# Server-side web search tool version. web_search_20260209 (dynamic filtering)
# is correct for the default claude-opus-4-8; models older than Opus 4.6 /
# Sonnet 4.6 require the basic variant web_search_20250305 instead.
WEB_SEARCH_TOOL_VERSION = "web_search_20260209"

SYSTEM_PROMPT = """\
You are an assistant manager for a fantasy football team on Sleeper. You help \
the user make manager decisions: setting lineups, evaluating waiver-wire and \
free-agent pickups, reading trades, and analyzing weekly matchups.

You have read-only tools over the user's Sleeper league. The Sleeper API does \
not provide point projections, so base your reasoning on roster construction, \
player roles, injury status, recent usage and trends, opponent matchups, and \
standings — and say when a call is genuinely close. Use get_nfl_state first if \
you need to know the current week.

Verify time-sensitive calls before committing to them. Sleeper's roster data \
can lag real life, so when a decision turns on a player's health, role, or a \
recent development, check get_injuries and get_player_news first. For anything \
that may have changed within the last day or so — late injury news, depth-chart \
shuffles, weather — use web_search. Cite the source (ESPN, or the site \
web_search surfaces) for any claim that came from news rather than a Sleeper \
tool, and never invent statistics or reports you didn't retrieve.

Be direct and decisive. Lead with the recommendation, then the short reasoning \
behind it. When you suggest a lineup change or pickup, name the specific \
players. If you lack the data to be sure, say so and give your best read anyway.
"""

# Reporter signature: (tool_name, tool_input) -> None
ToolReporter = Callable[[str, dict[str, Any]], None]


class AssistantManager:
    def __init__(
        self,
        config: Config,
        ctx: ToolContext,
        *,
        client: anthropic.Anthropic | None = None,
        tool_reporter: ToolReporter | None = None,
    ) -> None:
        self.config = config
        self.ctx = ctx
        self.client = client or anthropic.Anthropic(api_key=config.anthropic_api_key)
        self._tools: list[Tool] = build_tools(ctx)
        self._dispatch = {t.name: t.handler for t in self._tools}
        self._api_tools = [t.to_api() for t in self._tools]
        if config.web_search:
            # Server-side tool: Anthropic runs it; there is no local handler, so
            # it is not added to the dispatch map.
            self._api_tools.append(
                {"type": WEB_SEARCH_TOOL_VERSION, "name": "web_search", "max_uses": 5}
            )
        self.messages: list[dict[str, Any]] = []
        self._report = tool_reporter or (lambda name, args: None)

    def _run_tool(self, name: str, args: dict[str, Any]) -> str:
        self._report(name, args)
        handler = self._dispatch.get(name)
        if handler is None:
            return f"error: unknown tool '{name}'"
        try:
            return handler(args)
        except Exception as exc:  # surface tool errors back to the model
            return f"error: {type(exc).__name__}: {exc}"

    def send(self, user_message: str, *, max_iterations: int = 12) -> str:
        """Send a user turn and return the assistant's final text."""
        self.messages.append({"role": "user", "content": user_message})

        for _ in range(max_iterations):
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                thinking={"type": "adaptive"},
                output_config={"effort": self.config.effort},
                tools=self._api_tools,
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.content})

            # Surface server-side tool calls (e.g. web_search) for visibility;
            # they have already run on Anthropic's side.
            for block in response.content:
                if getattr(block, "type", None) == "server_tool_use":
                    self._report(block.name, dict(block.input))

            # A server tool hit its internal iteration limit; re-send to resume.
            if response.stop_reason == "pause_turn":
                continue

            if response.stop_reason != "tool_use":
                return _final_text(response.content)

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._run_tool(block.name, dict(block.input))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            self.messages.append({"role": "user", "content": tool_results})

        return (
            "I hit the tool-call limit for this question. Ask me to continue or "
            "narrow the request."
        )


def _final_text(content: list[Any]) -> str:
    parts = [block.text for block in content if getattr(block, "type", None) == "text"]
    return "\n".join(parts).strip() or "(no response)"
