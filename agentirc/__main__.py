"""Entry point: python -m agentirc"""

import argparse
import asyncio
import logging
import os

from .config import ChatConfig
from .bot import ChatBot


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-powered IRC agent")
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
    args = parser.parse_args()

    if args.generate_key:
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
        return

    # Load .env first, then apply CLI overrides (which win via direct set)
    from ircbot.config import load_env
    load_env(args.env_file)

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

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    config = ChatConfig.from_env()
    bot = ChatBot(config)
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
