"""Tool definitions for Responses APIs."""

from __future__ import annotations

from typing import Any

XAI_HOSTED_TOOL_TYPES = {"web_search", "x_search", "code_interpreter", "mcp"}


def build_tools(
    enabled: list[str],
    provider: str = "xai",
    *,
    web_search_country: str = "",
) -> list[dict[str, Any]]:
    """Build the tools list for the Responses API request.

    Supported tools:
        - web_search (xai)
        - x_search (xai)
        - code_interpreter (xai)
    """
    tool_builders: dict[str, tuple[set[str], Any]] = {
        "web_search": ({"xai"}, _web_search_tool),
        "x_search": ({"xai"}, _x_search_tool),
        "code_interpreter": ({"xai"}, _code_interpreter_tool),
    }

    tools = []
    for name in enabled:
        spec = tool_builders.get(name)
        if not spec:
            continue
        providers, builder = spec
        if provider in providers:
            if name == "web_search":
                tools.append(builder(provider, country=web_search_country))
            else:
                tools.append(builder(provider))
    return tools


def _web_search_tool(_provider: str, *, country: str = "") -> dict[str, Any]:
    tool: dict[str, Any] = {"type": "web_search"}
    if country:
        tool["user_location"] = {"type": "approximate", "country": country}
    return tool


def strip_search_country(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove user_location from web_search tool dicts."""
    result = []
    for tool in tools:
        if isinstance(tool, dict) and tool.get("type") == "web_search" and "user_location" in tool:
            tool = {k: v for k, v in tool.items() if k != "user_location"}
        result.append(tool)
    return result


def _x_search_tool(_provider: str) -> dict[str, Any]:
    return {"type": "x_search"}


def _code_interpreter_tool(_provider: str) -> dict[str, Any]:
    return {"type": "code_interpreter"}


def xai_model_supports_hosted_tools(model: str) -> bool:
    lowered = str(model or "").strip().lower()
    return lowered.startswith("grok-4")


def tools_for_model(enabled: list[str], provider: str, model: str) -> list[str]:
    if provider != "xai":
        return list(enabled)
    if xai_model_supports_hosted_tools(model):
        return list(enabled)
    return [name for name in enabled if name not in XAI_HOSTED_TOOL_TYPES]
