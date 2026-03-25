# agentirc

An AI-powered IRC agent built on a minimal async IRC bot framework. Supports multiple LLM providers (xAI, LM Studio) with per-user conversation history, tool use, and encrypted persistence.

## Table of Contents

- [Quick Start](#quick-start)
- [CLI Options](#cli-options)
- [Commands](#commands)
- [Documentation](#documentation)
- [License](#license)

## Quick Start

```bash
git clone <repo-url>
cd agentirc
cp .env.example .env
# Edit .env with your IRC server, nick, and at least one API provider
pip install .
agentirc
```

Or with Docker:

```bash
cp .env.example .env
# Edit .env
docker compose up -d
```

> **Requirements:** Python 3.10+, `httpx`, and optionally `cryptography` for encrypted history persistence.

## CLI Options

```
agentirc [options]
```

| Flag | Description |
|---|---|
| `--env-file PATH` | Path to .env file (default: `.env`) |
| `--debug` | Enable debug logging |
| `--host HOST` | IRC server hostname (overrides `IRC_HOST`) |
| `--port PORT` | IRC server port (overrides `IRC_PORT`) |
| `--nick NICK` | Bot nickname (overrides `IRC_NICK`) |
| `--channels CHANS` | Comma-separated channels (overrides `IRC_CHANNELS`) |
| `--tls` | Connect with TLS (overrides `IRC_USE_TLS`) |
| `--model MODEL` | Default model (overrides `DEFAULT_MODEL`) |
| `--generate-key` | Generate a Fernet encryption key and exit |

CLI flags override their corresponding environment variables.

## Commands

### User Commands

| Command | Aliases | Description |
|---|---|---|
| `!ai <message>` | `!chat`, `!ask` | Talk to the AI |
| `!persona <text>` | | Set a persona and reintroduce |
| `!custom <prompt>` | | Set a custom system prompt |
| `!reset` | | Reset conversation to defaults |
| `!stock` | | Reset conversation with no system prompt |
| `!mymodel [name]` | | Show or set your model |
| `!location <place>` | | Set your location for contextual answers |
| `!x <nick> <message>` | | Talk as another user |

### Admin Commands

| Command | Description |
|---|---|
| `!model [name\|reset]` | Show/set global default model |
| `!tools [on\|off\|toggle\|status]` | Enable/disable tool use |
| `!verbose [on\|off\|toggle]` | Toggle verbose mode |
| `!clear` | Clear all conversation state |
| `!country [on\|off\|status]` | Toggle search country filtering |
| `!join <#channel>` | Join a channel |
| `!part [#channel] [reason]` | Leave a channel |

Built-in IRC commands (`!ping`, `!time`, `!help`) are also available.

## Documentation

- [docs/configuration.md](docs/configuration.md) -- IRC and AI provider configuration
- [docs/commands.md](docs/commands.md) -- command registry and decorator API
- [docs/extending.md](docs/extending.md) -- subclassing IRCBot, event hooks
- [docs/ai-agent.md](docs/ai-agent.md) -- AI agent architecture, providers, tools, and history
- [docs/ai-output-disclaimer.md](docs/ai-output-disclaimer.md) -- AI output disclaimer and conditions of use
- [docs/not-a-companion.md](docs/not-a-companion.md) -- project scope and intended use

## License

MIT
