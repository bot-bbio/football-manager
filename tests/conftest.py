"""Shared fixtures: a small fake league and a player map for tests."""

from __future__ import annotations

import pytest

from fantasy_assistant.players import PlayerData


PLAYERS = {
    "100": {
        "full_name": "Josh Allen",
        "first_name": "Josh",
        "last_name": "Allen",
        "position": "QB",
        "team": "BUF",
        "status": "Active",
        "search_rank": 5,
    },
    "200": {
        "full_name": "Bijan Robinson",
        "first_name": "Bijan",
        "last_name": "Robinson",
        "position": "RB",
        "team": "ATL",
        "status": "Active",
        "search_rank": 3,
    },
    "300": {
        "full_name": "Some Backup",
        "first_name": "Some",
        "last_name": "Backup",
        "position": "RB",
        "team": "NYJ",
        "status": "Active",
        "injury_status": "Questionable",
        "search_rank": 250,
    },
    "400": {
        "full_name": "Deep Sleeper",
        "first_name": "Deep",
        "last_name": "Sleeper",
        "position": "WR",
        "team": None,
        "status": "Active",
        "search_rank": None,  # long tail; should be skipped by free-agent ranking
    },
    "BUF": {
        "first_name": "Buffalo",
        "last_name": "Bills",
        "position": "DEF",
        "team": "BUF",
        "status": "Active",
        "search_rank": 80,
    },
}


@pytest.fixture
def player_data() -> PlayerData:
    return PlayerData(PLAYERS)


class FakeSleeperClient:
    """A stand-in for SleeperClient returning canned league data."""

    def __init__(self) -> None:
        self.closed = False

    def get_nfl_state(self):
        return {"season": "2025", "season_type": "regular", "week": 4, "display_week": 4}

    def get_user(self, username_or_id):
        return {"user_id": "user_me", "username": username_or_id}

    def get_user_leagues(self, user_id, season):
        return [{"league_id": "league_1", "name": "Test League"}]

    def get_league(self, league_id):
        return {
            "name": "Test League",
            "season": "2025",
            "total_rosters": 2,
            "settings": {"num_teams": 2, "playoff_week_start": 15},
            "scoring_settings": {"rec": 1.0},
            "roster_positions": ["QB", "RB", "WR", "FLEX", "DEF"],
            "status": "in_season",
        }

    def get_league_users(self, league_id):
        return [
            {"user_id": "user_me", "display_name": "Me", "metadata": {"team_name": "My Squad"}},
            {"user_id": "user_rival", "display_name": "Rival", "metadata": {}},
        ]

    def get_rosters(self, league_id):
        return [
            {
                "roster_id": 1,
                "owner_id": "user_me",
                "players": ["100", "200", "300", "BUF"],
                "starters": ["100", "200", "BUF"],
                "reserve": [],
                "settings": {
                    "wins": 3,
                    "losses": 1,
                    "ties": 0,
                    "fpts": 420,
                    "fpts_decimal": 50,
                    "fpts_against": 380,
                    "fpts_against_decimal": 0,
                },
            },
            {
                "roster_id": 2,
                "owner_id": "user_rival",
                "players": ["400"],
                "starters": ["400"],
                "reserve": [],
                "settings": {
                    "wins": 1,
                    "losses": 3,
                    "ties": 0,
                    "fpts": 360,
                    "fpts_decimal": 0,
                    "fpts_against": 400,
                    "fpts_against_decimal": 0,
                },
            },
        ]

    def get_matchups(self, league_id, week):
        return [
            {"roster_id": 1, "matchup_id": 1, "points": 110.5, "starters": ["100", "200", "BUF"]},
            {"roster_id": 2, "matchup_id": 1, "points": 95.0, "starters": ["400"]},
        ]

    def get_transactions(self, league_id, week):
        return [
            {
                "type": "waiver",
                "status": "complete",
                "adds": {"300": 1},
                "drops": {"400": 2},
            },
            {"type": "free_agent", "status": "failed", "adds": {"100": 1}, "drops": {}},
        ]

    def get_trending_players(self, kind="add", *, lookback_hours=24, limit=25):
        return [{"player_id": "300", "count": 5000}, {"player_id": "400", "count": 1200}]


@pytest.fixture
def fake_client() -> FakeSleeperClient:
    return FakeSleeperClient()


# Trimmed but structurally-faithful copies of real ESPN payloads.
ESPN_NEWS = {
    "articles": [
        {
            "headline": "Bijan Robinson dominates in Falcons win",
            "description": "Bijan Robinson rushed for 120 yards and two scores.",
            "published": "2025-09-20T22:31:39Z",
            "links": {"web": {"href": "https://www.espn.com/nfl/story/bijan"}},
            "categories": [
                {"type": "league", "description": "NFL"},
                {"type": "athlete", "description": "Bijan Robinson", "athleteId": 4430807},
            ],
        },
        {
            "headline": "Bills roll on the road",
            "description": "Buffalo's quarterback threw for 300 yards.",
            "published": "2025-09-20T20:00:00Z",
            "links": {"web": {"href": "https://www.espn.com/nfl/story/bills"}},
            "categories": [
                {"type": "athlete", "description": "Josh Allen", "athleteId": 3918298},
            ],
        },
    ]
}

ESPN_INJURIES = {
    "injuries": [
        {
            "id": "1",
            "displayName": "New York Jets",
            "injuries": [
                {
                    "status": "Questionable",
                    "date": "2025-09-19T00:04Z",
                    "shortComment": "Some Backup is nursing a hamstring.",
                    "athlete": {
                        "displayName": "Some Backup",
                        "position": {"abbreviation": "RB"},
                        "team": {"abbreviation": "NYJ", "displayName": "New York Jets"},
                    },
                    "details": {
                        "fantasyStatus": {"description": "Game-Time Decision"},
                        "type": "Hamstring",
                        "detail": "Hamstring",
                        "returnDate": "2025-09-22",
                    },
                }
            ],
        },
        {
            "id": "2",
            "displayName": "Buffalo Bills",
            "injuries": [
                {
                    "status": "Active",
                    "date": "2025-09-18T00:00Z",
                    "shortComment": "Josh Allen is good to go.",
                    "athlete": {
                        "displayName": "Josh Allen",
                        "position": {"abbreviation": "QB"},
                        "team": {"abbreviation": "BUF", "displayName": "Buffalo Bills"},
                    },
                    "details": {"type": "Not Injury Related", "detail": ""},
                }
            ],
        },
    ]
}


class FakeESPNClient:
    """A stand-in for ESPNClient returning canned news and injury data."""

    def get_news(self, limit=50):
        return ESPN_NEWS

    def get_injuries(self):
        return ESPN_INJURIES


@pytest.fixture
def fake_news() -> FakeESPNClient:
    return FakeESPNClient()
