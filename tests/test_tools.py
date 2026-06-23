"""Tests for the agent tools against the fake league fixture."""

from __future__ import annotations

import json

import pytest

from fantasy_assistant.context import ToolContext
from fantasy_assistant.tools import build_tools


@pytest.fixture
def tools(fake_client, player_data):
    ctx = ToolContext(
        client=fake_client,
        players=player_data,
        user_id="user_me",
        username="me",
        league_id="league_1",
        season="2025",
        week=4,
    )
    return {t.name: t for t in build_tools(ctx)}


def call(tools, tool_name, **args):
    return json.loads(tools[tool_name].handler(args))


def test_get_nfl_state(tools):
    result = call(tools, "get_nfl_state")
    assert result["season"] == "2025"
    assert result["week"] == 4


def test_standings_sorted_by_wins(tools):
    rows = call(tools, "get_standings")
    assert rows[0]["owner"] == "My Squad"
    assert rows[0]["wins"] == 3
    assert rows[0]["points_for"] == 420.5


def test_get_my_team(tools):
    team = call(tools, "get_my_team")
    assert team["owner"] == "My Squad"
    assert team["record"] == {"wins": 3, "losses": 1, "ties": 0}
    assert "Josh Allen (QB - BUF)" in team["starters"]
    assert "Some Backup (RB - NYJ)" in team["bench"]


def test_get_team_by_name(tools):
    team = call(tools, "get_team", team="rival")
    assert team["roster_id"] == 2


def test_get_team_unknown(tools):
    result = call(tools, "get_team", team="nobody")
    assert "error" in result
    assert "My Squad" in result["teams"]


def test_get_matchup_current_week(tools):
    matchup = call(tools, "get_matchup")
    assert matchup["week"] == 4
    assert matchup["you"]["owner"] == "My Squad"
    assert matchup["opponent"]["owner"] == "Rival"


def test_lookup_player(tools):
    result = call(tools, "lookup_player", name="bijan")
    assert result[0]["player_id"] == "200"


def test_trending_marks_rostered(tools):
    result = call(tools, "get_trending_players", kind="add")
    by_id = {p["player_id"]: p for p in result["players"]}
    assert by_id["300"]["rostered_in_your_league"] is True   # on my roster
    assert by_id["400"]["rostered_in_your_league"] is True   # on rival roster


def test_free_agents_excludes_rostered_and_unranked(tools):
    # All ranked players are rostered in the fixture, so RB free agents is empty.
    result = call(tools, "get_free_agents", position="RB")
    assert result["free_agents"] == []


def test_transactions_only_complete(tools):
    result = call(tools, "get_transactions", week=4)
    assert len(result["transactions"]) == 1
    txn = result["transactions"][0]
    assert "Some Backup (RB - NYJ)" in txn["adds"]
