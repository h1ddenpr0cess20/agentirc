"""Tests for ircbot.config -- .env loading and BotConfig construction.

Coverage strategy:
- load_env: parses key=value, skips comments/blanks, handles quotes,
  respects existing env vars (setdefault behavior), missing file
- BotConfig.from_env: required fields, defaults, channel parsing,
  TLS flag parsing, missing required key raises KeyError
"""

from __future__ import annotations

import os
import pytest

from ircbot.config import BotConfig, load_env


# ── load_env ──────────────────────────────────────────────────────────

class TestLoadEnv:
    def test_loads_key_value_pairs(self, tmp_path, env_cleanup):
        dotenv = tmp_path / ".env"
        dotenv.write_text("MY_TEST_KEY=hello\n")
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "hello"

    def test_strips_double_quotes(self, tmp_path, env_cleanup):
        dotenv = tmp_path / ".env"
        dotenv.write_text('MY_TEST_KEY="quoted value"\n')
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "quoted value"

    def test_strips_single_quotes(self, tmp_path, env_cleanup):
        dotenv = tmp_path / ".env"
        dotenv.write_text("MY_TEST_KEY='single quoted'\n")
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "single quoted"

    def test_does_not_strip_mismatched_quotes(self, tmp_path, env_cleanup):
        dotenv = tmp_path / ".env"
        dotenv.write_text("MY_TEST_KEY=\"mismatch'\n")
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "\"mismatch'"

    def test_skips_comments(self, tmp_path, env_cleanup):
        dotenv = tmp_path / ".env"
        dotenv.write_text("# this is a comment\nMY_TEST_KEY=val\n")
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "val"

    def test_skips_blank_lines(self, tmp_path, env_cleanup):
        dotenv = tmp_path / ".env"
        dotenv.write_text("\n\n  \nMY_TEST_KEY=val\n")
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "val"

    def test_skips_lines_without_equals(self, tmp_path, env_cleanup):
        dotenv = tmp_path / ".env"
        dotenv.write_text("NOEQUALS\nMY_TEST_KEY=ok\n")
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "ok"
        assert os.environ.get("NOEQUALS") is None

    def test_setdefault_does_not_overwrite_existing(self, tmp_path, env_cleanup):
        os.environ["MY_TEST_KEY"] = "original"
        dotenv = tmp_path / ".env"
        dotenv.write_text("MY_TEST_KEY=should_not_win\n")
        load_env(str(dotenv))
        assert os.environ["MY_TEST_KEY"] == "original"

    def test_missing_file_is_silently_ignored(self, tmp_path):
        # Should not raise
        load_env(str(tmp_path / "nonexistent.env"))

    def test_value_with_equals_sign(self, tmp_path, env_cleanup):
        """Only the first = is the delimiter; the rest are part of the value."""
        dotenv = tmp_path / ".env"
        dotenv.write_text("MY_TEST_KEY=a=b=c\n")
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "a=b=c"

    def test_strips_whitespace_around_key_and_value(self, tmp_path, env_cleanup):
        dotenv = tmp_path / ".env"
        dotenv.write_text("  MY_TEST_KEY  =  spaced  \n")
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "spaced"

    def test_single_char_quoted_value_not_stripped(self, tmp_path, env_cleanup):
        """A single-char value like 'x' has len < 2, so quotes should not be stripped."""
        dotenv = tmp_path / ".env"
        dotenv.write_text("MY_TEST_KEY=x\n")
        load_env(str(dotenv))
        assert os.environ.get("MY_TEST_KEY") == "x"


# ── BotConfig.from_env ───────────────────────────────────────────────

class TestBotConfigFromEnv:
    def test_minimal_required_fields(self, env_cleanup):
        os.environ["IRC_HOST"] = "irc.example.com"
        os.environ["IRC_NICK"] = "mybot"
        cfg = BotConfig.from_env()
        assert cfg.host == "irc.example.com"
        assert cfg.nick == "mybot"
        assert cfg.port == 6667
        assert cfg.user == "mybot"  # defaults to nick
        assert cfg.realname == "IRC Bot"
        assert cfg.channels == []
        assert cfg.password == ""
        assert cfg.use_tls is False
        assert cfg.command_prefix == "!"

    def test_missing_host_raises_key_error(self, env_cleanup):
        os.environ["IRC_NICK"] = "mybot"
        with pytest.raises(KeyError, match="IRC_HOST"):
            BotConfig.from_env()

    def test_missing_nick_raises_key_error(self, env_cleanup):
        os.environ["IRC_HOST"] = "irc.example.com"
        with pytest.raises(KeyError, match="IRC_NICK"):
            BotConfig.from_env()

    def test_channels_parsed_from_comma_separated(self, env_cleanup):
        os.environ["IRC_HOST"] = "h"
        os.environ["IRC_NICK"] = "n"
        os.environ["IRC_CHANNELS"] = "#a, #b , #c"
        cfg = BotConfig.from_env()
        assert cfg.channels == ["#a", "#b", "#c"]

    def test_empty_channels_string(self, env_cleanup):
        os.environ["IRC_HOST"] = "h"
        os.environ["IRC_NICK"] = "n"
        os.environ["IRC_CHANNELS"] = ""
        cfg = BotConfig.from_env()
        assert cfg.channels == []

    def test_tls_true_variants(self, env_cleanup):
        os.environ["IRC_HOST"] = "h"
        os.environ["IRC_NICK"] = "n"
        for val in ("1", "true", "True", "TRUE", "yes", "Yes"):
            os.environ["IRC_USE_TLS"] = val
            cfg = BotConfig.from_env()
            assert cfg.use_tls is True, f"Expected True for IRC_USE_TLS={val}"

    def test_tls_false_variants(self, env_cleanup):
        os.environ["IRC_HOST"] = "h"
        os.environ["IRC_NICK"] = "n"
        for val in ("0", "false", "no", "random"):
            os.environ["IRC_USE_TLS"] = val
            cfg = BotConfig.from_env()
            assert cfg.use_tls is False, f"Expected False for IRC_USE_TLS={val}"

    def test_custom_port_and_prefix(self, env_cleanup):
        os.environ["IRC_HOST"] = "h"
        os.environ["IRC_NICK"] = "n"
        os.environ["IRC_PORT"] = "6697"
        os.environ["IRC_CMD_PREFIX"] = "."
        cfg = BotConfig.from_env()
        assert cfg.port == 6697
        assert cfg.command_prefix == "."

    def test_password_set(self, env_cleanup):
        os.environ["IRC_HOST"] = "h"
        os.environ["IRC_NICK"] = "n"
        os.environ["IRC_PASSWORD"] = "secret"
        cfg = BotConfig.from_env()
        assert cfg.password == "secret"

    def test_custom_user_and_realname(self, env_cleanup):
        os.environ["IRC_HOST"] = "h"
        os.environ["IRC_NICK"] = "n"
        os.environ["IRC_USER"] = "customuser"
        os.environ["IRC_REALNAME"] = "My Real Name"
        cfg = BotConfig.from_env()
        assert cfg.user == "customuser"
        assert cfg.realname == "My Real Name"


class TestBotConfigFrozen:
    def test_cannot_mutate_fields(self, minimal_config):
        with pytest.raises(AttributeError):
            minimal_config.host = "other"  # type: ignore[misc]
