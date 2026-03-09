# Extending the Bot

## TL;DR

Subclass `IRCBot` and override any of the `on_*` methods. For IRC commands not handled by the named hooks, define `on_raw_<command>(self, msg)` and it will be called automatically.

## Subclassing IRCBot

`IRCBot` is designed to be subclassed. All event hooks are regular async methods with no-op or minimal default behavior. Override only what you need.

```python
import asyncio
from ircbot import IRCBot, BotConfig, load_env
from ircbot.commands import register_builtins
from ircbot.protocol import IRCMessage

class MyBot(IRCBot):
    async def on_welcome(self, msg: IRCMessage) -> None:
        # Always call super() unless you want to skip auto-join
        await super().on_welcome(msg)
        await self.privmsg("NickServ", f"IDENTIFY {self.config.password}")

    async def on_join(self, msg: IRCMessage) -> None:
        await super().on_join(msg)
        if msg.nick != self.nick:
            await self.privmsg(msg.target, f"Welcome, {msg.nick}!")

load_env()
bot = MyBot(BotConfig.from_env())
register_builtins(bot)
asyncio.run(bot.run())
```

## Named event hooks

These methods are called by the internal dispatcher. Override any of them in a subclass.

### `on_welcome(self, msg: IRCMessage)`

Called when the server sends numeric `001` (RPL_WELCOME), which signals that registration is complete. The default implementation joins all channels listed in `config.channels`.

```python
async def on_welcome(self, msg: IRCMessage) -> None:
    await super().on_welcome(msg)
    # Custom post-connect logic here
```

### `on_privmsg(self, msg: IRCMessage)`

Called on every `PRIVMSG`. The default implementation calls `_try_command` to check for a command prefix; only resolved commands are logged at info level.

If you override this without calling `super()`, command dispatch stops working.

```python
async def on_privmsg(self, msg: IRCMessage) -> None:
    # Intercept all messages before command dispatch
    if "badword" in msg.text.lower():
        await self.privmsg(msg.target, f"{msg.nick}: watch your language.")
        return  # suppress command dispatch for this message
    await super().on_privmsg(msg)
```

### `on_join(self, msg: IRCMessage)`

Called when any user (including the bot) joins a channel. `msg.nick` is the joiner, `msg.target` is the channel. The default logs the event.

### `on_part(self, msg: IRCMessage)`

Called when any user parts a channel. `msg.target` is the channel. If the user supplied a part message, it is in `msg.text`. The default logs the event.

### `on_kick(self, msg: IRCMessage)`

Called when a user is kicked. `msg.params[1]` is the kicked nick. `msg.target` is the channel. The default logs the event and, if the bot itself was kicked, waits 5 seconds and rejoins.

```python
async def on_kick(self, msg: IRCMessage) -> None:
    await super().on_kick(msg)  # handles auto-rejoin
    # Additional logic, e.g. log to a database
```

## The on_raw_* pattern

After the named hooks run, the dispatcher checks for a method named `on_raw_<command>` where `<command>` is the lowercased IRC command or numeric. This lets you handle any IRC message type without modifying the dispatcher.

```python
class MyBot(IRCBot):
    async def on_raw_notice(self, msg: IRCMessage) -> None:
        """Handle NOTICE messages."""
        print(f"NOTICE from {msg.nick}: {msg.text}")

    async def on_raw_332(self, msg: IRCMessage) -> None:
        """332 is RPL_TOPIC -- sent when joining a channel."""
        channel = msg.params[1] if len(msg.params) > 1 else msg.target
        topic = msg.text
        print(f"Topic for {channel}: {topic}")

    async def on_raw_mode(self, msg: IRCMessage) -> None:
        """Handle MODE changes."""
        print(f"MODE change on {msg.target}: {msg.text}")
```

Named hooks and `on_raw_*` are not mutually exclusive. The dispatcher calls the named hook first (e.g. `on_privmsg`), then checks for `on_raw_privmsg`. Both will fire if both are defined.

## Sending raw IRC lines

Use `await self.send(line)` for anything not covered by the convenience helpers:

```python
# Convenience helpers
await self.privmsg("#channel", "Hello")
await self.notice("user", "This is a notice")
await self.join("#channel")
await self.part("#channel", "Goodbye")
await self.quit("Shutting down")

# Reply to whoever sent a message (channel or DM)
await self.reply(msg, "Got it")

# Raw line for anything else
await self.send("MODE #channel +b *!*@spammer.example.com")
await self.send("WHOIS somenick")
```

## Keeping state

Add instance variables in `__init__`, calling `super().__init__()` first:

```python
class StatefulBot(IRCBot):
    def __init__(self, config):
        super().__init__(config)
        self.seen: dict[str, str] = {}  # nick -> last message

    async def on_privmsg(self, msg):
        self.seen[msg.nick] = msg.text
        await super().on_privmsg(msg)
```

## Running without subclassing

You do not need to subclass `IRCBot` for simple bots. Register commands on a plain instance and run it:

```python
load_env()
bot = IRCBot(BotConfig.from_env())
register_builtins(bot)

@bot.command("echo", help="Repeat your message back")
async def echo(bot, msg, args):
    await bot.reply(msg, args)

asyncio.run(bot.run())
```

Subclassing is most useful when you need to intercept events (joins, parts, raw numerics) or maintain persistent state across the bot's lifetime.
