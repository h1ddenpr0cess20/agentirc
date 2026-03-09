"""Tests for ircbot.protocol -- IRC message parsing (RFC 2812).

Coverage strategy:
- parse_prefix: nick!user@host, nick@host, bare nick, server name
- parse: full messages with prefix, without prefix, trailing params,
  no params, multiple middle params, numeric commands, CTCP,
  command-only lines, case normalization
- IRCMessage properties: target, text, is_channel, reply_target
"""

from __future__ import annotations

import pytest

from ircbot.protocol import IRCMessage, parse, parse_prefix


# ── parse_prefix ──────────────────────────────────────────────────────

class TestParsePrefix:
    def test_full_nick_user_host(self):
        nick, user, host = parse_prefix("alice!~alice@host.example.com")
        assert nick == "alice"
        assert user == "~alice"
        assert host == "host.example.com"

    def test_nick_at_host_no_user(self):
        nick, user, host = parse_prefix("bob@server.example")
        assert nick == "bob"
        assert user == ""
        assert host == "server.example"

    def test_bare_nick_no_user_no_host(self):
        nick, user, host = parse_prefix("ChanServ")
        assert nick == "ChanServ"
        assert user == ""
        assert host == ""

    def test_server_name_with_dots(self):
        nick, user, host = parse_prefix("irc.libera.chat")
        assert nick == "irc.libera.chat"
        assert user == ""
        assert host == ""

    def test_empty_prefix(self):
        nick, user, host = parse_prefix("")
        assert nick == ""
        assert user == ""
        assert host == ""

    def test_user_with_at_sign_in_host(self):
        """The first ! splits nick from user, the first @ in the rest splits user from host."""
        nick, user, host = parse_prefix("x!y@z@w")
        assert nick == "x"
        assert user == "y"
        assert host == "z@w"


# ── parse ─────────────────────────────────────────────────────────────

class TestParse:
    def test_privmsg_with_prefix_and_trailing(self):
        raw = ":alice!~a@host PRIVMSG #test :hello world"
        msg = parse(raw)
        assert msg.prefix == "alice!~a@host"
        assert msg.nick == "alice"
        assert msg.user == "~a"
        assert msg.host == "host"
        assert msg.command == "PRIVMSG"
        assert msg.params == ["#test", "hello world"]
        assert msg.raw is raw

    def test_ping_no_prefix(self):
        msg = parse("PING :some.server.com")
        assert msg.prefix == ""
        assert msg.nick == ""
        assert msg.command == "PING"
        assert msg.params == ["some.server.com"]
        assert msg.text == "some.server.com"

    def test_numeric_welcome(self):
        raw = ":irc.server 001 mybot :Welcome to IRC"
        msg = parse(raw)
        assert msg.command == "001"
        assert msg.nick == "irc.server"
        assert msg.params == ["mybot", "Welcome to IRC"]

    def test_join_trailing_channel(self):
        raw = ":alice!~a@host JOIN :#channel"
        msg = parse(raw)
        assert msg.command == "JOIN"
        assert msg.params == ["#channel"]
        assert msg.target == "#channel"

    def test_join_no_trailing_colon(self):
        raw = ":alice!~a@host JOIN #channel"
        msg = parse(raw)
        assert msg.command == "JOIN"
        assert msg.params == ["#channel"]

    def test_kick_with_multiple_params_and_trailing(self):
        raw = ":op!~op@host KICK #channel baduser :Get out"
        msg = parse(raw)
        assert msg.command == "KICK"
        assert msg.params == ["#channel", "baduser", "Get out"]
        assert msg.target == "#channel"

    def test_command_only_no_params(self):
        msg = parse("QUIT")
        assert msg.command == "QUIT"
        assert msg.params == []
        assert msg.target == ""
        assert msg.text == ""

    def test_command_uppercased(self):
        msg = parse(":server privmsg #chan :hi")
        assert msg.command == "PRIVMSG"

    def test_ctcp_version_in_privmsg(self):
        raw = ":alice!a@h PRIVMSG testbot :\x01VERSION\x01"
        msg = parse(raw)
        assert msg.command == "PRIVMSG"
        assert msg.text == "\x01VERSION\x01"

    def test_trailing_only_message(self):
        raw = ":server NOTICE * :Looking up your hostname"
        msg = parse(raw)
        assert msg.command == "NOTICE"
        assert msg.params == ["*", "Looking up your hostname"]

    def test_empty_trailing(self):
        raw = ":server NOTICE * :"
        msg = parse(raw)
        assert msg.params == ["*", ""]

    def test_multiple_middle_params_no_trailing(self):
        raw = ":server 005 bot CHANTYPES=# PREFIX=(ov)@+"
        msg = parse(raw)
        assert msg.command == "005"
        assert msg.params == ["bot", "CHANTYPES=#", "PREFIX=(ov)@+"]

    def test_preserves_raw(self):
        raw = "PING :12345"
        msg = parse(raw)
        assert msg.raw == raw


# ── IRCMessage properties ────────────────────────────────────────────

class TestIRCMessageProperties:
    def test_target_returns_first_param(self):
        msg = parse(":nick!u@h PRIVMSG #chan :text")
        assert msg.target == "#chan"

    def test_target_empty_when_no_params(self):
        msg = parse("QUIT")
        assert msg.target == ""

    def test_text_returns_last_param(self):
        msg = parse(":nick!u@h PRIVMSG #chan :hello")
        assert msg.text == "hello"

    def test_text_empty_when_no_params(self):
        msg = parse("QUIT")
        assert msg.text == ""

    def test_is_channel_hash(self):
        msg = parse(":n!u@h PRIVMSG #chan :x")
        assert msg.is_channel is True

    def test_is_channel_ampersand(self):
        msg = parse(":n!u@h PRIVMSG &chan :x")
        assert msg.is_channel is True

    def test_is_channel_bang(self):
        msg = parse(":n!u@h PRIVMSG !chan :x")
        assert msg.is_channel is True

    def test_is_channel_plus(self):
        msg = parse(":n!u@h PRIVMSG +chan :x")
        assert msg.is_channel is True

    def test_is_channel_false_for_nick(self):
        msg = parse(":n!u@h PRIVMSG someone :x")
        assert msg.is_channel is False

    def test_is_channel_false_when_no_params(self):
        msg = parse("QUIT")
        assert msg.is_channel is False

    def test_reply_target_channel_message(self):
        msg = parse(":alice!u@h PRIVMSG #test :hello")
        assert msg.reply_target == "#test"

    def test_reply_target_private_message(self):
        msg = parse(":alice!u@h PRIVMSG botname :hello")
        assert msg.reply_target == "alice"

    def test_single_param_target_and_text_are_same(self):
        """When there's exactly one param, target and text both return it."""
        msg = parse(":alice!u@h JOIN #chan")
        assert msg.target == "#chan"
        assert msg.text == "#chan"
