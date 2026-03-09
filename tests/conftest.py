"""Shared fixtures and helpers for the ircbot test suite."""

from __future__ import annotations

import asyncio
import os
import pytest

from ircbot.config import BotConfig


@pytest.fixture
def minimal_config() -> BotConfig:
    """A BotConfig with sensible defaults for unit testing."""
    return BotConfig(
        host="irc.test.local",
        port=6667,
        nick="testbot",
        user="testbot",
        realname="Test Bot",
        channels=["#test"],
        password="",
        use_tls=False,
        command_prefix="!",
    )


@pytest.fixture
def env_cleanup():
    """Restore the environment after each test to avoid leakage."""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture(autouse=True)
def event_loop_guard():
    """Provide a default event loop for tests using asyncio.get_event_loop()."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()
        asyncio.set_event_loop(None)
