"""Core IRC bot with event dispatch and command registry.

This is the central piece: it ties the connection, protocol parser,
and command system together. Subclass it or register commands on an
instance -- both patterns work.
"""

from __future__ import annotations

import asyncio
import logging
import textwrap
from dataclasses import dataclass
from typing import Callable, Awaitable

from . import protocol
from .config import BotConfig
from .connection import IRCConnection

log = logging.getLogger(__name__)


# -- Command handler types --

@dataclass(slots=True)
class Command:
    """A registered bot command."""

    name: str
    handler: Callable[[IRCBot, protocol.IRCMessage, str], Awaitable[None]]
    help: str
    aliases: list[str]


# The handler signature:  async def handler(bot, message, args_str) -> None

class IRCBot:
    """Async IRC bot with a command registry and overridable event hooks.

    Usage::

        bot = IRCBot(config)
        bot.command("ping", help="Check if the bot is alive")(ping_handler)
        await bot.run()
    """

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.nick = config.nick  # mutable -- may change on collision
        self.conn = IRCConnection(
            host=config.host,
            port=config.port,
            use_tls=config.use_tls,
        )
        self._commands: dict[str, Command] = {}
        self._alias_map: dict[str, str] = {}  # alias -> canonical name

    # -- Command registration --

    def command(
        self,
        name: str,
        *,
        help: str = "",
        aliases: list[str] | None = None,
    ) -> Callable:
        """Decorator to register a command.

        The decorated function must have the signature::

            async def handler(bot: IRCBot, msg: IRCMessage, args: str) -> None

        ``args`` is the text after the command name, stripped.

        Example::

            @bot.command("greet", help="Say hello", aliases=["hi"])
            async def greet(bot, msg, args):
                await bot.reply(msg, f"Hello, {msg.nick}!")
        """
        aliases = aliases or []

        def decorator(fn: Callable) -> Callable:
            cmd = Command(name=name, handler=fn, help=help, aliases=aliases)
            self._commands[name] = cmd
            for alias in aliases:
                self._alias_map[alias] = name
            return fn

        return decorator

    def get_command(self, name: str) -> Command | None:
        """Look up a command by name or alias."""
        if name in self._commands:
            return self._commands[name]
        canonical = self._alias_map.get(name)
        if canonical:
            return self._commands.get(canonical)
        return None

    @property
    def commands(self) -> dict[str, Command]:
        """All registered commands (canonical names only)."""
        return dict(self._commands)

    # -- Convenience send helpers --

    async def send(self, line: str) -> None:
        """Send a raw IRC line."""
        await self.conn.send(line)

    @staticmethod
    def _chop(text: str, width: int = 420) -> list[str]:
        """Wrap text into lines under width, preserving word boundaries."""
        result: list[str] = []
        for line in text.splitlines():
            if len(line) > width:
                result.extend(textwrap.wrap(
                    line,
                    width=width,
                    drop_whitespace=False,
                    replace_whitespace=False,
                    fix_sentence_endings=True,
                    break_long_words=False,
                ))
            else:
                result.append(line)
        return result

    async def privmsg(self, target: str, text: str) -> None:
        """Send a PRIVMSG, chopping long lines at word boundaries."""
        lines = self._chop(text)
        for i, line in enumerate(lines):
            await self.send(f"PRIVMSG {target} :{line}")
            if i < len(lines) - 1:
                await asyncio.sleep(1)

    async def notice(self, target: str, text: str) -> None:
        """Send a NOTICE, chopping long lines at word boundaries."""
        lines = self._chop(text)
        for i, line in enumerate(lines):
            await self.send(f"NOTICE {target} :{line}")
            if i < len(lines) - 1:
                await asyncio.sleep(1)

    async def reply(self, msg: protocol.IRCMessage, text: str) -> None:
        """Reply in the appropriate context (channel or DM)."""
        await self.privmsg(msg.reply_target, text)

    async def join(self, channel: str) -> None:
        await self.send(f"JOIN {channel}")

    async def part(self, channel: str, reason: str = "Leaving") -> None:
        await self.send(f"PART {channel} :{reason}")

    async def quit(self, reason: str = "Bye") -> None:
        await self.send(f"QUIT :{reason}")

    # -- Connection lifecycle --

    async def run(self) -> None:
        """Start the bot (blocks until cancelled)."""
        log.info("Starting bot as %s", self.config.nick)
        await self.conn.run_forever(
            on_connect=self._on_connect,
            on_line=self._on_line,
        )

    async def _on_connect(self) -> None:
        """Send registration commands after TCP connect."""
        if self.config.password:
            await self.send(f"PASS {self.config.password}")

        self.nick = self.config.nick  # reset nick on reconnect
        await self.send(f"NICK {self.nick}")
        await self.send(f"USER {self.config.user} 0 * :{self.config.realname}")

    # -- IRC line dispatch --

    async def _on_line(self, raw: str) -> None:
        """Parse and dispatch a single IRC line."""
        msg = protocol.parse(raw)
        await self._dispatch(msg)

    async def _dispatch(self, msg: protocol.IRCMessage) -> None:
        """Route a parsed message to the appropriate handler."""

        if msg.command == "PING":
            await self.send(f"PONG :{msg.text}")

        elif msg.command == "001":  # RPL_WELCOME
            await self.on_welcome(msg)

        elif msg.command == "PRIVMSG":
            await self.on_privmsg(msg)

        elif msg.command == "JOIN":
            await self.on_join(msg)

        elif msg.command == "PART":
            await self.on_part(msg)

        elif msg.command == "KICK":
            await self.on_kick(msg)

        elif msg.command in ("433", "432"):
            # Nick in use or erroneous -- try with underscore suffix
            self.nick += "_"
            await self.send(f"NICK {self.nick}")
            log.warning("Nick collision, trying %s", self.nick)

        # Let subclasses handle arbitrary commands
        handler = getattr(self, f"on_raw_{msg.command.lower()}", None)
        if handler is not None:
            await handler(msg)

    # -- Event hooks (override in subclasses) --

    async def on_welcome(self, msg: protocol.IRCMessage) -> None:
        """Called after successful registration (numeric 001)."""
        log.info("Registered as %s", self.nick)
        for channel in self.config.channels:
            await self.join(channel)

    async def on_privmsg(self, msg: protocol.IRCMessage) -> None:
        """Called on every PRIVMSG. Dispatches commands automatically."""
        await self._try_command(msg)

    async def on_join(self, msg: protocol.IRCMessage) -> None:
        """Called when someone (including the bot) joins a channel."""
        log.debug("%s joined %s", msg.nick, msg.target)

    async def on_part(self, msg: protocol.IRCMessage) -> None:
        """Called when someone parts a channel."""
        reason = msg.text if len(msg.params) > 1 else ""
        log.debug("%s left %s (%s)", msg.nick, msg.target, reason)

    async def on_kick(self, msg: protocol.IRCMessage) -> None:
        """Called when someone is kicked. Auto-rejoins if it is the bot."""
        kicked = msg.params[1] if len(msg.params) > 1 else ""
        reason = msg.text if len(msg.params) > 2 else ""
        log.debug("%s kicked from %s (%s)", kicked, msg.target, reason)
        if kicked == self.nick:
            await asyncio.sleep(5)
            await self.join(msg.target)

    # -- Command dispatch --

    async def _try_command(self, msg: protocol.IRCMessage) -> None:
        """Check if a PRIVMSG is a bot command and dispatch it."""
        text = msg.text.strip()
        prefix = self.config.command_prefix

        if not text.startswith(prefix):
            return

        # Split "!ping some args" -> ("ping", "some args")
        without_prefix = text[len(prefix):]
        parts = without_prefix.split(None, 1)
        if not parts:
            return

        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        cmd = self.get_command(cmd_name)
        if cmd is None:
            return

        if args:
            log.info("command [%s] <%s> %s %s", msg.reply_target, msg.nick, cmd.name, args)
        else:
            log.info("command [%s] <%s> %s", msg.reply_target, msg.nick, cmd.name)

        try:
            await cmd.handler(self, msg, args)
        except Exception:
            log.exception("Error in command '%s'", cmd_name)
            await self.reply(msg, f"Error running command '{cmd_name}'.")
