"""Thin client for ESPN's public, read-only NFL news and injury endpoints.

ESPN exposes league news and a leaguewide injury report as unauthenticated
JSON. These ``site.api`` endpoints are undocumented but stable. Like the Sleeper
client, this only ever issues GET requests — it is used to verify roster
decisions against current real-world reporting (injury designations, role
changes, breaking developments) rather than to change anything.
"""

from __future__ import annotations

from typing import Any

import httpx

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
DEFAULT_TIMEOUT = 15.0


class ESPNError(RuntimeError):
    """Raised when the ESPN API returns an error or unexpected payload."""


class ESPNClient:
    """Minimal wrapper around the ESPN NFL news and injuries endpoints."""

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

    def __enter__(self) -> "ESPNClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- low level ---------------------------------------------------------

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:  # network/timeout/TLS
            raise ESPNError(f"request to {url} failed: {exc}") from exc
        if response.status_code == 404:
            raise ESPNError(f"not found: {path}")
        if response.status_code >= 400:
            raise ESPNError(f"ESPN returned {response.status_code} for {path}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ESPNError(f"non-JSON response for {path}: {exc}") from exc
        if data is None:
            raise ESPNError(f"no data for {path}")
        return data

    # -- endpoints ---------------------------------------------------------

    def get_news(self, limit: int = 50) -> dict[str, Any]:
        """Recent leaguewide NFL news. ``articles`` carries headlines, summaries,
        publish times, links, and athlete/team ``categories``."""
        return self._get(f"news?limit={int(limit)}")

    def get_injuries(self) -> dict[str, Any]:
        """The leaguewide injury report, grouped by team under ``injuries``."""
        return self._get("injuries")
