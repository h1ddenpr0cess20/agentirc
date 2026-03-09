# Commands

## TL;DR

Register a command with `@bot.command("name", help="...", aliases=[...])`. The handler is `async def fn(bot, msg, args)`. Call `register_builtins(bot)` to include the built-in `ping`, `time`, and `help` commands.

## How command dispatch works

When the bot receives a PRIVMSG, `on_privmsg` calls `_try_command`, which:

1. Checks whether the message text starts with `config.command_prefix` (default `!`).
2. Splits off the command name and passes the remainder as `args`.
3. Looks up the command by name, then by alias.
4. Calls the handler. If the handler raises, the bot logs the exception and sends an error reply.

Commands work in both channels and private messages. The reply goes back to wherever the message came from (`msg.reply_target`).

## Registering a command

Use `bot.command()` as a decorator:

```python
@bot.command("greet", help="Say hello", aliases=["hi", "hey"])
async def greet(bot, msg, args):
    name = args.strip() or msg.nick
    await bot.reply(msg, f"Hello, {name}!")
```

Or call it directly without decorating a function defined elsewhere:

```python
bot.command("greet", help="Say hello", aliases=["hi"])(greet_handler)
```

This is how `register_builtins` works internally.

## Handler signature

Every command handler must match this signature:

```python
async def handler(bot: IRCBot, msg: IRCMessage, args: str) -> None:
    ...
```

| Parameter | Type        | Description |
|-----------|-------------|-------------|
| `bot`     | `IRCBot`    | The bot instance. Use it to call `bot.reply`, `bot.privmsg`, `bot.send`, etc. |
| `msg`     | `IRCMessage`| The parsed PRIVMSG that triggered the command. See below for useful attributes. |
| `args`    | `str`       | The text after the command name, stripped of leading/trailing whitespace. Empty string if nothing followed. |

Useful `IRCMessage` attributes inside a handler:

| Attribute      | Description |
|----------------|-------------|
| `msg.nick`     | Nick of the user who sent the command |
| `msg.text`     | Full text of the PRIVMSG (includes the prefix and command name) |
| `msg.target`   | Channel name or the bot's nick (for DMs) |
| `msg.reply_target` | Where to send a reply: channel if public, nick if DM |
| `msg.is_channel` | `True` if the message was sent in a channel |

## Aliases

Pass `aliases` as a list of strings. Aliases are resolved to the canonical command name before lookup, so `bot.get_command("hi")` returns the same `Command` object as `bot.get_command("greet")`.

```python
@bot.command("help", help="List commands", aliases=["h"])
async def cmd_help(bot, msg, args):
    ...
```

Both `!help` and `!h` will invoke this handler.

## Help text

The `help` keyword argument is a plain string shown by the built-in `!help <command>` command. Keep it to one sentence.

```python
@bot.command("roll", help="Roll an N-sided die. Usage: !roll <sides>")
async def roll(bot, msg, args):
    ...
```

If `help` is omitted, `!help <command>` displays `No description.`

## Built-in commands

`register_builtins(bot)` registers these three commands:

| Command     | Aliases | Handler        | Description |
|-------------|---------|----------------|-------------|
| `ping`      | —       | `cmd_ping`     | Replies with `<nick>: pong!` |
| `time`      | —       | `cmd_time`     | Replies with the current UTC timestamp |
| `help`      | `h`     | `cmd_help`     | Lists all commands, or shows help for one |

You can override any of them by registering a new command with the same name after calling `register_builtins`. The later registration replaces the earlier one.

## Inspecting registered commands

```python
# All commands (canonical names only)
bot.commands  # dict[str, Command]

# Look up by name or alias
cmd = bot.get_command("h")   # returns the 'help' Command
cmd.name      # "help"
cmd.aliases   # ["h"]
cmd.help      # "List commands or get help for one"
cmd.handler   # the async function
```

## Organizing commands in a separate module

For larger bots, define handlers in a separate file and register them all at once:

```python
# mybot/extra_commands.py
from ircbot import IRCBot

def register(bot: IRCBot) -> None:
    @bot.command("roll", help="Roll a die. Usage: !roll <sides>")
    async def roll(bot, msg, args):
        import random
        try:
            sides = int(args)
        except ValueError:
            await bot.reply(msg, "Usage: !roll <number>")
            return
        await bot.reply(msg, str(random.randint(1, sides)))
```

```python
# main.py
from ircbot import IRCBot, BotConfig, load_env
from ircbot.commands import register_builtins
from mybot import extra_commands

load_env()
bot = IRCBot(BotConfig.from_env())
register_builtins(bot)
extra_commands.register(bot)

import asyncio
asyncio.run(bot.run())
```
