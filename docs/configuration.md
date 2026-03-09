# Configuration

The bot is configured entirely through environment variables. Copy `.env.example` to `.env` and edit it before running.

## TL;DR

Two variables are required: `IRC_HOST` and `IRC_NICK`. Everything else has a default.

## Loading order

`load_env()` reads `.env` from the current working directory using `os.environ.setdefault`, so real environment variables always take precedence over the file. You can skip the file entirely and export variables directly in your shell or process manager.

## Variables

| Variable         | Type    | Required | Default      | Description |
|------------------|---------|----------|--------------|-------------|
| `IRC_HOST`       | string  | yes      | —            | Hostname or IP of the IRC server |
| `IRC_PORT`       | integer | no       | `6667`       | TCP port |
| `IRC_NICK`       | string  | yes      | —            | Nickname the bot registers with |
| `IRC_USER`       | string  | no       | value of `IRC_NICK` | IRC username (the `USER` line) |
| `IRC_REALNAME`   | string  | no       | `IRC Bot`    | Real name field shown in WHOIS |
| `IRC_CHANNELS`   | string  | no       | _(empty)_    | Comma-separated list of channels to join on connect |
| `IRC_PASSWORD`   | string  | no       | _(empty)_    | Server password sent as `PASS` before registration |
| `IRC_USE_TLS`    | boolean | no       | `false`      | Connect over TLS. Accepts `1`, `true`, or `yes` |
| `IRC_CMD_PREFIX` | string  | no       | `!`          | Prefix character that triggers command dispatch |

## Examples

Minimal `.env` for a plaintext connection:

```ini
IRC_HOST=irc.libera.chat
IRC_NICK=mybot
IRC_CHANNELS=#mychannel
```

TLS on port 6697 with a server password:

```ini
IRC_HOST=irc.libera.chat
IRC_PORT=6697
IRC_USE_TLS=true
IRC_NICK=mybot
IRC_PASSWORD=s3cr3t
IRC_CHANNELS=#mychannel,#dev
```

Custom command prefix (use `.` instead of `!`):

```ini
IRC_CMD_PREFIX=.
```

## Notes

- `IRC_CHANNELS` is split on commas. Whitespace around channel names is stripped. An empty value means the bot connects but joins no channels automatically.
- If `IRC_NICK` is taken on connect, the bot appends `_` and retries. It does not restore the original nick automatically.
- The `.env` file uses `key=value` syntax. Blank lines and lines starting with `#` are ignored. Values may be wrapped in single or double quotes, which are stripped automatically.
- TLS uses Python's `ssl.create_default_context()`, which verifies the server certificate against the system trust store. Self-signed or non-standard CA certificates require code changes to `IRCConnection`.

> **New to `.env` files?** A `.env` file is a plain text file where each line sets one environment variable. Your shell does not read it automatically — the bot reads it at startup via `load_env()`. Never commit your `.env` file to version control if it contains passwords.
