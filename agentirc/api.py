"""OpenAI-compatible Responses API client."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable

import httpx

from .tools import build_tools

log = logging.getLogger(__name__)


class ResponsesClient:
    """Subset of the agent-smithers Responses client adapted for IRC."""

    LMSTUDIO_FALLBACK_USER_PROMPT = "Please continue the conversation."

    REQUEST_TIMEOUT = httpx.Timeout(300.0)

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        enabled_tools: list[str],
        provider: str = "openai",
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self.enabled_tools = list(enabled_tools)

    @staticmethod
    def _fallback_base_url(provider: str) -> str:
        if provider == "lmstudio":
            return "http://127.0.0.1:1234/v1"
        if provider == "xai":
            return "https://api.x.ai/v1"
        return "https://api.openai.com/v1"

    def _base_url(self, provider: str, api_base: str | None = None) -> str:
        configured = str(api_base or self.api_base or "").strip().rstrip("/")
        base = configured or self._fallback_base_url(provider)
        if base.endswith("/v1"):
            return base
        return f"{base}/v1"

    def _headers(self, api_key: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = str(self.api_key if api_key is None else api_key).strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Raise for HTTP errors, logging the provider's error body first.

        ``raise_for_status`` alone discards the response body, which is where
        providers put the actionable detail (unknown model, context-length
        exceeded, invalid tool, auth failure).
        """
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            body = (response.text or "").strip()
            if body:
                log.error("api error %s: %s", response.status_code, body[:1000])
            raise

    @staticmethod
    def _supports_instructions(provider: str) -> bool:
        return provider != "xai"

    @staticmethod
    def _has_user_message(items: Iterable[dict[str, Any]]) -> bool:
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("role") or "").strip() == "user" and str(item.get("content") or "").strip():
                return True
        return False

    @classmethod
    def _ensure_lmstudio_user_message(
        cls,
        items: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        final_items = [dict(item) for item in items if isinstance(item, dict)]
        if cls._has_user_message(final_items):
            return final_items
        final_items.append({"role": "user", "content": cls.LMSTUDIO_FALLBACK_USER_PROMPT})
        return final_items

    @staticmethod
    def _merge_include_items(existing: Any, additions: Iterable[str]) -> list[str]:
        merged: list[str] = []
        seen = set()
        for value in existing if isinstance(existing, list) else []:
            if isinstance(value, str) and value and value not in seen:
                merged.append(value)
                seen.add(value)
        for value in additions:
            if value and value not in seen:
                merged.append(value)
                seen.add(value)
        return merged

    @staticmethod
    def _is_chat_model(provider: str, model_id: str) -> bool:
        lowered = model_id.lower()
        if provider == "lmstudio":
            blocked_models = {
                "text-embedding-nomic-embed-text-v1.5",
            }
            if lowered in blocked_models:
                return False
            return bool(model_id.strip())
        if provider == "xai":
            if not lowered.startswith("grok-"):
                return False
            blocked_fragments = ("imagine", "image", "video", "voice", "vision")
            return not any(fragment in lowered for fragment in blocked_fragments)

        prefixes = ("gpt-", "o1", "o3", "o4")
        if not lowered.startswith(prefixes):
            return False

        blocked_fragments = (
            "preview",
            "audio",
            "computer-use",
            "transcribe",
            "tts",
            "image",
        )
        if any(fragment in lowered for fragment in blocked_fragments):
            return False

        if re.search(r"-\d{4}-\d{2}-\d{2}$", lowered):
            return False

        return True

    @staticmethod
    def build_input_items(
        messages: Iterable[dict[str, Any]],
        *,
        include_system: bool = False,
    ) -> tuple[str | None, list[dict[str, str]]]:
        instructions: list[str] = []
        input_items: list[dict[str, str]] = []
        for message in messages:
            role = str(message.get("role") or "").strip()
            content = str(message.get("content") or "")
            if not role or not content:
                continue
            if role == "system":
                if include_system:
                    input_items.append({"role": role, "content": content})
                else:
                    instructions.append(content)
                continue
            if role in {"user", "assistant"}:
                input_items.append({"role": role, "content": content})
        joined = "\n\n".join(part.strip() for part in instructions if part.strip()).strip()
        return (joined or None, input_items)

    def build_request_payload(
        self,
        *,
        model: str,
        messages: Iterable[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        previous_response_id: str | None = None,
        input_items: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        instructions: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        provider_name = provider or self.provider
        payload: dict[str, Any] = {"model": model}
        derived_instructions = instructions
        derived_input: list[dict[str, Any]] = []
        supports_instructions = self._supports_instructions(provider_name)
        if messages is not None:
            derived_instructions, derived_input = self.build_input_items(
                messages,
                include_system=not supports_instructions,
            )
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        if supports_instructions and derived_instructions and not previous_response_id:
            payload["instructions"] = derived_instructions
        final_input = input_items if input_items is not None else derived_input
        if provider_name == "lmstudio" and messages is not None and input_items is None:
            final_input = self._ensure_lmstudio_user_message(final_input)
        if final_input:
            payload["input"] = final_input
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        if options:
            for key, value in options.items():
                if value is not None:
                    payload[key] = value
        payload["store"] = False

        if provider_name == "xai" and any(
            isinstance(tool, dict) and tool.get("type") in {"web_search", "x_search"}
            for tool in (tools or [])
        ):
            payload["include"] = self._merge_include_items(
                payload.get("include"),
                ["no_inline_citations"],
            )
        return payload

    async def create_response(
        self,
        *,
        model: str,
        messages: Iterable[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        previous_response_id: str | None = None,
        input_items: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        instructions: str | None = None,
        provider: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """POST a built payload to ``/responses`` and return the decoded JSON."""
        provider_name = provider or self.provider
        base_url = self._base_url(provider_name, api_base)
        payload = self.build_request_payload(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            previous_response_id=previous_response_id,
            input_items=input_items,
            options=options,
            instructions=instructions,
            provider=provider_name,
        )
        log.info(
            "api POST %s/responses provider=%s model=%s tools=%d",
            base_url,
            provider_name,
            model,
            len(tools or []),
        )
        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/responses",
                headers=self._headers(api_key),
                json=payload,
            )
            self._raise_for_status(response)
            return response.json()

    async def ask_messages(
        self,
        messages: Iterable[dict[str, Any]],
        *,
        model: str | None = None,
        enabled_tools: list[str] | None = None,
        built_tools: list[dict[str, Any]] | None = None,
        provider: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, str | None]:
        """Send a full message history and return ``(text, response_id)``.

        Tools may be supplied pre-built via *built_tools*, otherwise they are
        constructed from *enabled_tools* (or the client default).
        """
        provider_name = provider or self.provider
        final_model = model or self.model
        if built_tools is not None:
            tools = built_tools
        else:
            tools = build_tools(
                self.enabled_tools if enabled_tools is None else enabled_tools,
                provider=provider_name,
            )
        options = {}
        if max_tokens is not None:
            options["max_output_tokens"] = max_tokens
        result = await self.create_response(
            model=final_model,
            messages=messages,
            tools=tools,
            options=options or None,
            provider=provider_name,
            api_base=api_base,
            api_key=api_key,
        )
        log.debug("Raw API response: %s", json.dumps(result, indent=2))
        text = self._extract_text(result)
        response_id = result.get("id")
        return text, response_id

    async def list_models(
        self,
        provider: str,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> list[str]:
        """Fetch the provider's model IDs, filtered to chat-capable models.

        Falls back to the unfiltered list when the filter removes everything.
        """
        base_url = self._base_url(provider, api_base)
        log.info("api GET %s/models provider=%s", base_url, provider)
        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
            response = await client.get(
                f"{base_url}/models",
                headers=self._headers(api_key),
            )
            self._raise_for_status(response)
            payload = response.json()
        model_ids = [
            str(item.get("id") or "").strip()
            for item in payload.get("data", [])
            if isinstance(item, dict)
        ]
        filtered = sorted({model_id for model_id in model_ids if self._is_chat_model(provider, model_id)})
        return filtered or sorted({model_id for model_id in model_ids if model_id})

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in response.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []) or []:
                ctype = content.get("type")
                if ctype == "output_text":
                    text = str(content.get("text") or "")
                elif ctype == "refusal":
                    # OpenAI returns refusals as a distinct content part.
                    text = str(content.get("refusal") or "")
                else:
                    continue
                if text:
                    parts.append(text)
        if parts:
            return "\n".join(parts).strip()
        return str(response.get("output_text") or "").strip() or "(no response)"
