"""Tests for ircbot.bot -- IRCBot command registry, dispatch, and event hooks.

Coverage strategy:
- Command registration: register by decorator, lookup by name, lookup by alias,
  unknown command returns None, commands dict excludes aliases
- Command dispatch (_try_command): prefix matching, arg splitting, no-prefix ignored,
  prefix-only ignored, alias dispatch, error handling in command handler
- Event dispatch (_dispatch): PING -> PONG, 001 -> join channels, PRIVMSG routing,
  nick collision (433/432) appends underscore, KICK auto-rejoin when bot is kicked,
  KICK ignored when someone else is kicked
- Connection lifecycle (_on_connect): sends NICK/USER, sends PASS if configured,
  resets nick on reconnect
- Send helpers: privmsg splits newlines, reply routes to channel vs DM
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, call

from ircbot.bot import IRCBot, Command
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
    # Replace the connection's send method so nothing touches real sockets
    bot.conn.send = AsyncMock()
    return bot


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Command registration ────────────────────────────────────────────


class TestCommandRegistration:
    def test_register_and_lookup_by_name(self):
        bot = _bot()

        @bot.command("greet", help="Say hi")
        async def greet(b, msg, args):
            pass

        cmd = bot.get_command("greet")
        assert cmd is not None
        assert cmd.name == "greet"
        assert cmd.help == "Say hi"
        assert cmd.handler is greet

    def test_lookup_by_alias(self):
        bot = _bot()

        @bot.command("greet", aliases=["hi", "hello"])
        async def greet(b, msg, args):
            pass

        assert bot.get_command("hi") is not None
        assert bot.get_command("hi").name == "greet"
        assert bot.get_command("hello").name == "greet"

    def test_unknown_command_returns_none(self):
        bot = _bot()
        assert bot.get_command("nonexistent") is None

    def test_commands_dict_contains_only_canonical_names(self):
        bot = _bot()

        @bot.command("greet", aliases=["hi"])
        async def greet(b, msg, args):
            pass

        cmds = bot.commands
        assert "greet" in cmds
        assert "hi" not in cmds

    def test_commands_dict_is_a_copy(self):
        bot = _bot()

        @bot.command("test")
        async def handler(b, msg, args):
            pass

        cmds = bot.commands
        cmds["injected"] = None
        assert bot.get_command("injected") is None

    def test_decorator_returns_original_function(self):
        bot = _bot()

        async def original(b, msg, args):
            pass

        result = bot.command("test")(original)
        assert result is original

    def test_multiple_commands_registered(self):
        bot = _bot()

        @bot.command("a")
        async def cmd_a(b, msg, args):
            pass

        @bot.command("b")
        async def cmd_b(b, msg, args):
            pass

        assert bot.get_command("a").handler is cmd_a
        assert bot.get_command("b").handler is cmd_b


# ── Command dispatch (_try_command) ──────────────────────────────────


class TestCommandDispatch:
    def test_dispatches_command_with_args(self):
        bot = _bot()
        received = {}

        @bot.command("echo")
        async def echo(b, msg, args):
            received["args"] = args
            received["nick"] = msg.nick

        msg = parse(":alice!u@h PRIVMSG #test :!echo hello world")
        _run(bot._try_command(msg))
        assert received["args"] == "hello world"
        assert received["nick"] == "alice"

    def test_dispatches_command_without_args(self):
        bot = _bot()
        called = []

        @bot.command("ping")
        async def ping(b, msg, args):
            called.append(args)

        msg = parse(":alice!u@h PRIVMSG #test :!ping")
        _run(bot._try_command(msg))
        assert called == [""]

    def test_ignores_message_without_prefix(self):
        bot = _bot()
        called = []

        @bot.command("ping")
        async def ping(b, msg, args):
            called.append(True)

        msg = parse(":alice!u@h PRIVMSG #test :just a normal message")
        _run(bot._try_command(msg))
        assert called == []

    def test_ignores_prefix_only(self):
        bot = _bot()
        called = []

        @bot.command("ping")
        async def ping(b, msg, args):
            called.append(True)

        msg = parse(":alice!u@h PRIVMSG #test :!")
        _run(bot._try_command(msg))
        assert called == []

    def test_dispatches_via_alias(self):
        bot = _bot()
        called = []

        @bot.command("greet", aliases=["hi"])
        async def greet(b, msg, args):
            called.append(True)

        msg = parse(":alice!u@h PRIVMSG #test :!hi")
        _run(bot._try_command(msg))
        assert called == [True]

    def test_command_name_is_case_insensitive(self):
        bot = _bot()
        called = []

        @bot.command("ping")
        async def ping(b, msg, args):
            called.append(True)

        msg = parse(":alice!u@h PRIVMSG #test :!PING")
        _run(bot._try_command(msg))
        assert called == [True]

    def test_unknown_command_silently_ignored(self):
        bot = _bot()
        msg = parse(":alice!u@h PRIVMSG #test :!nonexistent")
        # Should not raise
        _run(bot._try_command(msg))

    def test_custom_prefix(self):
        bot = _bot(command_prefix=".")
        called = []

        @bot.command("ping")
        async def ping(b, msg, args):
            called.append(True)

        msg = parse(":alice!u@h PRIVMSG #test :.ping")
        _run(bot._try_command(msg))
        assert called == [True]

    def test_handler_exception_sends_error_reply(self):
        bot = _bot()

        @bot.command("fail")
        async def fail(b, msg, args):
            raise ValueError("boom")

        msg = parse(":alice!u@h PRIVMSG #test :!fail")
        _run(bot._try_command(msg))

        # Should have sent an error message back
        bot.conn.send.assert_called()
        sent_line = bot.conn.send.call_args[0][0]
        assert "Error running command" in sent_line
        assert "fail" in sent_line


# ── Event dispatch (_dispatch) ───────────────────────────────────────


class TestEventDispatch:
    def test_ping_responds_with_pong(self):
        bot = _bot()
        msg = parse("PING :irc.server.com")
        _run(bot._dispatch(msg))
        bot.conn.send.assert_called_once_with("PONG :irc.server.com")

    def test_welcome_001_joins_configured_channels(self):
        bot = _bot(channels=["#foo", "#bar"])
        msg = parse(":server 001 testbot :Welcome")
        _run(bot._dispatch(msg))
        calls = bot.conn.send.call_args_list
        sent = [c[0][0] for c in calls]
        assert "JOIN #foo" in sent
        assert "JOIN #bar" in sent

    def test_welcome_with_no_channels(self):
        bot = _bot(channels=[])
        msg = parse(":server 001 testbot :Welcome")
        _run(bot._dispatch(msg))
        # Should not attempt any JOINs
        for c in bot.conn.send.call_args_list:
            assert not c[0][0].startswith("JOIN")

    def test_nick_collision_433_appends_underscore(self):
        bot = _bot(nick="mybot")
        assert bot.nick == "mybot"
        msg = parse(":server 433 * mybot :Nickname is already in use")
        _run(bot._dispatch(msg))
        assert bot.nick == "mybot_"
        bot.conn.send.assert_called_with("NICK mybot_")

    def test_nick_collision_432_appends_underscore(self):
        bot = _bot(nick="mybot")
        msg = parse(":server 432 * mybot :Erroneous nickname")
        _run(bot._dispatch(msg))
        assert bot.nick == "mybot_"

    def test_repeated_nick_collisions_accumulate_underscores(self):
        bot = _bot(nick="mybot")
        msg433 = parse(":server 433 * mybot :Nickname is already in use")
        _run(bot._dispatch(msg433))
        assert bot.nick == "mybot_"
        msg433_2 = parse(":server 433 * mybot_ :Nickname is already in use")
        _run(bot._dispatch(msg433_2))
        assert bot.nick == "mybot__"

    def test_privmsg_dispatches_command(self):
        bot = _bot()
        called = []

        @bot.command("ping")
        async def ping(b, msg, args):
            called.append(True)

        msg = parse(":alice!u@h PRIVMSG #test :!ping")
        _run(bot._dispatch(msg))
        assert called == [True]

    def test_kick_auto_rejoin_when_bot_kicked(self):
        bot = _bot(nick="testbot")
        msg = parse(":op!u@h KICK #test testbot :Bye")
        with patch("asyncio.sleep", new_callable=AsyncMock):
            _run(bot._dispatch(msg))
        calls = bot.conn.send.call_args_list
        sent = [c[0][0] for c in calls]
        assert "JOIN #test" in sent

    def test_kick_no_rejoin_when_other_user_kicked(self):
        bot = _bot(nick="testbot")
        msg = parse(":op!u@h KICK #test otheruser :Bye")
        _run(bot._dispatch(msg))
        calls = bot.conn.send.call_args_list
        sent = [c[0][0] for c in calls]
        assert "JOIN #test" not in sent

    def test_raw_handler_called_if_present(self):
        bot = _bot()
        captured = []

        async def on_raw_notice(msg):
            captured.append(msg.text)

        bot.on_raw_notice = on_raw_notice
        msg = parse(":server NOTICE * :Hello")
        _run(bot._dispatch(msg))
        assert captured == ["Hello"]


# ── Connection lifecycle (_on_connect) ───────────────────────────────


class TestOnConnect:
    def test_sends_nick_and_user(self):
        bot = _bot(nick="mybot", user="myuser", realname="My Bot")
        _run(bot._on_connect())
        calls = [c[0][0] for c in bot.conn.send.call_args_list]
        assert "NICK mybot" in calls
        assert "USER myuser 0 * :My Bot" in calls

    def test_sends_pass_if_configured(self):
        bot = _bot(password="secret")
        _run(bot._on_connect())
        calls = [c[0][0] for c in bot.conn.send.call_args_list]
        assert "PASS secret" in calls

    def test_no_pass_when_empty(self):
        bot = _bot(password="")
        _run(bot._on_connect())
        calls = [c[0][0] for c in bot.conn.send.call_args_list]
        assert all("PASS" not in c for c in calls)

    def test_nick_resets_on_reconnect(self):
        bot = _bot(nick="original")
        bot.nick = "original__"  # simulate previous collision
        _run(bot._on_connect())
        assert bot.nick == "original"
        calls = [c[0][0] for c in bot.conn.send.call_args_list]
        assert "NICK original" in calls


# ── Send helpers ─────────────────────────────────────────────────────


class TestSendHelpers:
    def test_privmsg_sends_correct_format(self):
        bot = _bot()
        _run(bot.privmsg("#test", "hello"))
        bot.conn.send.assert_called_once_with("PRIVMSG #test :hello")

    def test_privmsg_splits_newlines(self):
        bot = _bot()
        _run(bot.privmsg("#test", "line1\nline2\nline3"))
        calls = [c[0][0] for c in bot.conn.send.call_args_list]
        assert calls == [
            "PRIVMSG #test :line1",
            "PRIVMSG #test :line2",
            "PRIVMSG #test :line3",
        ]

    def test_notice_sends_correct_format(self):
        bot = _bot()
        _run(bot.notice("alice", "hi"))
        bot.conn.send.assert_called_once_with("NOTICE alice :hi")

    def test_reply_to_channel_message(self):
        bot = _bot()
        msg = parse(":alice!u@h PRIVMSG #test :hello")
        _run(bot.reply(msg, "world"))
        bot.conn.send.assert_called_once_with("PRIVMSG #test :world")

    def test_reply_to_private_message(self):
        bot = _bot()
        msg = parse(":alice!u@h PRIVMSG testbot :hello")
        _run(bot.reply(msg, "world"))
        bot.conn.send.assert_called_once_with("PRIVMSG alice :world")

    def test_join_sends_correct_format(self):
        bot = _bot()
        _run(bot.join("#newchan"))
        bot.conn.send.assert_called_once_with("JOIN #newchan")

    def test_part_sends_correct_format(self):
        bot = _bot()
        _run(bot.part("#test", "goodbye"))
        bot.conn.send.assert_called_once_with("PART #test :goodbye")

    def test_quit_sends_correct_format(self):
        bot = _bot()
        _run(bot.quit("shutting down"))
        bot.conn.send.assert_called_once_with("QUIT :shutting down")
