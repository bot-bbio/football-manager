"""Player metadata: caching, lookup, and name resolution.

The full Sleeper player map is ~5 MB and changes slowly, so we cache it to disk
and refresh once a day. This module turns opaque player ids into names and
supports searching by (partial) name.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

from .sleeper_client import SleeperClient

CACHE_TTL_SECONDS = 24 * 60 * 60


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    path = root / "fantasy-assistant"
    path.mkdir(parents=True, exist_ok=True)
    return path


class PlayerData:
    """Indexed view over the Sleeper player map."""

    def __init__(self, players: dict[str, Any]) -> None:
        self.players = players
        self._name_index: dict[str, list[str]] = {}
        for pid, info in players.items():
            for token in self._name_tokens(pid, info):
                self._name_index.setdefault(token, []).append(pid)

    # -- construction ------------------------------------------------------

    @classmethod
    def load(
        cls,
        client: SleeperClient,
        *,
        cache_path: Path | None = None,
        ttl_seconds: int = CACHE_TTL_SECONDS,
    ) -> "PlayerData":
        """Load the player map, using a fresh-enough disk cache when present."""
        path = cache_path or (_cache_dir() / "players_nfl.json")
        if path.exists() and (time.time() - path.stat().st_mtime) < ttl_seconds:
            try:
                return cls(json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError):
                pass  # fall through to a fresh fetch

        players = client.get_all_players()
        try:
            path.write_text(json.dumps(players))
        except OSError:
            pass  # caching is best-effort
        return cls(players)

    # -- lookups -----------------------------------------------------------

    @staticmethod
    def _name_tokens(pid: str, info: dict[str, Any]) -> Iterable[str]:
        full = info.get("full_name")
        if not full:
            # Team defenses and some entries have no full_name.
            first = info.get("first_name") or ""
            last = info.get("last_name") or ""
            full = f"{first} {last}".strip() or info.get("last_name") or pid
        yield full.lower()

    def display_name(self, pid: str) -> str:
        info = self.players.get(pid)
        if not info:
            return pid
        full = info.get("full_name")
        if not full:
            first = info.get("first_name") or ""
            last = info.get("last_name") or ""
            full = f"{first} {last}".strip() or pid
        pos = info.get("position") or "?"
        team = info.get("team") or "FA"
        return f"{full} ({pos} - {team})"

    def get(self, pid: str) -> dict[str, Any] | None:
        return self.players.get(pid)

    def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Return players whose name contains ``query`` (case-insensitive)."""
        q = query.strip().lower()
        if not q:
            return []
        matches: list[tuple[int, str]] = []
        for token, pids in self._name_index.items():
            if q in token:
                # Exact-name matches sort ahead of substring matches.
                rank = 0 if token == q else 1
                for pid in pids:
                    matches.append((rank, pid))
        # De-dupe while keeping the best rank per player.
        best: dict[str, int] = {}
        for rank, pid in matches:
            if pid not in best or rank < best[pid]:
                best[pid] = rank

        def sort_key(pid: str) -> tuple[int, int]:
            search_rank = self.players.get(pid, {}).get("search_rank")
            if not isinstance(search_rank, int):
                search_rank = 1_000_000
            return (best[pid], search_rank)

        ordered = sorted(best, key=sort_key)[:limit]
        return [self._summary(pid) for pid in ordered]

    def _summary(self, pid: str) -> dict[str, Any]:
        info = self.players.get(pid, {})
        return {
            "player_id": pid,
            "name": self.display_name(pid),
            "position": info.get("position"),
            "team": info.get("team"),
            "status": info.get("status"),
            "injury_status": info.get("injury_status"),
            "search_rank": info.get("search_rank"),
        }

    def summary(self, pid: str) -> dict[str, Any]:
        """Public helper returning a compact dict for one player id."""
        return self._summary(pid)
