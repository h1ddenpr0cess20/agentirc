"""Tests for agentirc model filtering/provider mapping and tool building."""

from __future__ import annotations

from agentirc.models import _is_chat_model, provider_for_model, refresh_model_catalog
from agentirc.tools import build_tools, tools_for_model


class TestModelFiltering:
    def test_xai_chat_model_filter(self):
        assert _is_chat_model("xai", "grok-4") is True
        assert _is_chat_model("xai", "grok-3-mini") is True
        assert _is_chat_model("xai", "grok-imagine-image") is False

    def test_provider_for_model_uses_list_and_heuristics(self):
        models = {
            "xai": ["grok-4"],
            "lmstudio": ["local-model"],
        }
        assert provider_for_model("local-model", models) == "lmstudio"
        assert provider_for_model("grok-4-fast-reasoning", models) == "xai"

    def test_refresh_model_catalog_merges_fetched_models(self, monkeypatch):
        def fake_fetch(_base: str, _key: str, provider: str = "xai"):
            return {
                "xai": ["grok-4"],
                "lmstudio": ["local-model"],
            }[provider]

        monkeypatch.setattr("agentirc.models.fetch_models", fake_fetch)
        merged = refresh_model_catalog(
            configured_models={
                "xai": [],
                "lmstudio": [],
            },
            base_urls={
                "xai": "https://api.x.ai/v1",
                "lmstudio": "http://127.0.0.1:1234/v1",
            },
            api_keys={
                "xai": "X",
                "lmstudio": "",
            },
            server_models=True,
        )
        assert merged["xai"] == ["grok-4"]
        assert merged["lmstudio"] == ["local-model"]


class TestTools:
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
