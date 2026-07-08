"""AI-powered IRC agent that wraps the base IRCBot."""

from __future__ import annotations

import asyncio
import functools
import logging

from ircbot import IRCBot, IRCMessage, register_builtins
from .api import ResponsesClient
from .config import ChatConfig
from .history import HistoryStore
from .models import (
    KNOWN_PROVIDERS,
    pick_default_model,
    provider_for_model,
)
from .tools import build_tools, tools_for_model

log = logging.getLogger(__name__)

_HISTORY_MAX_ITEMS = 24
_REPLY_LINE_DELAY = 0.5

_PROVIDER_LABELS = {
    "xai": "xAI",
    "openai": "OpenAI",
    "lmstudio": "LM Studio",
}

_TOGGLE_ON = {"on", "true", "1", "enable", "enabled"}
_TOGGLE_OFF = {"off", "false", "0", "disable", "disabled"}
_TOGGLE_FLIP = {"toggle", "switch"}


def _parse_toggle(arg: str, current: bool) -> bool | None:
    """Resolve an on/off/toggle argument against the current state.

    Returns the new state, or ``None`` when the argument is not recognized.
    """
    if arg in _TOGGLE_ON:
        return True
    if arg in _TOGGLE_OFF:
        return False
    if arg in _TOGGLE_FLIP:
        return not current
    return None


