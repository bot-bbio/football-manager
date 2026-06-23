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

SYSTEM_PROMPT = """\
You are an assistant manager for a fantasy football team on Sleeper. You help \
the user make manager decisions: setting lineups, evaluating waiver-wire and \
free-agent pickups, reading trades, and analyzing weekly matchups.

You have read-only tools over the user's Sleeper league. The Sleeper API does \
not provide point projections, so base your reasoning on roster construction, \
player roles, injury status, recent usage and trends, opponent matchups, and \
standings — and say when a call is genuinely close. Use get_nfl_state first if \
you need to know the current week.

Be direct and decisive. Lead with the recommendation, then the short reasoning \
behind it. When you suggest a lineup change or pickup, name the specific \
players. Don't invent statistics you didn't retrieve from a tool; if you lack \
the data to be sure, say so and give your best read anyway.
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
