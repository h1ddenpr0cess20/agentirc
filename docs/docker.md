# Docker

## Quick Start

```bash
cp .env.example .env
# Edit .env with your IRC server, nick, and API keys
docker compose up -d
```

This builds the image and starts the bot in the background. Conversation history is stored in a named volume (`history`).

## Building the Image

Build manually without Compose:

```bash
docker build -t agentirc .
```

Then run it:

```bash
docker run -d --env-file .env --name agentirc agentirc
```

## docker-compose.yml

```yaml
services:
  agentirc:
    build: .
    env_file: .env
    volumes:
      - history:/app
    restart: unless-stopped

volumes:
  history:
```

| Key | Purpose |
|---|---|
| `build: .` | Builds from the `Dockerfile` in the repo root |
| `env_file: .env` | Loads all configuration from your `.env` file |
| `volumes: history:/app` | Persists conversation history across restarts |
| `restart: unless-stopped` | Auto-restarts the bot unless you explicitly stop it |

## Dockerfile

The image uses `python:3.12-slim` and installs the package with the `crypto` extra (for encrypted history). The entrypoint is `agentirc`.

## Managing the Container

```bash
# View logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code changes
docker compose up -d --build

# Restart
docker compose restart
```

## Passing CLI Flags

Override the default command to pass CLI flags:

```bash
docker run --env-file .env agentirc agentirc --debug --tls
```

Or in `docker-compose.yml`:

```yaml
services:
  agentirc:
    build: .
    env_file: .env
    command: ["agentirc", "--debug", "--tls"]
```

## Environment Variables

All configuration is done through environment variables loaded from `.env`. See [configuration.md](configuration.md) for the full list.

## Notes

- The image does **not** include a `.env` file — you must provide one at runtime.
- If you change code or dependencies, rebuild with `docker compose up -d --build`.
- TLS to the IRC server is configured via `IRC_USE_TLS=true` in `.env`, not in Docker networking.
