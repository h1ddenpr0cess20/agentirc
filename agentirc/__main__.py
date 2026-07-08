"""Entry point: python -m agentirc"""

import argparse
import asyncio
import logging
import os

from .config import ChatConfig
from .bot import ChatBot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI-powered IRC agent")
    parser.add_argument(
        "--init",
        action="store_true",
        help="Write a starter .env file to the current directory and exit",
    )
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Generate a Fernet encryption key for history persistence and exit",
    )
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--host",
        metavar="HOST",
        help="IRC server hostname (overrides IRC_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        metavar="PORT",
        help="IRC server port (overrides IRC_PORT)",
    )
    parser.add_argument(
        "--nick",
        metavar="NICK",
        help="Bot nickname (overrides IRC_NICK)",
    )
    parser.add_argument(
        "--channels",
        metavar="CHANS",
        help="Comma-separated channels to join (overrides IRC_CHANNELS)",
    )
    parser.add_argument(
        "--tls",
        action="store_true",
        default=None,
        help="Connect with TLS (overrides IRC_USE_TLS)",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        help="Default model (overrides DEFAULT_MODEL)",
    )
    return parser


def write_starter_env() -> None:
    from importlib.resources import files
    dest = os.path.join(os.getcwd(), ".env")
    if os.path.exists(dest):
        print(f"{dest} already exists, not overwriting.")
        return
    content = files("agentirc").joinpath(".env.example").read_text()
    with open(dest, "w") as f:
        f.write(content)
    print(f"Wrote starter config to {dest}")


def apply_cli_overrides(args: argparse.Namespace) -> None:
    """Apply CLI flags on top of the loaded .env (direct set beats setdefault)."""
    if args.host:
        os.environ["IRC_HOST"] = args.host
    if args.port is not None:
        os.environ["IRC_PORT"] = str(args.port)
    if args.nick:
        os.environ["IRC_NICK"] = args.nick
    if args.channels:
        os.environ["IRC_CHANNELS"] = args.channels
    if args.tls:
        os.environ["IRC_USE_TLS"] = "true"
    if args.model:
        os.environ["DEFAULT_MODEL"] = args.model


def main() -> None:
    args = build_parser().parse_args()

    if args.init:
        write_starter_env()
        return

    if args.generate_key:
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
        return

    from ircbot.config import load_env
    load_env(args.env_file)
    apply_cli_overrides(args)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    config = ChatConfig.from_env(args.env_file)
    bot = ChatBot(config)
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutting down.")


if __name__ == "__main__":
    main()
