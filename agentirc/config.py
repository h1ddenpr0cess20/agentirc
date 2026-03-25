"""Configuration for the AI agent layer."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ircbot.config import BotConfig, load_env

_DEFAULT_PERSONALITY = "a helpful IRC chatbot"
_DEFAULT_PROMPT_PREFIX = "You are "
_DEFAULT_PROMPT_SUFFIX = "."
_DEFAULT_PROMPT_SUFFIX_EXTRA = " Keep responses concise (under 400 chars) since this is IRC."


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ChatConfig:
    """AI agent configuration."""

    irc: BotConfig
    models: dict[str, list[str]]
    api_keys: dict[str, str]
    base_urls: dict[str, str]
    default_model: str
    default_personality: str = _DEFAULT_PERSONALITY
    prompt_prefix: str = _DEFAULT_PROMPT_PREFIX
    prompt_suffix: str = _DEFAULT_PROMPT_SUFFIX
    prompt_suffix_extra: str = _DEFAULT_PROMPT_SUFFIX_EXTRA
    default_system_prompt: str = ""
    max_tokens: int = 300
    tools: list[str] = field(default_factory=lambda: ["web_search", "x_search", "code_interpreter"])
    admins: list[str] = field(default_factory=list)
    server_models: bool = True
    web_search_country: str = ""
    history_encryption_key: str = ""

    def make_default_prompt(self, *, verbose: bool = False) -> str:
        """Build the default system prompt for a new conversation."""
        if self.default_system_prompt:
            return self.default_system_prompt.strip()
        extra = "" if verbose else self.prompt_suffix_extra
        return f"{self.prompt_prefix}{self.default_personality}{self.prompt_suffix}{extra}".strip()

    @classmethod
    def from_env(cls) -> ChatConfig:
        """Build config from environment variables."""
        load_env()
        xai_models = _parse_csv(os.environ.get("XAI_MODELS"))
        lmstudio_models = _parse_csv(os.environ.get("LMSTUDIO_MODELS"))

        default_model = os.environ.get("DEFAULT_MODEL", "").strip()
        if not default_model:
            default_model = (
                (xai_models[0] if xai_models else "")
                or (lmstudio_models[0] if lmstudio_models else "")
            )

        return cls(
            irc=BotConfig.from_env(),
            models={
                "xai": xai_models,
                "lmstudio": lmstudio_models,
            },
            api_keys={
                "xai": os.environ.get("XAI_API_KEY", "").strip(),
                "lmstudio": os.environ.get("LMSTUDIO_API_KEY", "").strip(),
            },
            base_urls={
                "xai": os.environ.get("XAI_API_BASE", "https://api.x.ai/v1").strip(),
                "lmstudio": os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1").strip(),
            },
            default_model=default_model,
            default_personality=os.environ.get(
                "AGENTIRC_DEFAULT_PERSONALITY",
                os.environ.get("AGENTIRC_PERSONALITY", _DEFAULT_PERSONALITY),
            ).strip()
            or _DEFAULT_PERSONALITY,
            prompt_prefix=os.environ.get("AGENTIRC_PROMPT_PREFIX", _DEFAULT_PROMPT_PREFIX),
            prompt_suffix=os.environ.get("AGENTIRC_PROMPT_SUFFIX", _DEFAULT_PROMPT_SUFFIX),
            prompt_suffix_extra=os.environ.get("AGENTIRC_PROMPT_SUFFIX_EXTRA", _DEFAULT_PROMPT_SUFFIX_EXTRA),
            default_system_prompt=os.environ.get("AGENTIRC_SYSTEM_PROMPT", "").strip(),
            max_tokens=int(os.environ.get("AGENTIRC_MAX_TOKENS", "300")),
            tools=[
                t.strip()
                for t in os.environ.get("AGENTIRC_TOOLS", "web_search,x_search,code_interpreter").split(",")
                if t.strip()
            ],
            admins=[nick.lower() for nick in _parse_csv(os.environ.get("AGENTIRC_ADMINS"))],
            server_models=_parse_bool(os.environ.get("AGENTIRC_SERVER_MODELS"), True),
            web_search_country=os.environ.get("WEB_SEARCH_COUNTRY", "").strip(),
            history_encryption_key=os.environ.get("HISTORY_ENCRYPTION_KEY", "").strip(),
        )
