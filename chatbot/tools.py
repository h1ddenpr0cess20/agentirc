"""Tool definitions for OpenAI-compatible Responses APIs."""

from __future__ import annotations

from typing import Any

XAI_HOSTED_TOOL_TYPES = {"web_search", "x_search", "code_interpreter", "mcp"}


def build_tools(enabled: list[str], provider: str = "openai") -> list[dict[str, Any]]:
    """Build the tools list for the Responses API request.

    Supported tools:
        - web_search (openai, xai)
        - x_search (xai)
        - code_interpreter (openai, xai)
    """
    tool_builders: dict[str, tuple[set[str], Any]] = {
        "web_search": ({"openai", "xai"}, _web_search_tool),
        "x_search": ({"xai"}, _x_search_tool),
        "code_interpreter": ({"openai", "xai"}, _code_interpreter_tool),
    }

    tools = []
    for name in enabled:
        spec = tool_builders.get(name)
        if not spec:
            continue
        providers, builder = spec
        if provider in providers:
            tools.append(builder(provider))
    return tools


def _web_search_tool(_provider: str) -> dict[str, Any]:
    return {"type": "web_search"}


def _x_search_tool(_provider: str) -> dict[str, Any]:
    return {"type": "x_search"}


def _code_interpreter_tool(provider: str) -> dict[str, Any]:
    tool = {"type": "code_interpreter"}
    if provider == "openai":
        tool["container"] = {"type": "auto"}
    return tool


def xai_model_supports_hosted_tools(model: str) -> bool:
    lowered = str(model or "").strip().lower()
    return lowered.startswith("grok-4")


def tools_for_model(enabled: list[str], provider: str, model: str) -> list[str]:
    if provider != "xai":
        return list(enabled)
    if xai_model_supports_hosted_tools(model):
        return list(enabled)
    return [name for name in enabled if name not in XAI_HOSTED_TOOL_TYPES]
