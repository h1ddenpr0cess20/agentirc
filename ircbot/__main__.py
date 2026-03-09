"""Entry point: python -m ircbot"""

from __future__ import annotations

import asyncio
import logging
import sys

from .config import load_env, BotConfig
from .bot import IRCBot
from .commands import register_builtins


def setup_logging() -> None:
    """Configure stdlib logging with a clean format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
    # Quiet down the debug-level line logging unless DEBUG is set
    logging.getLogger("ircbot.connection").setLevel(
        logging.DEBUG if "--debug" in sys.argv else logging.INFO
    )


async def main() -> None:
    load_env()
    config = BotConfig.from_env()
    bot = IRCBot(config)
    register_builtins(bot)
    await bot.run()


if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutting down.")
