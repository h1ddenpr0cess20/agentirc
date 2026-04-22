"""Model discovery and provider resolution helpers."""

from __future__ import annotations

import json
import logging
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

KNOWN_PROVIDERS = ("openai", "xai", "lmstudio")


def _models_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    return f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"


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
    if not model_id.startswith(prefixes):
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


def provider_for_model(model: str, models: dict[str, list[str]]) -> str | None:
    selected = str(model or "").strip()
    if not selected:
        return None

    for provider, provider_models in models.items():
        if selected in provider_models:
            return provider

    lowered = selected.lower()
    if lowered.startswith("grok-"):
        return "xai"
    if lowered.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    return None


def fetch_models(api_base: str, api_key: str = "", provider: str = "openai") -> list[str]:
    """GET models and return filtered chat-capable model IDs."""
    url = _models_url(api_base)
    req = Request(url, method="GET")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError) as exc:
        log.error("Failed to fetch models from %s: %s", url, exc)
        return []

    models = [m["id"] for m in body.get("data", []) if isinstance(m, dict) and "id" in m]
    models = [m for m in models if _is_chat_model(provider, m)]
    models.sort()
    return models


def refresh_model_catalog(
    configured_models: dict[str, list[str]],
    *,
    base_urls: dict[str, str],
    api_keys: dict[str, str],
    server_models: bool = True,
) -> dict[str, list[str]]:
    """Build a provider->models map from config and optional server discovery."""
    merged: dict[str, list[str]] = {
        provider: sorted(dict.fromkeys(configured_models.get(provider, [])))
        for provider in KNOWN_PROVIDERS
    }

    if not server_models:
        return merged

    for provider in KNOWN_PROVIDERS:
        api_base = str(base_urls.get(provider, "") or "").strip()
        if not api_base:
            continue

        api_key = str(api_keys.get(provider, "") or "").strip()

        fetched = fetch_models(api_base, api_key, provider=provider)
        if not fetched:
            continue

        merged[provider] = sorted(dict.fromkeys([*merged[provider], *fetched]))

    return merged


def pick_default_model(models: dict[str, list[str]], preferred: str = "") -> str:
    """Select a default model from preferred value or the catalog."""
    preferred = preferred.strip()
    if preferred:
        return preferred

    for provider in KNOWN_PROVIDERS:
        items = models.get(provider, [])
        if items:
            return items[0]
    raise RuntimeError("No models available from configured providers")


def pick_model(api_base: str, api_key: str = "", preferred: str = "", provider: str = "openai") -> str:
    """Legacy helper: pick a model from a single provider endpoint."""
    available = fetch_models(api_base, api_key, provider=provider)

    if available:
        log.debug("Available models: %s", ", ".join(available))
        if preferred and preferred in available:
            return preferred
        if preferred:
            log.warning("Preferred model %r not found, using %s", preferred, available[0])
        return available[0]

    if preferred:
        log.warning("Could not fetch models from %s, using preferred model %r", api_base, preferred)
        return preferred

    raise RuntimeError(f"No models available from {api_base}")
