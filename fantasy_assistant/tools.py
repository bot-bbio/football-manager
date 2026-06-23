"""Tool definitions exposed to the agent.

Each tool is a read-only operation against Sleeper data. Tools return JSON
strings so Claude receives structured data it can reason over. Handlers take a
single dict of parsed arguments; the agent loop dispatches by name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from .context import ToolContext
from .sleeper_client import SleeperError

Handler = Callable[[dict[str, Any]], str]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler

    def to_api(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def _dump(data: Any) -> str:
    return json.dumps(data, default=str)


def _points(settings: dict[str, Any], key: str) -> float:
    whole = settings.get(key) or 0
    decimal = settings.get(f"{key}_decimal") or 0
    return round(whole + decimal / 100, 2)


def build_tools(ctx: ToolContext) -> list[Tool]:
    """Build the tool list bound to a resolved context."""

    def _owner_names() -> dict[str, str]:
        """roster_id -> human team/owner name."""
        users = {u["user_id"]: u for u in ctx.client.get_league_users(ctx.league_id)}
        names: dict[str, str] = {}
        for roster in ctx.client.get_rosters(ctx.league_id):
            owner_id = roster.get("owner_id")
            user = users.get(owner_id, {})
            team_name = (user.get("metadata") or {}).get("team_name")
            names[str(roster["roster_id"])] = (
                team_name or user.get("display_name") or f"Roster {roster['roster_id']}"
            )
        return names

    def _my_roster() -> dict[str, Any]:
        for roster in ctx.client.get_rosters(ctx.league_id):
            if roster.get("owner_id") == ctx.user_id:
                return roster
        raise SleeperError("could not find your roster in this league")

    def _roster_view(roster: dict[str, Any], owner: str) -> dict[str, Any]:
        settings = roster.get("settings") or {}
        starters = roster.get("starters") or []
        all_players = roster.get("players") or []
        bench = [p for p in all_players if p not in starters]
        return {
            "roster_id": roster.get("roster_id"),
            "owner": owner,
            "record": {
                "wins": settings.get("wins", 0),
                "losses": settings.get("losses", 0),
                "ties": settings.get("ties", 0),
            },
            "points_for": _points(settings, "fpts"),
            "points_against": _points(settings, "fpts_against"),
            "starters": [ctx.players.display_name(p) for p in starters if p != "0"],
            "bench": [ctx.players.display_name(p) for p in bench],
            "ir": [ctx.players.display_name(p) for p in (roster.get("reserve") or [])],
        }

    # -- handlers ----------------------------------------------------------

    def get_nfl_state(_: dict[str, Any]) -> str:
        state = ctx.client.get_nfl_state()
        return _dump(
            {
                "season": state.get("season"),
                "season_type": state.get("season_type"),
                "week": state.get("week"),
                "display_week": state.get("display_week"),
            }
        )

    def get_league_info(_: dict[str, Any]) -> str:
        league = ctx.client.get_league(ctx.league_id)
        settings = league.get("settings") or {}
        return _dump(
            {
                "name": league.get("name"),
                "season": league.get("season"),
                "total_teams": settings.get("num_teams") or league.get("total_rosters"),
                "scoring_type": league.get("scoring_settings", {}).get("rec"),
                "roster_positions": league.get("roster_positions"),
                "status": league.get("status"),
                "playoff_week_start": settings.get("playoff_week_start"),
            }
        )

    def get_standings(_: dict[str, Any]) -> str:
        names = _owner_names()
        rows = []
        for roster in ctx.client.get_rosters(ctx.league_id):
            settings = roster.get("settings") or {}
            rid = str(roster["roster_id"])
            rows.append(
                {
                    "owner": names.get(rid, rid),
                    "wins": settings.get("wins", 0),
                    "losses": settings.get("losses", 0),
                    "ties": settings.get("ties", 0),
                    "points_for": _points(settings, "fpts"),
                    "points_against": _points(settings, "fpts_against"),
                }
            )
        rows.sort(key=lambda r: (r["wins"], r["points_for"]), reverse=True)
        return _dump(rows)

    def get_my_team(_: dict[str, Any]) -> str:
        names = _owner_names()
        roster = _my_roster()
        return _dump(_roster_view(roster, names.get(str(roster["roster_id"]), ctx.username)))

    def get_team(args: dict[str, Any]) -> str:
        target = str(args.get("team", "")).strip().lower()
        if not target:
            return _dump({"error": "provide a team owner name or roster_id"})
        names = _owner_names()
        for roster in ctx.client.get_rosters(ctx.league_id):
            rid = str(roster["roster_id"])
            owner = names.get(rid, rid)
            if target == rid or target in owner.lower():
                return _dump(_roster_view(roster, owner))
        return _dump({"error": f"no team matching '{args.get('team')}'", "teams": list(names.values())})

    def get_matchup(args: dict[str, Any]) -> str:
        week = int(args.get("week") or ctx.week)
        names = _owner_names()
        matchups = ctx.client.get_matchups(ctx.league_id, week)
        my_roster = _my_roster()
        my_rid = my_roster["roster_id"]
        my_entry = next((m for m in matchups if m["roster_id"] == my_rid), None)
        if not my_entry:
            return _dump({"error": f"no matchup found for week {week}"})
        matchup_id = my_entry.get("matchup_id")
        opponents = [
            m
            for m in matchups
            if m.get("matchup_id") == matchup_id and m["roster_id"] != my_rid
        ]

        def entry_view(m: dict[str, Any]) -> dict[str, Any]:
            rid = str(m["roster_id"])
            return {
                "owner": names.get(rid, rid),
                "points": m.get("points"),
                "starters": [
                    ctx.players.display_name(p)
                    for p in (m.get("starters") or [])
                    if p != "0"
                ],
            }

        return _dump(
            {
                "week": week,
                "you": entry_view(my_entry),
                "opponent": entry_view(opponents[0]) if opponents else None,
            }
        )

    def lookup_player(args: dict[str, Any]) -> str:
        name = str(args.get("name", "")).strip()
        if not name:
            return _dump({"error": "provide a player name"})
        return _dump(ctx.players.search(name, limit=int(args.get("limit") or 8)))

    def get_trending_players(args: dict[str, Any]) -> str:
        kind = args.get("kind", "add")
        limit = int(args.get("limit") or 15)
        try:
            trending = ctx.client.get_trending_players(kind, limit=limit)
        except SleeperError as exc:
            return _dump({"error": str(exc)})
        rostered = _rostered_player_ids()
        out = []
        for entry in trending:
            pid = entry.get("player_id")
            summary = ctx.players.summary(pid)
            summary["count"] = entry.get("count")
            summary["rostered_in_your_league"] = pid in rostered
            out.append(summary)
        return _dump({"kind": kind, "players": out})

    def _rostered_player_ids() -> set[str]:
        ids: set[str] = set()
        for roster in ctx.client.get_rosters(ctx.league_id):
            ids.update(roster.get("players") or [])
        return ids

    def get_free_agents(args: dict[str, Any]) -> str:
        position = args.get("position")
        position = str(position).upper() if position else None
        limit = int(args.get("limit") or 15)
        rostered = _rostered_player_ids()
        candidates: list[tuple[int, str]] = []
        for pid, info in ctx.players.players.items():
            if pid in rostered:
                continue
            if (info.get("status") or "Active") not in ("Active", None):
                continue
            if position and info.get("position") != position:
                continue
            rank = info.get("search_rank")
            if not isinstance(rank, int):
                continue  # skip the long tail with no relevance signal
            candidates.append((rank, pid))
        candidates.sort(key=lambda t: t[0])
        out = [ctx.players.summary(pid) for _, pid in candidates[:limit]]
        return _dump({"position": position, "free_agents": out})

    def get_transactions(args: dict[str, Any]) -> str:
        week = int(args.get("week") or ctx.week)
        names = _owner_names()
        try:
            txns = ctx.client.get_transactions(ctx.league_id, week)
        except SleeperError as exc:
            return _dump({"error": str(exc)})
        out = []
        for t in txns:
            if t.get("status") != "complete":
                continue
            adds = {
                ctx.players.display_name(pid): names.get(str(rid), str(rid))
                for pid, rid in (t.get("adds") or {}).items()
            }
            drops = {
                ctx.players.display_name(pid): names.get(str(rid), str(rid))
                for pid, rid in (t.get("drops") or {}).items()
            }
            out.append(
                {
                    "type": t.get("type"),
                    "adds": adds,
                    "drops": drops,
                }
            )
        return _dump({"week": week, "transactions": out})

    return [
        Tool(
            "get_nfl_state",
            "Get the current NFL season, season type, and week.",
            {"type": "object", "properties": {}},
            get_nfl_state,
        ),
        Tool(
            "get_league_info",
            "Get the configured league's name, size, scoring, and roster slots.",
            {"type": "object", "properties": {}},
            get_league_info,
        ),
        Tool(
            "get_standings",
            "Get every team's record and points for/against, sorted by wins.",
            {"type": "object", "properties": {}},
            get_standings,
        ),
        Tool(
            "get_my_team",
            "Get the user's own roster: starters, bench, IR, record, and points.",
            {"type": "object", "properties": {}},
            get_my_team,
        ),
        Tool(
            "get_team",
            "Get another team's roster by owner/team name or roster_id.",
            {
                "type": "object",
                "properties": {
                    "team": {
                        "type": "string",
                        "description": "Owner display name, team name, or roster_id.",
                    }
                },
                "required": ["team"],
            },
            get_team,
        ),
        Tool(
            "get_matchup",
            "Get the user's head-to-head matchup for a week (defaults to current).",
            {
                "type": "object",
                "properties": {
                    "week": {
                        "type": "integer",
                        "description": "NFL week number; omit for the current week.",
                    }
                },
            },
            get_matchup,
        ),
        Tool(
            "lookup_player",
            "Search players by (partial) name; returns ids, team, position, injury.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["name"],
            },
            lookup_player,
        ),
        Tool(
            "get_trending_players",
            "Get the most added or dropped players across Sleeper in the last 24h.",
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["add", "drop"]},
                    "limit": {"type": "integer"},
                },
            },
            get_trending_players,
        ),
        Tool(
            "get_free_agents",
            "List the most relevant unrostered players in the league, by position.",
            {
                "type": "object",
                "properties": {
                    "position": {
                        "type": "string",
                        "description": "QB, RB, WR, TE, K, DEF; omit for all.",
                    },
                    "limit": {"type": "integer"},
                },
            },
            get_free_agents,
        ),
        Tool(
            "get_transactions",
            "List completed adds/drops/trades for a week (defaults to current).",
            {
                "type": "object",
                "properties": {"week": {"type": "integer"}},
            },
            get_transactions,
        ),
    ]
