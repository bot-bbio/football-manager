"""Resolve a Config into the concrete identifiers the tools need.

Turns a username + (optional) league id into a user id, an active league, the
current season, and the current week, so tools don't each repeat that lookup.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .news_client import ESPNClient
from .players import PlayerData
from .sleeper_client import SleeperClient, SleeperError


@dataclass
class ToolContext:
    client: SleeperClient
    players: PlayerData
    news: ESPNClient
    user_id: str
    username: str
    league_id: str
    season: str
    week: int


class ContextError(RuntimeError):
    """Raised when we cannot determine which user/league to operate on."""


def resolve_context(
    client: SleeperClient,
    config: Config,
    *,
    news_client: ESPNClient | None = None,
) -> ToolContext:
    if not config.sleeper_username:
        raise ContextError(
            "SLEEPER_USERNAME is not set. Set it to your Sleeper username."
        )

    state = client.get_nfl_state()
    season = config.season or state.get("season")
    if not season:
        raise ContextError("could not determine the current NFL season")
    # During the offseason `week` can be 0; fall back to 1 for lookups.
    week = state.get("week") or state.get("display_week") or 1

    try:
        user = client.get_user(config.sleeper_username)
    except SleeperError as exc:
        raise ContextError(
            f"Sleeper user '{config.sleeper_username}' not found ({exc})"
        ) from exc
    user_id = user["user_id"]

    league_id = config.league_id or _autodiscover_league(client, user_id, season)

    players = PlayerData.load(client)
    return ToolContext(
        client=client,
        players=players,
        news=news_client or ESPNClient(),
        user_id=user_id,
        username=config.sleeper_username,
        league_id=league_id,
        season=str(season),
        week=int(week),
    )


def _autodiscover_league(client: SleeperClient, user_id: str, season: str) -> str:
    leagues = client.get_user_leagues(user_id, season)
    if not leagues:
        raise ContextError(
            f"no NFL leagues found for this user in {season}. "
            "Set SLEEPER_LEAGUE_ID explicitly."
        )
    if len(leagues) == 1:
        return leagues[0]["league_id"]
    names = ", ".join(
        f"{lg.get('name', '?')} (id {lg['league_id']})" for lg in leagues
    )
    raise ContextError(
        "multiple leagues found; set SLEEPER_LEAGUE_ID to one of: " + names
    )
