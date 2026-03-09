"""Tests for chatbot model filtering/provider mapping and tool building."""

from __future__ import annotations

from chatbot.models import _is_chat_model, provider_for_model, refresh_model_catalog
from chatbot.tools import build_tools, tools_for_model


class TestModelFiltering:
    def test_openai_chat_model_filter(self):
        assert _is_chat_model("openai", "gpt-5-mini") is True
        assert _is_chat_model("openai", "o3-pro") is True
        assert _is_chat_model("openai", "gpt-4.1-2025-04-14") is False
        assert _is_chat_model("openai", "gpt-4o-mini-tts") is False
        assert _is_chat_model("openai", "computer-use-preview") is False

    def test_xai_chat_model_filter(self):
        assert _is_chat_model("xai", "grok-4") is True
        assert _is_chat_model("xai", "grok-3-mini") is True
        assert _is_chat_model("xai", "grok-imagine-image") is False

    def test_provider_for_model_uses_list_and_heuristics(self):
        models = {
            "openai": ["gpt-5-mini"],
            "xai": ["grok-4"],
            "lmstudio": ["local-model"],
        }
        assert provider_for_model("local-model", models) == "lmstudio"
        assert provider_for_model("grok-4-fast-reasoning", models) == "xai"
        assert provider_for_model("o4-mini", models) == "openai"

    def test_refresh_model_catalog_merges_fetched_models(self, monkeypatch):
        def fake_fetch(_base: str, _key: str, provider: str = "openai"):
            return {
                "openai": ["gpt-5-mini", "o3-pro"],
                "xai": ["grok-4"],
                "lmstudio": ["local-model"],
            }[provider]

        monkeypatch.setattr("chatbot.models.fetch_models", fake_fetch)
        merged = refresh_model_catalog(
            configured_models={
                "openai": ["gpt-5-mini"],
                "xai": [],
                "lmstudio": [],
            },
            base_urls={
                "openai": "https://api.openai.com",
                "xai": "https://api.x.ai/v1",
                "lmstudio": "http://127.0.0.1:1234/v1",
            },
            api_keys={
                "openai": "O",
                "xai": "X",
                "lmstudio": "",
            },
            server_models=True,
        )
        assert merged["openai"] == ["gpt-5-mini", "o3-pro"]
        assert merged["xai"] == ["grok-4"]
        assert merged["lmstudio"] == ["local-model"]


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
