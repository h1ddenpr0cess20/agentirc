"""Built-in bot commands.

Each command is a plain async function with the signature:
    async def handler(bot: IRCBot, msg: IRCMessage, args: str) -> None

Call register_builtins(bot) to wire them up.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bot import IRCBot
    from .protocol import IRCMessage


async def cmd_ping(bot: IRCBot, msg: IRCMessage, _args: str) -> None:
    """Check if the bot is alive."""
    await bot.reply(msg, f"{msg.nick}: pong!")


async def cmd_time(bot: IRCBot, msg: IRCMessage, _args: str) -> None:
    """Show the current UTC time."""
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    await bot.reply(msg, f"UTC: {now}")


async def cmd_help(bot: IRCBot, msg: IRCMessage, args: str) -> None:
    """List available commands or show help for a specific command."""
    prefix = bot.config.command_prefix

    if args:
        cmd = bot.get_command(args.lower())
        if cmd:
            alias_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            await bot.reply(msg, f"{prefix}{cmd.name}{alias_str} -- {cmd.help or 'No description.'}")
        else:
            await bot.reply(msg, f"Unknown command: {args}")
        return

    names = sorted(bot.commands.keys())
    await bot.reply(msg, f"Commands: {', '.join(prefix + n for n in names)}")
    await bot.reply(msg, f"Use {prefix}help <command> for details.")


def register_builtins(bot: IRCBot) -> None:
    """Register all built-in commands on a bot instance."""
    bot.command("ping", help="Check if the bot is alive")(cmd_ping)
    bot.command("time", help="Show current UTC time")(cmd_time)
    bot.command("help", help="List commands or get help for one", aliases=["h"])(cmd_help)
