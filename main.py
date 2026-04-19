"""Household Agent — домашній асистент."""
import logging
import sys
from pathlib import Path
from telegram.ext import Application
from core.config import TELEGRAM_TOKEN, LOGS_DIR
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("main")


async def error_handler(update: object, context):
    log.error(f"Помилка: {context.error}")


def main():
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_TOKEN не встановлено")
        sys.exit(1)

    from bot.client import setup_handlers

    log.info("Household Agent стартує...")

    from bot.client import post_init
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .post_init(post_init)
        .build()
    )

    setup_handlers(app)
    app.add_error_handler(error_handler)

    log.info("Polling запущено")
    try:
        app.run_polling(
            drop_pending_updates=True,
            poll_interval=1.0,
            timeout=20
        )
    finally:
        pass


if __name__ == "__main__":
    main()