def admin_only(fn):
    """Guard a ChatBot command method so only configured admins can run it."""

    @functools.wraps(fn)
    async def wrapper(self: ChatBot, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        if not self._is_admin(msg.nick):
            await bot.reply(msg, "Admin only.")
            return
        await fn(self, bot, msg, args)

    return wrapper


class ChatBot:
    """Wrap IRCBot with multi-provider AI chat capabilities."""

    def __init__(self, config: ChatConfig) -> None:
        self.config = config
        self.bot = IRCBot(config.irc)

        self.models = {
            provider: list(config.models.get(provider, []))
            for provider in KNOWN_PROVIDERS
        }
        self.default_model = pick_default_model(self.models, config.default_model)
        self.model = self.default_model
        self.default_personality = config.default_personality
        self.tools_enabled = True
        self.verbose = False
        self.search_country_enabled = bool(config.web_search_country)

        store_path = None
        encryption_key = None
        if config.history_encryption_key:
            store_path = "."
            encryption_key = config.history_encryption_key

        self.history = HistoryStore(
            prompt_prefix=config.prompt_prefix,
            prompt_suffix=config.prompt_suffix,
            personality=config.default_personality,
            prompt_suffix_extra=config.prompt_suffix_extra,
            max_items=_HISTORY_MAX_ITEMS,
            system_prompt=config.default_system_prompt or None,
            store_path=store_path,
            encryption_key=encryption_key,
        )

        self._user_models: dict[str, dict[str, str]] = {}

        provider = self._provider_for_model(self.model)
        self.client = ResponsesClient(
            api_base=self._base_url(provider),
            api_key=self._api_key(provider),
            model=self.model,
            enabled_tools=config.tools,
            provider=provider,
        )

        log.info("Using default model: %s (%s)", self.model, provider)
        self._register_commands()

    def _register_commands(self) -> None:
        """Register built-in IRC commands and AI commands."""
        register_builtins(self.bot)
        command = self.bot.command
        command("ai", help="Talk to the AI: !chat <message>", aliases=["chat", "ask"])(self._cmd_chat)
        command("x", help="Talk as another user: !x <nick> <message>")(self._cmd_x)
        command("persona", help="Set persona and reintroduce: !persona <text>")(self._cmd_persona)
        command("custom", help="Set custom system prompt: !custom <prompt>")(self._cmd_custom)
        command("reset", help="Reset your AI conversation to default settings")(self._cmd_reset)
        command("stock", help="Reset your AI conversation with no system prompt")(self._cmd_stock)
        command("mymodel", help="Show or set your model: !mymodel [name]")(self._cmd_mymodel)
        command("model", help="Admin: show/set global model: !model [name|reset]")(self._cmd_model)
        command("tools", help="Admin: !tools [on|off|toggle|status]")(self._cmd_tools)
        command("verbose", help="Admin: !verbose [on|off|toggle|status]")(self._cmd_verbose)
        command("clear", help="Admin: clear all conversation state")(self._cmd_clear)
        command("country", help="Admin: toggle search country filtering: !country [on|off|status]")(self._cmd_country)
        command("location", help="Set your location: !location <place> | !location clear")(self._cmd_location)
        command("join", help="Admin: join a channel: !join <#channel>")(self._cmd_join)
        command("part", help="Admin: leave a channel: !part [#channel] [reason]")(self._cmd_part)

    async def _cmd_chat(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        if not args.strip():
            await bot.reply(msg, "Usage: !chat <message>")
            return
        await self._respond(bot, msg, msg.nick, args.strip())

    async def _cmd_x(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        parts = args.strip().split(None, 1)
        if len(parts) < 2:
            await bot.reply(msg, "Usage: !x <nick> <message>")
            return
        target_nick, text = parts[0], parts[1].strip()
        if not text:
            await bot.reply(msg, "Usage: !x <nick> <message>")
            return
        await self._respond(bot, msg, target_nick, text)

    async def _cmd_persona(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        room, user = self._thread_key(msg, msg.nick)
        persona = args.strip() or self.default_personality
        self.history.init_prompt(room, user, persona=persona)
        self.history.add(room, user, "user", "introduce yourself")
        await self._respond(bot, msg, msg.nick)

    async def _cmd_custom(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        custom = args.strip()
        if not custom:
            await bot.reply(msg, "Usage: !custom <prompt>")
            return
        room, user = self._thread_key(msg, msg.nick)
        self.history.init_prompt(room, user, custom=custom)
        self.history.add(room, user, "user", "introduce yourself")
        await self._respond(bot, msg, msg.nick)

    async def _cmd_reset(self, bot: IRCBot, msg: IRCMessage, _args: str) -> None:
        room, user = self._thread_key(msg, msg.nick)
        self.history.reset(room, user, stock=False)
        await bot.reply(msg, f"{self.bot.config.nick} reset to default for {msg.nick}")

    async def _cmd_stock(self, bot: IRCBot, msg: IRCMessage, _args: str) -> None:
        room, user = self._thread_key(msg, msg.nick)
        self.history.reset(room, user, stock=True)
        await bot.reply(msg, f"Stock settings applied for {msg.nick}")

    async def _cmd_mymodel(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        await self._refresh_models()
        room, user = self._thread_key(msg, msg.nick)
        requested = args.strip()
        if not requested:
            current = self._user_models.get(room, {}).get(user, self.model)
            await bot.reply(msg, f"Your current model: {current}")
            await bot.reply(msg, f"Available models: {', '.join(self._all_models())}")
            return
        if not self._is_valid_model(requested):
            await bot.reply(msg, f"Model '{requested}' not found. Available: {', '.join(self._all_models())}")
            return
        self._user_models.setdefault(room, {})[user] = requested
        await bot.reply(msg, f"Model for {msg.nick} set to {requested}")

    @admin_only
    async def _cmd_model(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        requested = args.strip()
        if not requested:
            await self._refresh_models()
            await bot.reply(msg, f"Current model: {self.model}")
            for line in self._models_by_provider_lines():
                await bot.reply(msg, line)
            return
        if requested.lower() == "reset":
            self.model = self.default_model
            await bot.reply(msg, f"Model set to {self.model}")
            return
        if self._is_valid_model(requested):
            self.model = requested
            await bot.reply(msg, f"Model set to {self.model}")
            return
        await bot.reply(msg, f"Model '{requested}' not found.")

    @admin_only
    async def _cmd_tools(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        arg = args.strip().lower()
        if arg in ("", "status"):
            state = "enabled" if self.tools_enabled else "disabled"
            await bot.reply(msg, f"Tools are currently {state}")
            return
        new_state = _parse_toggle(arg, self.tools_enabled)
        if new_state is None:
            await bot.reply(msg, "Usage: !tools [on|off|toggle|status]")
            return
        self.tools_enabled = new_state
        state = "enabled" if self.tools_enabled else "disabled"
        await bot.reply(msg, f"Tools are now {state}")

    @admin_only
    async def _cmd_verbose(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        arg = args.strip().lower()
        if arg in ("", "status"):
            await bot.reply(msg, f"Verbose mode is {'ON' if self.verbose else 'OFF'}")
            return
        new_state = _parse_toggle(arg, self.verbose)
        if new_state is None:
            await bot.reply(msg, "Usage: !verbose [on|off|toggle]")
            return
        self.verbose = new_state
        self.history.set_verbose(self.verbose)
        await bot.reply(msg, f"Verbose mode set to {'ON' if self.verbose else 'OFF'}")

    @admin_only
    async def _cmd_clear(self, bot: IRCBot, msg: IRCMessage, _args: str) -> None:
        self.history.clear_all()
        self._user_models.clear()
        self.model = self.default_model
        await bot.reply(msg, "Bot has been reset for everyone.")

    @admin_only
    async def _cmd_country(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        country = self.config.web_search_country
        if not country:
            await bot.reply(msg, "No search country configured (WEB_SEARCH_COUNTRY not set).")
            return
        arg = args.strip().lower()
        if arg in ("", "status"):
            state = "enabled" if self.search_country_enabled else "disabled"
            await bot.reply(msg, f"Search country filtering ({country}): {state}")
            return
        new_state = _parse_toggle(arg, self.search_country_enabled)
        if new_state is None:
            await bot.reply(msg, "Usage: !country [on|off|toggle|status]")
            return
        self.search_country_enabled = new_state
        state = "enabled" if self.search_country_enabled else "disabled"
        await bot.reply(msg, f"Search country filtering ({country}): {state}")

    async def _cmd_location(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        _room, user = self._thread_key(msg, msg.nick)
        arg = args.strip()
        if not arg:
            loc = self.history.get_location(user)
            if loc:
                await bot.reply(msg, f"Your location: {loc}")
            else:
                await bot.reply(msg, "No location set. Usage: !location <place>")
            return
        if arg.lower() in ("clear", "remove", "reset", "none"):
            self.history.set_location(user, "")
            await bot.reply(msg, "Location cleared.")
            return
        self.history.set_location(user, arg)
        await bot.reply(msg, f"Location set to: {arg}")

    @admin_only
    async def _cmd_join(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        channel = args.strip()
        if not channel:
            await bot.reply(msg, "Usage: !join <#channel>")
            return
        if not channel.startswith(("#", "&", "!", "+")):
            channel = f"#{channel}"
        await bot.join(channel)
        await bot.reply(msg, f"Joined {channel}")

    @admin_only
    async def _cmd_part(self, bot: IRCBot, msg: IRCMessage, args: str) -> None:
        parts = args.strip().split(None, 1)
        if parts and parts[0].startswith(("#", "&", "!", "+")):
            channel = parts[0]
            reason = parts[1] if len(parts) > 1 else ""
        elif msg.is_channel:
            channel = msg.target
            reason = args.strip()
        else:
            await bot.reply(msg, "Usage: !part <#channel> [reason]")
            return
        await bot.part(channel, reason)

    def _thread_key(self, msg: IRCMessage, user_nick: str) -> tuple[str, str]:
        room = msg.target.lower() if msg.is_channel else "__dm__"
        return (room, user_nick.lower())

    def _provider_for_model(self, model: str) -> str:
        provider = provider_for_model(model, self.models)
        if provider:
            return provider
        configured = [p for p in KNOWN_PROVIDERS if self._base_url(p)]
        if len(configured) == 1:
            return configured[0]
        return "openai"

    def _base_url(self, provider: str) -> str:
        return str(self.config.base_urls.get(provider, "") or "").strip()

    def _api_key(self, provider: str) -> str:
        return str(self.config.api_keys.get(provider, "") or "").strip()

    def _is_admin(self, nick: str) -> bool:
        return nick.lower() in set(self.config.admins)

    def _all_models(self) -> list[str]:
        values: list[str] = []
        seen = set()
        for provider in KNOWN_PROVIDERS:
            for model in self.models.get(provider, []):
                if model not in seen:
                    values.append(model)
                    seen.add(model)
        return values

    def _is_valid_model(self, model: str) -> bool:
        return model in set(self._all_models())

    @staticmethod
    def _provider_label(provider: str) -> str:
        return _PROVIDER_LABELS.get(provider, provider)

    def _models_by_provider_lines(self) -> list[str]:
        lines: list[str] = []
        for provider in KNOWN_PROVIDERS:
            items = self.models.get(provider, [])
            if not items:
                continue
            lines.append(f"{self._provider_label(provider)}: {', '.join(items)}")
        return lines or ["No models available."]

    async def _refresh_models(self) -> None:
        if not self.config.server_models:
            return
        merged = dict(self.models)
        for provider in KNOWN_PROVIDERS:
            api_base = self._base_url(provider)
            api_key = self._api_key(provider)
            if provider == "lmstudio":
                if not api_base:
                    continue
            elif not api_key:
                continue
            try:
                fetched = await self.client.list_models(
                    provider,
                    api_base=api_base,
                    api_key=api_key,
                )
            except Exception:
                log.exception("Failed to refresh model list from %s", provider)
                continue
            if not fetched:
                continue
            configured = list(self.models.get(provider, []))
            merged[provider] = sorted(dict.fromkeys([*fetched, *configured]))
        self.models = merged

    @staticmethod
    def _clean_response_text(text: str) -> str:
        cleaned = text or ""
        if "<think>" in cleaned and "</think>" in cleaned:
            cleaned = cleaned.split("</think>", 1)[1]
        if "<|begin_of_solution|>" in cleaned and "<|end_of_solution|>" in cleaned:
            cleaned = cleaned.split("<|begin_of_solution|>", 1)[1].split(
                "<|end_of_solution|>",
                1,
            )[0]
        return cleaned.strip()

    async def _respond(self, bot: IRCBot, msg: IRCMessage, user_nick: str, text: str | None = None) -> None:
        room, user = self._thread_key(msg, user_nick)
        if text:
            self.history.add(room, user, "user", text)
        messages = self.history.get(room, user)
        model = self._user_models.get(room, {}).get(user, self.model)
        provider = self._provider_for_model(model)
        api_base = self._base_url(provider)
        if not api_base:
            await bot.reply(msg, f"No API base configured for provider '{provider}'.")
            return

        tool_names = tools_for_model(self.config.tools, provider, model) if self.tools_enabled else []
        country = self.config.web_search_country if self.search_country_enabled else ""
        tools = build_tools(tool_names, provider, web_search_country=country, mcp_servers=self.config.mcp_servers)
        try:
            reply, _response_id = await self.client.ask_messages(
                messages,
                model=model,
                provider=provider,
                api_base=api_base,
                api_key=self._api_key(provider),
                built_tools=tools,
                max_tokens=self.config.max_tokens,
            )
        except Exception:
            log.exception("AI request failed")
            await bot.reply(msg, "AI request failed.")
            return

        cleaned = self._clean_response_text(reply)
        if not cleaned:
            await bot.reply(msg, "(no response)")
            return
        self.history.add(room, user, "assistant", cleaned)
        for line in cleaned.splitlines():
            if line.strip():
                await bot.reply(msg, line)
                await asyncio.sleep(_REPLY_LINE_DELAY)

    async def run(self) -> None:
        """Start the agent."""
        await self._refresh_models()
        await self.bot.run()
