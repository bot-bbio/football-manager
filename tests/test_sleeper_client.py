"""Tests for the Sleeper client using httpx's MockTransport (no real network)."""

from __future__ import annotations

import httpx
import pytest

from fantasy_assistant.sleeper_client import SleeperClient, SleeperError


def make_client(handler) -> SleeperClient:
    transport = httpx.MockTransport(handler)
    return SleeperClient(client=httpx.Client(transport=transport))


def test_get_user_builds_correct_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"user_id": "u1", "username": "bob"})

    client = make_client(handler)
    user = client.get_user("bob")
    assert user["user_id"] == "u1"
    assert seen["url"] == "https://api.sleeper.app/v1/user/bob"


def test_null_payload_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        # Sleeper returns the JSON literal `null` for unknown users/leagues.
        return httpx.Response(
            200, content=b"null", headers={"content-type": "application/json"}
        )

    client = make_client(handler)
    with pytest.raises(SleeperError):
        client.get_user("ghost")


def test_404_raises_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = make_client(handler)
    with pytest.raises(SleeperError, match="not found"):
        client.get_league("nope")


def test_trending_kind_validation():
    client = make_client(lambda r: httpx.Response(200, json=[]))
    with pytest.raises(SleeperError):
        client.get_trending_players("sideways")


def test_trending_url_includes_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[])

    client = make_client(handler)
    client.get_trending_players("add", lookback_hours=12, limit=5)
    assert "lookback_hours=12" in seen["url"]
    assert "limit=5" in seen["url"]
    assert "trending/add" in seen["url"]
