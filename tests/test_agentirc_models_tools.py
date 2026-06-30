"""Tests for agentirc model filtering/provider mapping and tool building."""

from __future__ import annotations

import pytest

from agentirc.api import ResponsesClient
from agentirc.models import pick_default_model, provider_for_model
from agentirc.tools import build_tools, tools_for_model


class TestModelFiltering:
    def test_openai_chat_model_filter(self):
        assert ResponsesClient._is_chat_model("openai", "gpt-5-mini") is True
        assert ResponsesClient._is_chat_model("openai", "o3-pro") is True
        assert ResponsesClient._is_chat_model("openai", "gpt-4.1-2025-04-14") is False
        assert ResponsesClient._is_chat_model("openai", "gpt-4o-mini-tts") is False
        assert ResponsesClient._is_chat_model("openai", "computer-use-preview") is False

    def test_xai_chat_model_filter(self):
        assert ResponsesClient._is_chat_model("xai", "grok-4") is True
        assert ResponsesClient._is_chat_model("xai", "grok-3-mini") is True
        assert ResponsesClient._is_chat_model("xai", "grok-imagine-image") is False

    def test_provider_for_model_uses_list_and_heuristics(self):
        models = {
            "openai": ["gpt-5-mini"],
            "xai": ["grok-4"],
            "lmstudio": ["local-model"],
        }
        assert provider_for_model("local-model", models) == "lmstudio"
        assert provider_for_model("grok-4-fast-reasoning", models) == "xai"
        assert provider_for_model("o4-mini", models) == "openai"
        assert provider_for_model("unknown-model", models) is None

    def test_pick_default_model_prefers_explicit_then_catalog(self):
        models = {"xai": ["grok-4"], "lmstudio": ["local-model"]}
        assert pick_default_model(models, preferred="grok-3-mini") == "grok-3-mini"
        assert pick_default_model(models) == "grok-4"
        with pytest.raises(RuntimeError):
            pick_default_model({"xai": [], "lmstudio": []})


class TestTools:
    def test_openai_tools(self):
        tools = build_tools(["web_search", "x_search", "code_interpreter"], provider="openai")
        assert tools == [
            {"type": "web_search"},
            {"type": "code_interpreter", "container": {"type": "auto"}},
        ]

    def test_xai_tools(self):
        tools = build_tools(["web_search", "x_search", "code_interpreter"], provider="xai")
        assert tools == [
            {"type": "web_search"},
            {"type": "x_search"},
            {"type": "code_interpreter"},
        ]

    def test_xai_non_grok4_model_disables_hosted_tools(self):
        tools = tools_for_model(
            ["web_search", "x_search", "code_interpreter"],
            provider="xai",
            model="grok-3-mini",
        )
        assert tools == []

    def test_lmstudio_tools(self):
        tools = build_tools(["web_search", "x_search", "code_interpreter"], provider="lmstudio")
        assert tools == []

    def test_mcp_tools_built_from_servers(self):
        servers = [{"server_label": "demo", "server_url": "https://example.com/mcp"}]
        tools = build_tools(["mcp"], provider="xai", mcp_servers=servers)
        assert tools == [
            {
                "type": "mcp",
                "server_label": "demo",
                "server_url": "https://example.com/mcp",
                "require_approval": "never",
            }
        ]
