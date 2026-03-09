"""Tests for chatbot command behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from chatbot.bot import ChatBot
from chatbot.config import ChatConfig
from ircbot.config import BotConfig
from ircbot.protocol import parse


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _cfg() -> ChatConfig:
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
            "openai": ["gpt-5-mini"],
            "xai": ["grok-4"],
            "lmstudio": ["local-model"],
        },
        api_keys={
            "openai": "O",
            "xai": "X",
            "lmstudio": "",
        },
        base_urls={
            "openai": "https://api.openai.com",
            "xai": "https://api.x.ai/v1",
            "lmstudio": "http://127.0.0.1:1234/v1",
        },
        default_model="gpt-5-mini",
        tools=["web_search", "x_search", "code_interpreter"],
        admins=["admin"],
        server_models=False,
    )


def _make_bot() -> ChatBot:
    chat = ChatBot(_cfg())
    chat.bot.conn.send = AsyncMock()
    return chat


class TestChatbotCommands:
    def test_non_admin_cannot_use_model_command(self):
        chat = _make_bot()
        msg = parse(":alice!u@h PRIVMSG #test :!model grok-4")
        _run(chat.bot._try_command(msg))
        sent = chat.bot.conn.send.call_args[0][0]
        assert "Admin only." in sent

    def test_mymodel_affects_provider_used_by_chat(self):
        chat = _make_bot()
        chat.client.ask = AsyncMock(return_value=("ok", "resp_1"))

        _run(chat.bot._try_command(parse(":alice!u@h PRIVMSG #test :!mymodel grok-4")))
        _run(chat.bot._try_command(parse(":alice!u@h PRIVMSG #test :!chat hello")))

        kwargs = chat.client.ask.await_args.kwargs
        assert kwargs["model"] == "grok-4"
        assert kwargs["provider"] == "xai"
        assert kwargs["enabled_tools"] == ["web_search", "x_search", "code_interpreter"]

    def test_tools_off_disables_tools_in_chat_requests(self):
        chat = _make_bot()
        chat.client.ask = AsyncMock(return_value=("ok", "resp_1"))

        _run(chat.bot._try_command(parse(":admin!u@h PRIVMSG #test :!tools off")))
        _run(chat.bot._try_command(parse(":admin!u@h PRIVMSG #test :!chat hello")))

        kwargs = chat.client.ask.await_args.kwargs
        assert kwargs["enabled_tools"] == []

    def test_stock_removes_system_prompt(self):
        chat = _make_bot()
        chat.client.ask = AsyncMock(return_value=("ok", "resp_1"))

        _run(chat.bot._try_command(parse(":alice!u@h PRIVMSG #test :!stock")))
        _run(chat.bot._try_command(parse(":alice!u@h PRIVMSG #test :!chat hello")))

        kwargs = chat.client.ask.await_args.kwargs
        assert kwargs["system_prompt"] is None

    def test_clear_resets_global_model(self):
        chat = _make_bot()
        _run(chat.bot._try_command(parse(":admin!u@h PRIVMSG #test :!model grok-4")))
        assert chat.model == "grok-4"

        _run(chat.bot._try_command(parse(":admin!u@h PRIVMSG #test :!clear")))
        assert chat.model == chat.default_model

