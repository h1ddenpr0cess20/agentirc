"""Entry point: python -m chatbot"""

import asyncio
import logging

from .config import ChatConfig
from .bot import ChatBot


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    config = ChatConfig.from_env()
    bot = ChatBot(config)
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
