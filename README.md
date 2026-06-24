# Fantasy Football Assistant Manager

A Claude-powered assistant manager for your [Sleeper](https://sleeper.com)
fantasy football team. Ask it natural-language questions about your league and
it pulls live data from Sleeper's public API to answer: lineup calls, waiver
and free-agent targets, trade reads, matchup analysis, and standings. Before it
commits to a time-sensitive call it cross-checks the pick against current news
(injuries, role changes, breaking developments).

It is **read-only** — it never makes a move in your league. It reads your
roster and the league around it, then gives you a recommendation.

## How it works

The agent is a manual tool-use loop over Claude (`claude-opus-4-8` by default).
Claude is given a set of read-only tools backed by
[Sleeper's HTTP API](https://docs.sleeper.com/); it decides which to call to
answer your question.

```
your question ─▶ Claude ─▶ picks tools ─▶ Sleeper API ─▶ data ─▶ Claude ─▶ answer
```

Available tools: current NFL week, league info, standings, your roster, any
other team's roster, your weekly matchup, player search, leaguewide trending
adds/drops, position-filtered free agents, and recent transactions.

> Note: Sleeper's API does not expose point projections, so the agent reasons
> from roster construction, player roles, injury status, recent trends, and
> matchups rather than projected points.

### Verifying picks

Sleeper's roster data can lag real life, so the agent has a news layer it uses
to sanity-check time-sensitive decisions before recommending them:

- **`get_injuries`** — the current [ESPN](https://www.espn.com) NFL injury
  report (designation, body part, return notes), optionally filtered to one
  team. Free, no API key.
- **`get_player_news`** — recent ESPN headlines for a named player (role
  changes, suspensions, breaking developments). Free, no API key.
- **`web_search`** — Anthropic's native web search, for anything that may have
  changed in the last day (late injury news, depth-chart shuffles, weather),
  with citations. On by default; bills per search on top of token usage.
  Disable with `FANTASY_ASSISTANT_WEB_SEARCH=0`.

## Setup

```bash
pip install -e .            # or: pip install -e ".[dev]" for tests
cp .env.example .env        # then edit .env
```

Set at least `ANTHROPIC_API_KEY` and `SLEEPER_USERNAME` in `.env` (or as
environment variables). If you have more than one league, set
`SLEEPER_LEAGUE_ID` — find it with `fantasy-assistant leagues`.

## Usage

```bash
# List your leagues (to grab a league id)
fantasy-assistant leagues

# One-off question
fantasy-assistant ask "Who should I start at flex this week?"

# Interactive chat (keeps context across questions)
fantasy-assistant chat
```

Example questions:

- "Set my optimal lineup for this week and explain the close calls."
- "Is anyone in my lineup banged up this week?"
- "Are there any free-agent running backs worth picking up?"
- "Who's trending on waivers that I don't already roster?"
- "Break down my matchup this week — where do I have an edge?"
- "Should I worry about my bench depth at receiver?"

Tool calls are printed to stderr as the agent works, so you can see what it
looked at.

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | yes | Anthropic API key |
| `SLEEPER_USERNAME` | yes | Your Sleeper username |
| `SLEEPER_LEAGUE_ID` | no | Pin a league (auto-detected if you have one) |
| `SLEEPER_SEASON` | no | Defaults to the current NFL season |
| `FANTASY_ASSISTANT_MODEL` | no | Defaults to `claude-opus-4-8` |
| `FANTASY_ASSISTANT_EFFORT` | no | Reasoning effort: `low`/`medium`/`high` (default `high`) |
| `FANTASY_ASSISTANT_WEB_SEARCH` | no | Live web search for breaking news (default `on`; set `0` to use ESPN only) |

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests mock the network, so they run without Sleeper or Anthropic access.

The full ~5 MB Sleeper player map is cached to
`~/.cache/fantasy-assistant/players_nfl.json` and refreshed once a day.
