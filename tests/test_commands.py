"""Tests for ircbot.commands -- built-in !ping, !time, !help commands.

Coverage strategy:
- cmd_ping: responds with "nick: pong!" to the correct reply target
- cmd_time: responds with UTC timestamp in expected format
- cmd_help: lists all commands when no args, shows specific command help when
  given an arg, shows aliases, handles unknown command
- register_builtins: registers ping, time, help with correct metadata
"""

from __future__ import annotations

import asyncio
import re
import time
from unittest.mock import AsyncMock

from ircbot.bot import IRCBot
from ircbot.commands import cmd_ping, cmd_time, cmd_help, register_builtins
from ircbot.config import BotConfig
from ircbot.protocol import parse


def _config(**overrides) -> BotConfig:
    defaults = dict(
        host="irc.test", port=6667, nick="testbot", user="testbot",
        realname="Test Bot", channels=["#test"], password="",
        use_tls=False, command_prefix="!",
    )
    defaults.update(overrides)
    return BotConfig(**defaults)


def _bot(**overrides) -> IRCBot:
    bot = IRCBot(_config(**overrides))
    bot.conn.send = AsyncMock()
    return bot


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _sent_lines(bot: IRCBot) -> list[str]:
    return [c[0][0] for c in bot.conn.send.call_args_list]


# ── cmd_ping ─────────────────────────────────────────────────────────


class TestCmdPing:
    def test_responds_with_pong_in_channel(self):
        bot = _bot()
        msg = parse(":alice!u@h PRIVMSG #test :!ping")
        _run(cmd_ping(bot, msg, ""))
        lines = _sent_lines(bot)
        assert len(lines) == 1
        assert lines[0] == "PRIVMSG #test :alice: pong!"

    def test_responds_with_pong_in_dm(self):
        bot = _bot()
        msg = parse(":alice!u@h PRIVMSG testbot :!ping")
        _run(cmd_ping(bot, msg, ""))
        lines = _sent_lines(bot)
        assert len(lines) == 1
        assert lines[0] == "PRIVMSG alice :alice: pong!"

    def test_uses_sender_nick_in_response(self):
        bot = _bot()
        msg = parse(":bob!u@h PRIVMSG #test :!ping")
        _run(cmd_ping(bot, msg, ""))
        assert "bob: pong!" in _sent_lines(bot)[0]


# ── cmd_time ─────────────────────────────────────────────────────────


class TestCmdTime:
    def test_responds_with_utc_timestamp(self):
        bot = _bot()
        msg = parse(":alice!u@h PRIVMSG #test :!time")
        _run(cmd_time(bot, msg, ""))
        lines = _sent_lines(bot)
        assert len(lines) == 1
        # Should match pattern like "UTC: 2026-03-09 12:34:56"
        assert lines[0].startswith("PRIVMSG #test :UTC: ")
        timestamp = lines[0].split("UTC: ", 1)[1]
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", timestamp)

    def test_timestamp_is_current_utc(self):
        bot = _bot()
        msg = parse(":alice!u@h PRIVMSG #test :!time")
        before = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
        _run(cmd_time(bot, msg, ""))
        after = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
        timestamp = _sent_lines(bot)[0].split("UTC: ", 1)[1]
        # The minute should match either before or after (handles minute boundary)
        ts_minute = timestamp[:16]
        assert ts_minute in (before, after)


# ── cmd_help ─────────────────────────────────────────────────────────


class TestCmdHelp:
    def _bot_with_builtins(self) -> IRCBot:
        bot = _bot()
        register_builtins(bot)
        return bot

    def test_list_all_commands(self):
        bot = self._bot_with_builtins()
        msg = parse(":alice!u@h PRIVMSG #test :!help")
        _run(cmd_help(bot, msg, ""))
        lines = _sent_lines(bot)
        # First line lists commands, second line says "Use !help <command>"
        assert len(lines) == 2
        assert "!ping" in lines[0]
        assert "!time" in lines[0]
        assert "!help" in lines[0]
        assert "Use !help" in lines[1]

    def test_help_for_specific_command(self):
        bot = self._bot_with_builtins()
        msg = parse(":alice!u@h PRIVMSG #test :!help ping")
        _run(cmd_help(bot, msg, "ping"))
        lines = _sent_lines(bot)
        assert len(lines) == 1
        assert "!ping" in lines[0]
        assert "alive" in lines[0].lower()

    def test_help_for_command_with_aliases(self):
        bot = self._bot_with_builtins()
        msg = parse(":alice!u@h PRIVMSG #test :!help help")
        _run(cmd_help(bot, msg, "help"))
        lines = _sent_lines(bot)
        assert len(lines) == 1
        assert "aliases: h" in lines[0]

    def test_help_for_unknown_command(self):
        bot = self._bot_with_builtins()
        msg = parse(":alice!u@h PRIVMSG #test :!help nonexistent")
        _run(cmd_help(bot, msg, "nonexistent"))
        lines = _sent_lines(bot)
        assert len(lines) == 1
        assert "Unknown command" in lines[0]
        assert "nonexistent" in lines[0]

    def test_help_via_alias(self):
        bot = self._bot_with_builtins()
        msg = parse(":alice!u@h PRIVMSG #test :!help h")
        _run(cmd_help(bot, msg, "h"))
        lines = _sent_lines(bot)
        assert len(lines) == 1
        # Should resolve the alias and show the help command's info
        assert "!help" in lines[0]

    def test_help_uses_configured_prefix(self):
        bot = _bot(command_prefix=".")
        register_builtins(bot)
        msg = parse(":alice!u@h PRIVMSG #test :.help")
        _run(cmd_help(bot, msg, ""))
        lines = _sent_lines(bot)
        assert ".ping" in lines[0]
        assert ".help" in lines[0]

    def test_help_no_description_fallback(self):
        bot = _bot()

        @bot.command("bare")
        async def bare(b, m, a):
            pass

        msg = parse(":alice!u@h PRIVMSG #test :!help bare")
        _run(cmd_help(bot, msg, "bare"))
        lines = _sent_lines(bot)
        assert "No description." in lines[0]


# ── register_builtins ────────────────────────────────────────────────


class TestRegisterBuiltins:
    def test_registers_all_three_commands(self):
        bot = _bot()
        register_builtins(bot)
        assert bot.get_command("ping") is not None
        assert bot.get_command("time") is not None
        assert bot.get_command("help") is not None

    def test_help_has_alias_h(self):
        bot = _bot()
        register_builtins(bot)
        cmd = bot.get_command("h")
        assert cmd is not None
        assert cmd.name == "help"

    def test_ping_has_correct_help_text(self):
        bot = _bot()
        register_builtins(bot)
        cmd = bot.get_command("ping")
        assert "alive" in cmd.help.lower()

    def test_handlers_are_callable(self):
        bot = _bot()
        register_builtins(bot)
        for name in ("ping", "time", "help"):
            cmd = bot.get_command(name)
            assert callable(cmd.handler)
