"""Test the manual tool-use loop with a stubbed Anthropic client."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fantasy_assistant.agent import AssistantManager
from fantasy_assistant.config import Config
from fantasy_assistant.context import ToolContext


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(tool_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


class FakeMessages:
    """Returns a scripted sequence of responses on successive create() calls."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeAnthropic:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


@pytest.fixture
def ctx(fake_client, player_data, fake_news):
    return ToolContext(
        client=fake_client,
        players=player_data,
        news=fake_news,
        user_id="user_me",
        username="me",
        league_id="league_1",
        season="2025",
        week=4,
    )


def make_config(web_search=False):
    return Config(
        anthropic_api_key="key",
        sleeper_username="me",
        league_id="league_1",
        season="2025",
        model="claude-opus-4-8",
        effort="high",
        web_search=web_search,
    )


def test_agent_runs_tool_then_answers(ctx):
    responses = [
        SimpleNamespace(
            stop_reason="tool_use",
            content=[tool_block("t1", "get_standings", {})],
        ),
        SimpleNamespace(
            stop_reason="end_turn",
            content=[text_block("You are in first place.")],
        ),
    ]
    reported = []
    agent = AssistantManager(
        make_config(),
        ctx,
        client=FakeAnthropic(responses),
        tool_reporter=lambda name, args: reported.append(name),
    )
    answer = agent.send("How am I doing?")
    assert answer == "You are in first place."
    assert reported == ["get_standings"]

    # The tool result was fed back as a user message.
    roles = [m["role"] for m in agent.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
    tool_result_msg = agent.messages[2]["content"][0]
    assert tool_result_msg["type"] == "tool_result"
    assert tool_result_msg["tool_use_id"] == "t1"


def test_agent_handles_unknown_tool(ctx):
    responses = [
        SimpleNamespace(
            stop_reason="tool_use",
            content=[tool_block("t1", "does_not_exist", {})],
        ),
        SimpleNamespace(stop_reason="end_turn", content=[text_block("done")]),
    ]
    agent = AssistantManager(make_config(), ctx, client=FakeAnthropic(responses))
    agent.send("hi")
    result = agent.messages[2]["content"][0]["content"]
    assert "unknown tool" in result


def test_agent_immediate_answer_without_tools(ctx):
    responses = [
        SimpleNamespace(stop_reason="end_turn", content=[text_block("hello")]),
    ]
    agent = AssistantManager(make_config(), ctx, client=FakeAnthropic(responses))
    assert agent.send("hi") == "hello"


def server_tool_block(name, tool_input):
    return SimpleNamespace(type="server_tool_use", name=name, input=tool_input)


def test_agent_resumes_after_pause_turn(ctx):
    # A server-side web search pauses the turn; the loop must re-send to resume
    # rather than returning early, and should report the server tool call.
    responses = [
        SimpleNamespace(
            stop_reason="pause_turn",
            content=[server_tool_block("web_search", {"query": "Josh Allen injury"})],
        ),
        SimpleNamespace(
            stop_reason="end_turn",
            content=[text_block("Allen is healthy; start him.")],
        ),
    ]
    reported = []
    agent = AssistantManager(
        make_config(web_search=True),
        ctx,
        client=FakeAnthropic(responses),
        tool_reporter=lambda name, args: reported.append(name),
    )
    answer = agent.send("Is Josh Allen ok to start?")
    assert answer == "Allen is healthy; start him."
    assert reported == ["web_search"]
    assert len(agent.client.messages.calls) == 2  # resumed, not returned early


def test_web_search_tool_toggle(ctx):
    enabled = AssistantManager(make_config(web_search=True), ctx, client=FakeAnthropic([]))
    assert any(t.get("name") == "web_search" for t in enabled._api_tools)

    disabled = AssistantManager(make_config(web_search=False), ctx, client=FakeAnthropic([]))
    assert not any(t.get("name") == "web_search" for t in disabled._api_tools)
