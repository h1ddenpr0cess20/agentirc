"""Configuration loading from environment variables and .env files.

Provides a typed dataclass instead of a raw dict.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_env(path: str = ".env") -> None:
    """Load key=value pairs from a .env file into os.environ.

    Uses setdefault so real environment variables always win.
    Skips blank lines and comments (#).
    Handles quoted values (single or double quotes).
    """
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True, slots=True)
class BotConfig:
    """Typed, immutable bot configuration."""

    host: str
    port: int
    nick: str
    user: str
    realname: str
    channels: list[str] = field(default_factory=list)
    password: str = ""
    use_tls: bool = False
    command_prefix: str = "!"

    @classmethod
    def from_env(cls) -> BotConfig:
        """Build config from environment variables (IRC_HOST, IRC_PORT, etc.)."""
        nick = os.environ["IRC_NICK"]
        channels_raw = os.environ.get("IRC_CHANNELS", "")
        return cls(
            host=os.environ["IRC_HOST"],
            port=int(os.environ.get("IRC_PORT", "6667")),
            nick=nick,
            user=os.environ.get("IRC_USER", nick),
            realname=os.environ.get("IRC_REALNAME", "IRC Bot"),
            channels=[c.strip() for c in channels_raw.split(",") if c.strip()],
            password=os.environ.get("IRC_PASSWORD", ""),
            use_tls=os.environ.get("IRC_USE_TLS", "false").lower() in ("1", "true", "yes"),
            command_prefix=os.environ.get("IRC_CMD_PREFIX", "!"),
        )
