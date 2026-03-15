"""Entry point: python -m agentirc"""

import argparse
import asyncio
import logging

from .config import ChatConfig
from .bot import ChatBot


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-powered IRC agent")
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Generate a Fernet encryption key for history persistence and exit",
    )
    args = parser.parse_args()

    if args.generate_key:
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    config = ChatConfig.from_env()
    bot = ChatBot(config)
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
