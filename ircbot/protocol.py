"""IRC protocol message parsing.

Stateless functions that turn raw IRC lines into structured data.
Follows RFC 2812 message format: [:prefix] command params... [:trailing]
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IRCMessage:
    """A parsed IRC protocol message."""

    raw: str
    prefix: str
    nick: str
    user: str
    host: str
    command: str
    params: list[str]

    @property
    def target(self) -> str:
        """First param -- typically a channel or nick."""
        return self.params[0] if self.params else ""

    @property
    def text(self) -> str:
        """Trailing param (the human-readable body of PRIVMSG, NOTICE, etc.)."""
        return self.params[-1] if self.params else ""

    @property
    def is_channel(self) -> bool:
        """Whether the target is a channel (starts with # or &)."""
        return bool(self.target) and self.target[0] in "#&!+"

    @property
    def reply_target(self) -> str:
        """Where to send a reply: the channel if public, the sender's nick if private."""
        return self.target if self.is_channel else self.nick


def parse_prefix(prefix: str) -> tuple[str, str, str]:
    """Split a prefix into (nick, user, host).

    Handles both 'nick!user@host' and plain server names.
    """
    nick = prefix
    user = ""
    host = ""

    if "!" in prefix:
        nick, _, rest = prefix.partition("!")
        user, _, host = rest.partition("@")
    elif "@" in prefix:
        nick, _, host = prefix.partition("@")

    return nick, user, host


def parse(line: str) -> IRCMessage:
    """Parse a raw IRC line into an IRCMessage.

    Handles the full RFC 2812 format:
        [:prefix SPACE] command [params] [:trailing]
    """
    raw = line
    prefix = ""
    remaining = line

    # Extract prefix
    if remaining.startswith(":"):
        prefix, _, remaining = remaining[1:].partition(" ")

    # Extract command
    if " " in remaining:
        command, _, remaining = remaining.partition(" ")
    else:
        command = remaining
        remaining = ""

    command = command.upper()

    # Extract params
    params: list[str] = []
    while remaining:
        if remaining.startswith(":"):
            params.append(remaining[1:])
            break
        if " " in remaining:
            param, _, remaining = remaining.partition(" ")
            params.append(param)
        else:
            params.append(remaining)
            break

    nick, user, host = parse_prefix(prefix)

    return IRCMessage(
        raw=raw,
        prefix=prefix,
        nick=nick,
        user=user,
        host=host,
        command=command,
        params=params,
    )
