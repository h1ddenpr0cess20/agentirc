"""Provider resolution and default-model selection helpers.

Runtime model discovery (querying a provider's ``/models`` endpoint) lives on
:class:`agentirc.api.ResponsesClient`; this module only deals with the static
catalog supplied via configuration.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

KNOWN_PROVIDERS = ("openai", "xai", "lmstudio")


def provider_for_model(model: str, models: dict[str, list[str]]) -> str | None:
    """Resolve which provider owns *model*.

    Matches against the configured per-provider catalogs first, then falls back
    to the ``grok-`` naming heuristic for xAI. Returns ``None`` when unknown.
    """
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


def pick_default_model(models: dict[str, list[str]], preferred: str = "") -> str:
    """Select a default model from *preferred* or the first available catalog entry."""
    preferred = preferred.strip()
    if preferred:
        return preferred

    for provider in KNOWN_PROVIDERS:
        items = models.get(provider, [])
        if items:
            return items[0]
    raise RuntimeError("No models available from configured providers")
