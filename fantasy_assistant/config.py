"""Runtime configuration for the assistant manager agent.

Configuration is read from environment variables (optionally seeded from a
local ``.env`` file). Nothing here is secret except ``ANTHROPIC_API_KEY``; the
Sleeper identifiers are public.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Default model for the agent. Per Anthropic guidance this is the most capable
# generally-available model; override with FANTASY_ASSISTANT_MODEL if desired.
DEFAULT_MODEL = "claude-opus-4-8"


def _env_bool(key: str, default: bool) -> bool:
    """Parse a boolean environment variable. Unset returns ``default``."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _load_dotenv() -> None:
    """Best-effort load of a local .env file without a hard dependency.

    If python-dotenv is installed we use it; otherwise we parse a minimal
    KEY=value file ourselves. Existing environment variables always win.
    """
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    try:  # pragma: no cover - exercised indirectly
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Config:
    """Resolved configuration for a single agent run."""

    anthropic_api_key: str | None
    sleeper_username: str | None
    league_id: str | None
    season: str | None
    model: str
    effort: str
    web_search: bool

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv()
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            sleeper_username=os.environ.get("SLEEPER_USERNAME"),
            league_id=os.environ.get("SLEEPER_LEAGUE_ID"),
            season=os.environ.get("SLEEPER_SEASON"),
            model=os.environ.get("FANTASY_ASSISTANT_MODEL", DEFAULT_MODEL),
            effort=os.environ.get("FANTASY_ASSISTANT_EFFORT", "high"),
            web_search=_env_bool("FANTASY_ASSISTANT_WEB_SEARCH", True),
        )
