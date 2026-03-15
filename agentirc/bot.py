"""AI-powered IRC agent that wraps the base IRCBot."""

from __future__ import annotations

import asyncio
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
        self.personality = self.default_personality
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
            max_items=24,
            store_path=store_path,
            encryption_key=encryption_key,
        )

        self._user_models: dict[str, dict[str, str]] = {}

        provider = self._provider_for_model(self.model)
        self.client = ResponsesClient(
            api_base=self._base_url(provider),
            api_key=self._api_key(provider),
            model=self.model,
            system_prompt=self._default_prompt(),
            max_tokens=config.max_tokens,
            enabled_tools=config.tools,
            provider=provider,
        )

        log.info("Using default model: %s (%s)", self.model, provider)
        self._register_commands()

    def _register_commands(self) -> None:
        """Register built-in IRC commands and AI commands."""
        register_builtins(self.bot)

        @self.bot.command("ai", help="Talk to the AI: !chat <message>", aliases=["chat", "ask"])
        async def cmd_chat(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            if not args.strip():
                await bot.reply(msg, "Usage: !chat <message>")
                return
            await self._respond(bot, msg, msg.nick, args.strip())

        @self.bot.command("x", help="Talk as another user: !x <nick> <message>")
        async def cmd_x(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            parts = args.strip().split(None, 1)
            if len(parts) < 2:
                await bot.reply(msg, "Usage: !x <nick> <message>")
                return
            target_nick, text = parts[0], parts[1].strip()
            if not text:
                await bot.reply(msg, "Usage: !x <nick> <message>")
                return
            await self._respond(bot, msg, target_nick, text)

        @self.bot.command("persona", help="Set persona and reintroduce: !persona <text>")
        async def cmd_persona(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            room, user = self._thread_key(msg, msg.nick)
            persona = args.strip() or self.default_personality
            self.history.init_prompt(room, user, persona=persona)
            self.history.add(room, user, "user", "introduce yourself")
            await self._respond(bot, msg, msg.nick)

        @self.bot.command("custom", help="Set custom system prompt: !custom <prompt>")
        async def cmd_custom(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            custom = args.strip()
            if not custom:
                await bot.reply(msg, "Usage: !custom <prompt>")
                return
            room, user = self._thread_key(msg, msg.nick)
            self.history.init_prompt(room, user, custom=custom)
            self.history.add(room, user, "user", "introduce yourself")
            await self._respond(bot, msg, msg.nick)

        @self.bot.command("reset", help="Reset your AI conversation to default settings")
        async def cmd_reset(bot: IRCBot, msg: IRCMessage, _args: str) -> None:
            room, user = self._thread_key(msg, msg.nick)
            self.history.reset(room, user, stock=False)
            await bot.reply(msg, f"{self.bot.config.nick} reset to default for {msg.nick}")

        @self.bot.command("stock", help="Reset your AI conversation with no system prompt")
        async def cmd_stock(bot: IRCBot, msg: IRCMessage, _args: str) -> None:
            room, user = self._thread_key(msg, msg.nick)
            self.history.reset(room, user, stock=True)
            await bot.reply(msg, f"Stock settings applied for {msg.nick}")

        @self.bot.command("mymodel", help="Show or set your model: !mymodel [name]")
        async def cmd_mymodel(bot: IRCBot, msg: IRCMessage, args: str) -> None:
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

        @self.bot.command("model", help="Admin: show/set global model: !model [name|reset]")
        async def cmd_model(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            if not self._is_admin(msg.nick):
                await bot.reply(msg, "Admin only.")
                return
            
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

        @self.bot.command("tools", help="Admin: !tools [on|off|toggle|status]")
        async def cmd_tools(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            if not self._is_admin(msg.nick):
                await bot.reply(msg, "Admin only.")
                return
            arg = args.strip().lower()
            if arg in ("", "status"):
                state = "enabled" if self.tools_enabled else "disabled"
                await bot.reply(msg, f"Tools are currently {state}")
                return
            if arg in ("on", "enable", "enabled"):
                self.tools_enabled = True
            elif arg in ("off", "disable", "disabled"):
                self.tools_enabled = False
            else:
                self.tools_enabled = not self.tools_enabled
            state = "enabled" if self.tools_enabled else "disabled"
            await bot.reply(msg, f"Tools are now {state}")

        @self.bot.command("verbose", help="Admin: !verbose [on|off|toggle|status]")
        async def cmd_verbose(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            if not self._is_admin(msg.nick):
                await bot.reply(msg, "Admin only.")
                return
            arg = args.strip().lower()
            if arg in ("", "status"):
                await bot.reply(msg, f"Verbose mode is {'ON' if self.verbose else 'OFF'}")
                return
            if arg in ("on", "true", "1", "enable", "enabled"):
                self.verbose = True
            elif arg in ("off", "false", "0", "disable", "disabled"):
                self.verbose = False
            elif arg in ("toggle", "switch"):
                self.verbose = not self.verbose
            else:
                await bot.reply(msg, "Usage: !verbose [on|off|toggle]")
                return
            await bot.reply(msg, f"Verbose mode set to {'ON' if self.verbose else 'OFF'}")

        @self.bot.command("clear", help="Admin: clear all conversation state")
        async def cmd_clear(bot: IRCBot, msg: IRCMessage, _args: str) -> None:
            if not self._is_admin(msg.nick):
                await bot.reply(msg, "Admin only.")
                return
            self.history.clear_all()
            self._user_models.clear()
            self.model = self.default_model
            self.personality = self.default_personality
            await bot.reply(msg, "Bot has been reset for everyone.")

        @self.bot.command("country", help="Admin: toggle search country filtering: !country [on|off|status]")
        async def cmd_country(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            if not self._is_admin(msg.nick):
                await bot.reply(msg, "Admin only.")
                return
            country = self.config.web_search_country
            if not country:
                await bot.reply(msg, "No search country configured (WEB_SEARCH_COUNTRY not set).")
                return
            arg = args.strip().lower()
            if arg in ("", "status"):
                state = "enabled" if self.search_country_enabled else "disabled"
                await bot.reply(msg, f"Search country filtering ({country}): {state}")
                return
            if arg in ("on", "enable", "enabled"):
                self.search_country_enabled = True
            elif arg in ("off", "disable", "disabled"):
                self.search_country_enabled = False
            else:
                self.search_country_enabled = not self.search_country_enabled
            state = "enabled" if self.search_country_enabled else "disabled"
            await bot.reply(msg, f"Search country filtering ({country}): {state}")

        @self.bot.command("location", help="Set your location: !location <place> | !location clear")
        async def cmd_location(bot: IRCBot, msg: IRCMessage, args: str) -> None:
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

        @self.bot.command("join", help="Admin: join a channel: !join <#channel>")
        async def cmd_join(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            if not self._is_admin(msg.nick):
                await bot.reply(msg, "Admin only.")
                return
            channel = args.strip()
            if not channel:
                await bot.reply(msg, "Usage: !join <#channel>")
                return
            if not channel.startswith(("#", "&", "!", "+")):
                channel = f"#{channel}"
            await bot.join(channel)
            await bot.reply(msg, f"Joined {channel}")

        @self.bot.command("part", help="Admin: leave a channel: !part [#channel] [reason]")
        async def cmd_part(bot: IRCBot, msg: IRCMessage, args: str) -> None:
            if not self._is_admin(msg.nick):
                await bot.reply(msg, "Admin only.")
                return
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
        if provider == "xai":
            return "xAI"
        if provider == "openai":
            return "OpenAI"
        if provider == "lmstudio":
            return "LM Studio"
        return provider

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

    def _default_prompt(self) -> str:
        if self.config.default_system_prompt:
            return self.config.default_system_prompt
        extra = "" if self.verbose else self.config.prompt_suffix_extra
        return (
            f"{self.config.prompt_prefix}"
            f"{self.personality}"
            f"{self.config.prompt_suffix}"
            f"{extra}"
        ).strip()

    @staticmethod
    def _clean_response_text(text: str) -> str:
        cleaned = text or ""
        if "</think>" in cleaned and "<think>" in cleaned:
            try:
                cleaned = cleaned.split("</think>", 1)[1]
            except Exception:
                pass
        if "<|begin_of_solution|>" in cleaned and "<|end_of_solution|>" in cleaned:
            try:
                cleaned = cleaned.split("<|begin_of_solution|>", 1)[1].split(
                    "<|end_of_solution|>",
                    1,
                )[0]
            except Exception:
                pass
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
        tools = build_tools(tool_names, provider, web_search_country=country)
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
        self.history.add(room, user, "assistant", cleaned)
        for line in cleaned.splitlines():
            if line.strip():
                await bot.reply(msg, line)

    async def run(self) -> None:
        """Start the agent."""
        await self._refresh_models()
        await self.bot.run()
