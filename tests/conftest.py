"""Shared fixtures and helpers for the ircbot test suite."""

from __future__ import annotations

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
    """Remove IRC_* env vars before and after a test to avoid leakage."""
    irc_keys = [k for k in os.environ if k.startswith("IRC_")]
    saved = {k: os.environ.pop(k) for k in irc_keys}
    yield
    # Remove anything the test added
    for k in list(os.environ):
        if k.startswith("IRC_"):
            del os.environ[k]
    # Restore originals
    os.environ.update(saved)
