"""Tests for agentirc API/model helpers."""

from __future__ import annotations

import asyncio
import logging

from agentirc.api import ResponsesClient
from agentirc.models import pick_model


def _client(api_base: str = "https://api.openai.com") -> ResponsesClient:
    return ResponsesClient(
        api_base=api_base,
        api_key="",
        model="gpt-5-mini",
        system_prompt="be concise",
        max_tokens=200,
        enabled_tools=[],
    )


class TestResponsesClient:
    def test_base_url_with_plain_base(self):
        client = _client("https://api.openai.com")
        assert client._base_url("openai") == "https://api.openai.com/v1"

    def test_base_url_with_v1_base(self):
        client = _client("https://api.openai.com/v1")
        assert client._base_url("openai") == "https://api.openai.com/v1"

    def test_build_request_payload_uses_responses_shape(self):
        client = _client()
        payload = client.build_request_payload(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "be concise"},
                {"role": "user", "content": "hello"},
            ],
        )
        assert payload["instructions"] == "be concise"
        assert payload["input"] == [{"role": "user", "content": "hello"}]

    def test_build_request_payload_xai_keeps_system_in_input(self):
        client = _client()
        payload = client.build_request_payload(
            model="grok-4",
            provider="xai",
            messages=[
                {"role": "system", "content": "be concise"},
                {"role": "user", "content": "hello"},
            ],
            tools=[{"type": "x_search"}],
        )
        assert "instructions" not in payload
        assert payload["input"] == [
            {"role": "system", "content": "be concise"},
            {"role": "user", "content": "hello"},
        ]
        assert payload["include"] == ["no_inline_citations"]

    def test_build_request_payload_omits_instructions_with_previous_response(self):
        client = _client()
        payload = client.build_request_payload(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "be concise"},
                {"role": "user", "content": "hello"},
            ],
            previous_response_id="resp_123",
        )
        assert payload["previous_response_id"] == "resp_123"
        assert "instructions" not in payload

    def test_extract_text_prefers_structured_output(self):
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "one"},
                        {"type": "output_text", "text": "two"},
                    ],
                }
            ],
            "output_text": "fallback",
        }
        assert ResponsesClient._extract_text(response) == "one\ntwo"

    def test_extract_text_falls_back_to_output_text(self):
        assert ResponsesClient._extract_text({"output_text": " hi "}) == "hi"

    def test_create_response_logs_api_call(self, monkeypatch, caplog):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"id": "resp_123", "output_text": "ok"}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                del args, kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                del exc_type, exc, tb
                return False

            async def post(self, url, headers=None, json=None):
                del headers, json
                assert url == "https://api.openai.com/v1/responses"
                return FakeResponse()

        monkeypatch.setattr("agentirc.api.httpx.AsyncClient", FakeClient)
        with caplog.at_level(logging.INFO, logger="agentirc.api"):
            asyncio.run(_client().create_response(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": "hello"}],
            ))

        assert [record.getMessage() for record in caplog.records] == [
            "api POST https://api.openai.com/v1/responses provider=openai model=gpt-5-mini tools=0"
        ]

    def test_list_models_falls_back_to_unfiltered_when_filter_is_empty(self, monkeypatch):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"id": "provider-specific-model-a"}]}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                del args, kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                del exc_type, exc, tb
                return False

            async def get(self, url, headers=None):
                del url, headers
                return FakeResponse()

        monkeypatch.setattr("agentirc.api.httpx.AsyncClient", FakeClient)
        models = asyncio.run(_client().list_models("xai", api_base="https://api.x.ai/v1", api_key="X"))
        assert models == ["provider-specific-model-a"]

    def test_list_models_logs_api_call(self, monkeypatch, caplog):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"id": "grok-4"}]}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                del args, kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                del exc_type, exc, tb
                return False

            async def get(self, url, headers=None):
                del headers
                assert url == "https://api.x.ai/v1/models"
                return FakeResponse()

        monkeypatch.setattr("agentirc.api.httpx.AsyncClient", FakeClient)
        with caplog.at_level(logging.INFO, logger="agentirc.api"):
            asyncio.run(_client().list_models("xai", api_base="https://api.x.ai/v1", api_key="X"))

        assert [record.getMessage() for record in caplog.records] == [
            "api GET https://api.x.ai/v1/models provider=xai"
        ]


class TestPickModel:
    def test_pick_model_uses_preferred_when_listing_fails(self, monkeypatch):
        monkeypatch.setattr("agentirc.models.fetch_models", lambda *_args, **_kwargs: [])
        assert pick_model("https://api.openai.com", preferred="gpt-5-mini") == "gpt-5-mini"
