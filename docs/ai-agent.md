# AI Agent

The `agentirc` package extends the base `ircbot` framework with multi-provider AI chat capabilities via Responses APIs.

## Architecture

```
agentirc/
  __main__.py   -- entry point (python -m agentirc)
  config.py     -- ChatConfig (extends BotConfig with AI settings)
  bot.py        -- ChatBot (wraps IRCBot with AI commands)
  api.py        -- ResponsesClient (HTTP client for Responses APIs)
  models.py     -- model discovery and provider resolution
  tools.py      -- tool definitions (web_search, x_search, code_interpreter, mcp)
  history.py    -- per-user conversation history with optional encryption
```

`ChatBot` creates an `IRCBot` instance, registers AI commands on it, and delegates IRC lifecycle to the base bot. Each user gets an independent conversation thread keyed by `(room, nick)`.

## Providers

Two providers are supported out of the box:

| Provider | Env Prefix | API Base Default |
|---|---|---|
| xAI | `XAI_*` | `https://api.x.ai/v1` |
| LM Studio | `LMSTUDIO_*` | `http://127.0.0.1:1234/v1` |

Each provider needs a base URL and API key (LM Studio can work without a key). Models can be listed explicitly via `*_MODELS` env vars or discovered from the server at startup when `AGENTIRC_SERVER_MODELS=true`.

## Configuration

All agentirc-specific variables (in addition to the [IRC variables](configuration.md)):

| Variable | Default | Description |
|---|---|---|
| `XAI_API_BASE` | `https://api.x.ai/v1` | xAI API base URL |
| `XAI_API_KEY` | | xAI API key |
| `XAI_MODELS` | | Comma-separated model list |
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` | LM Studio base URL |
| `LMSTUDIO_API_KEY` | | LM Studio API key (optional) |
| `LMSTUDIO_MODELS` | | Comma-separated model list |
| `DEFAULT_MODEL` | first available | Default model for all users |
| `AGENTIRC_TOOLS` | `web_search,x_search,code_interpreter` | Enabled tools |
| `AGENTIRC_ADMINS` | | Comma-separated admin nicks |
| `AGENTIRC_SERVER_MODELS` | `true` | Fetch model list from provider APIs |
| `AGENTIRC_DEFAULT_PERSONALITY` | `a helpful IRC chatbot` | Default persona |
| `AGENTIRC_PROMPT_PREFIX` | `You are ` | System prompt prefix |
| `AGENTIRC_PROMPT_SUFFIX` | `.` | System prompt suffix |
| `AGENTIRC_PROMPT_SUFFIX_EXTRA` | ` Keep responses concise...` | Appended when verbose mode is off |
| `AGENTIRC_SYSTEM_PROMPT` | | Override the entire system prompt |
| `AGENTIRC_MAX_TOKENS` | `300` | Max output tokens per response |
| `WEB_SEARCH_COUNTRY` | | ISO 3166-1 alpha-2 country code for search bias |
| `HISTORY_ENCRYPTION_KEY` | | Fernet key for persistent history |

## Tools

Tools are passed to the Responses API and executed server-side by the provider:

| Tool | Providers | Description |
|---|---|---|
| `web_search` | xAI | Web search with optional country bias |
| `x_search` | xAI | Search X/Twitter posts |
| `code_interpreter` | xAI | Execute code in a sandbox |

Tools are automatically filtered per-provider. xAI hosted tools (`web_search`, `x_search`, `code_interpreter`) require Grok 4+ models.

Admins can toggle tools at runtime with `!tools on|off`.

## Conversation History

Each `(room, user)` pair maintains an independent message thread with a system prompt. History is capped at 24 messages (oldest non-system messages are trimmed first).

### Encrypted Persistence

Set `HISTORY_ENCRYPTION_KEY` to persist conversations across restarts. Generate a key:

```bash
python -m agentirc --generate-key
```

History is saved to `history.enc` using Fernet symmetric encryption. The `cryptography` package is required.

### User Location

Users can set their location with `!location <place>`. The location is appended to system prompts across all threads and preserved across `!clear` operations.

## Per-User Models

Users can pick their own model with `!mymodel <name>`. This overrides the global default for that user in that room only. Admins can change the global default with `!model <name>`.
