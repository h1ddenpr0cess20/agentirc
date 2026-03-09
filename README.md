# ircbot

A minimal async IRC bot framework written in pure Python stdlib. No dependencies.

## Table of Contents

- [Quick Start](#quick-start)
- [Built-in Commands](#built-in-commands)
- [Adding a Command](#adding-a-command)
- [Subclassing the Bot](#subclassing-the-bot)
- [Documentation](#documentation)
- [License](#license)

## Quick Start

```bash
git clone https://github.com/youruser/ircbot.git
cd ircbot
cp .env.example .env
# Edit .env with your server, nick, and channels
python -m ircbot
```

Pass `--debug` to log every raw IRC line to stderr.

> **Requirements:** Python 3.10 or later. No third-party packages needed.

## Built-in Commands

| Command       | Aliases | Description                        |
|---------------|---------|------------------------------------|
| `!ping`       |         | Bot replies with `pong!`           |
| `!time`       |         | Bot replies with the current UTC time |
| `!help`       | `!h`    | Lists all commands                 |
| `!help <cmd>` | `!h`    | Shows help text for one command    |

The command prefix defaults to `!` and is configurable via `IRC_CMD_PREFIX`.

## Adding a Command

Register a command on a bot instance with the `@bot.command` decorator:

```python
from ircbot import IRCBot, BotConfig, load_env
from ircbot.commands import register_builtins

load_env()
config = BotConfig.from_env()
bot = IRCBot(config)
register_builtins(bot)

@bot.command("greet", help="Say hello to someone", aliases=["hi"])
async def greet(bot, msg, args):
    name = args.strip() or msg.nick
    await bot.reply(msg, f"Hello, {name}!")

import asyncio
asyncio.run(bot.run())
```

The handler signature is always `async def handler(bot: IRCBot, msg: IRCMessage, args: str) -> None`. `args` is the text after the command name, stripped.

## Subclassing the Bot

Override event hooks to react to IRC events beyond commands:

```python
from ircbot import IRCBot, BotConfig, load_env
from ircbot.protocol import IRCMessage

class MyBot(IRCBot):
    async def on_join(self, msg: IRCMessage) -> None:
        if msg.nick != self.nick:
            await self.privmsg(msg.target, f"Welcome, {msg.nick}!")

load_env()
asyncio.run(MyBot(BotConfig.from_env()).run())
```

See [docs/extending.md](docs/extending.md) for all available hooks and the `on_raw_*` pattern.

## Documentation

Full documentation lives in the [docs/](docs/) folder:

- [docs/configuration.md](docs/configuration.md) — all environment variables, types, and defaults
- [docs/commands.md](docs/commands.md) — command registry, decorator API, aliases, help text
- [docs/extending.md](docs/extending.md) — subclassing IRCBot, event hooks, on_raw_* pattern

## License

MIT
