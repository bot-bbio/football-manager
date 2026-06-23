"""Tests for player indexing, search, and disk caching."""

from __future__ import annotations

import json
import time

from fantasy_assistant.players import PlayerData


def test_display_name_for_player(player_data):
    assert player_data.display_name("100") == "Josh Allen (QB - BUF)"


def test_display_name_for_defense(player_data):
    # Defenses have no full_name; we build one from first/last.
    assert player_data.display_name("BUF") == "Buffalo Bills (DEF - BUF)"


def test_display_name_unknown_id(player_data):
    assert player_data.display_name("does_not_exist") == "does_not_exist"


def test_search_exact_match_ranks_first(player_data):
    results = player_data.search("josh allen")
    assert results[0]["player_id"] == "100"


def test_search_partial_match(player_data):
    results = player_data.search("robinson")
    assert any(r["player_id"] == "200" for r in results)


def test_search_empty_query(player_data):
    assert player_data.search("   ") == []


def test_load_uses_fresh_cache(tmp_path):
    cache = tmp_path / "players.json"
    cache.write_text(json.dumps({"100": {"full_name": "Cached Guy", "position": "QB"}}))

    class BoomClient:
        def get_all_players(self):  # should never be called when cache is fresh
            raise AssertionError("network should not be hit for a fresh cache")

    data = PlayerData.load(BoomClient(), cache_path=cache)
    assert data.get("100")["full_name"] == "Cached Guy"


def test_load_refetches_when_cache_stale(tmp_path):
    cache = tmp_path / "players.json"
    cache.write_text(json.dumps({"old": {}}))
    # Make the cache look old.
    old = time.time() - 10_000
    import os

    os.utime(cache, (old, old))

    class FreshClient:
        def get_all_players(self):
            return {"new": {"full_name": "Fresh", "position": "WR"}}

    data = PlayerData.load(FreshClient(), cache_path=cache, ttl_seconds=1)
    assert "new" in data.players
    # The new data is written back to the cache.
    assert "new" in json.loads(cache.read_text())
