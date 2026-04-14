"""Tests for .country command, store=false, and search country tooling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from agentirc.bot import ChatBot
from agentirc.config import ChatConfig
from agentirc.tools import build_tools, strip_search_country
from ircbot.config import BotConfig
from ircbot.protocol import parse


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _cfg(*, web_search_country: str = "") -> ChatConfig:
    return ChatConfig(
        irc=BotConfig(
            host="irc.test",
            port=6667,
            nick="testbot",
            user="testbot",
            realname="Test Bot",
            channels=["#test"],
            password="",
            use_tls=False,
            command_prefix="!",
        ),
        models={
            "xai": ["grok-4-1-fast-non-reasoning", "grok-4"],
            "lmstudio": ["local-model"],
        },
        api_keys={
            "xai": "X",
            "lmstudio": "",
        },
        base_urls={
            "xai": "https://api.x.ai/v1",
            "lmstudio": "http://127.0.0.1:1234/v1",
        },
        default_model="grok-4-1-fast-non-reasoning",
        tools=["web_search", "x_search", "code_interpreter"],
        admins=["admin"],
        server_models=False,
        web_search_country=web_search_country,
    )


def _make_bot(**kwargs) -> ChatBot:
    chat = ChatBot(_cfg(**kwargs))
    chat.bot.conn.send = AsyncMock()
    return chat


class TestBuildToolsCountry:
    def test_web_search_includes_country(self):
        tools = build_tools(["web_search"], "xai", web_search_country="US")
        ws = [t for t in tools if t["type"] == "web_search"][0]
        assert ws["user_location"]["country"] == "US"

    def test_web_search_no_country(self):
        tools = build_tools(["web_search"], "xai", web_search_country="")
        ws = [t for t in tools if t["type"] == "web_search"][0]
        assert "user_location" not in ws

    def test_strip_search_country(self):
        tools = build_tools(["web_search"], "xai", web_search_country="GB")
        stripped = strip_search_country(tools)
        assert "user_location" not in stripped[0]


class TestCountryCommand:
    def test_no_country_configured(self):
        chat = _make_bot()
        msg = parse(":admin!u@h PRIVMSG #test :!country")
        _run(chat.bot._try_command(msg))
        sent = chat.bot.conn.send.call_args[0][0]
        assert "not set" in sent.lower() or "not configured" in sent.lower()

    def test_country_status(self):
        chat = _make_bot(web_search_country="US")
        msg = parse(":admin!u@h PRIVMSG #test :!country status")
        _run(chat.bot._try_command(msg))
        sent = chat.bot.conn.send.call_args[0][0]
        assert "enabled" in sent.lower()

    def test_country_disable(self):
        chat = _make_bot(web_search_country="US")
        assert chat.search_country_enabled is True
        msg = parse(":admin!u@h PRIVMSG #test :!country off")
        _run(chat.bot._try_command(msg))
        assert chat.search_country_enabled is False

    def test_country_enable(self):
        chat = _make_bot(web_search_country="US")
        chat.search_country_enabled = False
        msg = parse(":admin!u@h PRIVMSG #test :!country on")
        _run(chat.bot._try_command(msg))
        assert chat.search_country_enabled is True

    def test_country_toggle(self):
        chat = _make_bot(web_search_country="US")
        assert chat.search_country_enabled is True
        msg = parse(":admin!u@h PRIVMSG #test :!country toggle")
        _run(chat.bot._try_command(msg))
        assert chat.search_country_enabled is False

    def test_country_non_admin(self):
        chat = _make_bot(web_search_country="US")
        msg = parse(":alice!u@h PRIVMSG #test :!country off")
        _run(chat.bot._try_command(msg))
        sent = chat.bot.conn.send.call_args[0][0]
        assert "Admin only." in sent


class TestLocationCommand:
    def test_location_set(self):
        chat = _make_bot()
        msg = parse(":alice!u@h PRIVMSG #test :!location New York")
        _run(chat.bot._try_command(msg))
        sent = chat.bot.conn.send.call_args[0][0]
        assert "New York" in sent

    def test_location_show(self):
        chat = _make_bot()
        chat.history.set_location("alice", "Tokyo")
        msg = parse(":alice!u@h PRIVMSG #test :!location")
        _run(chat.bot._try_command(msg))
        sent = chat.bot.conn.send.call_args[0][0]
        assert "Tokyo" in sent

    def test_location_clear(self):
        chat = _make_bot()
        chat.history.set_location("alice", "Tokyo")
        msg = parse(":alice!u@h PRIVMSG #test :!location clear")
        _run(chat.bot._try_command(msg))
        assert chat.history.get_location("alice") is None

    def test_location_no_location_set(self):
        chat = _make_bot()
        msg = parse(":alice!u@h PRIVMSG #test :!location")
        _run(chat.bot._try_command(msg))
        sent = chat.bot.conn.send.call_args[0][0]
        assert "No location set" in sent


class TestStoreDisabled:
    def test_store_false_in_payload(self):
        from agentirc.api import ResponsesClient
        client = ResponsesClient(
            api_base="https://api.x.ai/v1",
            api_key="test",
            model="grok-4-1-fast-non-reasoning",
            system_prompt="test",
            max_tokens=100,
            enabled_tools=[],
            provider="xai",
        )
        payload = client.build_request_payload(
            model="grok-4-1-fast-non-reasoning",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert payload["store"] is False
