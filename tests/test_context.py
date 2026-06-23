"""Tests for context resolution (username -> league -> week)."""

from __future__ import annotations

import pytest

from fantasy_assistant.config import Config
from fantasy_assistant.context import ContextError, resolve_context


def make_config(**overrides) -> Config:
    base = dict(
        anthropic_api_key="key",
        sleeper_username="me",
        league_id=None,
        season=None,
        model="claude-opus-4-8",
        effort="high",
    )
    base.update(overrides)
    return Config(**base)


def test_resolve_autodiscovers_single_league(fake_client, monkeypatch):
    # Avoid touching the real player cache/network.
    from fantasy_assistant import context as ctx_mod

    monkeypatch.setattr(
        ctx_mod.PlayerData, "load", classmethod(lambda cls, client: cls({}))
    )
    ctx = resolve_context(fake_client, make_config())
    assert ctx.league_id == "league_1"
    assert ctx.user_id == "user_me"
    assert ctx.week == 4
    assert ctx.season == "2025"


def test_resolve_requires_username(fake_client):
    with pytest.raises(ContextError, match="SLEEPER_USERNAME"):
        resolve_context(fake_client, make_config(sleeper_username=None))


def test_resolve_errors_on_multiple_leagues(fake_client, monkeypatch):
    monkeypatch.setattr(
        fake_client,
        "get_user_leagues",
        lambda user_id, season: [
            {"league_id": "a", "name": "A"},
            {"league_id": "b", "name": "B"},
        ],
    )
    with pytest.raises(ContextError, match="multiple leagues"):
        resolve_context(fake_client, make_config())
