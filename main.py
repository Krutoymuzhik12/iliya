"""Точка входа: python main.py"""

from __future__ import annotations

import asyncio
import logging
import sys

from avito.bot_worker import AvitoBot
from config.settings import DATA_DIR, SETTINGS


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(SETTINGS.log_path, encoding="utf-8"),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    bot = AvitoBot(SETTINGS)
    asyncio.run(bot.run())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
