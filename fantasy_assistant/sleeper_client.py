"""Thin client for Sleeper's public read-only HTTP API.

Sleeper exposes league, roster, matchup, transaction, and player data without
authentication. See https://docs.sleeper.com/ . This client only ever issues
GET requests — it cannot modify a league.
"""

from __future__ import annotations

from typing import Any

import httpx

BASE_URL = "https://api.sleeper.app/v1"
DEFAULT_TIMEOUT = 15.0


class SleeperError(RuntimeError):
    """Raised when the Sleeper API returns an error or unexpected payload."""


class SleeperClient:
    """Minimal wrapper around the Sleeper v1 endpoints used by the agent."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # Allow injecting a client (e.g. with a MockTransport) for tests.
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "SleeperClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- low level ---------------------------------------------------------

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:  # network/timeout/TLS
            raise SleeperError(f"request to {url} failed: {exc}") from exc
        if response.status_code == 404:
            raise SleeperError(f"not found: {path}")
        if response.status_code >= 400:
            raise SleeperError(
                f"Sleeper returned {response.status_code} for {path}"
            )
        # Sleeper returns the JSON literal `null` for unknown users/leagues.
        data = response.json()
        if data is None:
            raise SleeperError(f"no data for {path}")
        return data

    # -- state -------------------------------------------------------------

    def get_nfl_state(self) -> dict[str, Any]:
        """Current NFL season/week metadata."""
        return self._get("state/nfl")

    # -- users & leagues ---------------------------------------------------

    def get_user(self, username_or_id: str) -> dict[str, Any]:
        """Resolve a Sleeper username (or user id) to a user object."""
        return self._get(f"user/{username_or_id}")

    def get_user_leagues(self, user_id: str, season: str) -> list[dict[str, Any]]:
        return self._get(f"user/{user_id}/leagues/nfl/{season}")

    def get_league(self, league_id: str) -> dict[str, Any]:
        return self._get(f"league/{league_id}")

    def get_rosters(self, league_id: str) -> list[dict[str, Any]]:
        return self._get(f"league/{league_id}/rosters")

    def get_league_users(self, league_id: str) -> list[dict[str, Any]]:
        return self._get(f"league/{league_id}/users")

    def get_matchups(self, league_id: str, week: int) -> list[dict[str, Any]]:
        return self._get(f"league/{league_id}/matchups/{week}")

    def get_transactions(self, league_id: str, week: int) -> list[dict[str, Any]]:
        return self._get(f"league/{league_id}/transactions/{week}")

    # -- players -----------------------------------------------------------

    def get_all_players(self) -> dict[str, Any]:
        """The full NFL player map (player_id -> info). Large (~5 MB)."""
        return self._get("players/nfl")

    def get_trending_players(
        self, kind: str = "add", *, lookback_hours: int = 24, limit: int = 25
    ) -> list[dict[str, Any]]:
        if kind not in ("add", "drop"):
            raise SleeperError("trending kind must be 'add' or 'drop'")
        path = (
            f"players/nfl/trending/{kind}"
            f"?lookback_hours={lookback_hours}&limit={limit}"
        )
        return self._get(path)
