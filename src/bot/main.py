import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import settings
from src.db.database import db
from src.bot.handlers import router
from src.bot.yandex_gpt import yandex_gpt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup():
    logger.info("Connecting to database...")
    await db.connect()
    logger.info("Database connected")

    logger.info("Initializing Yandex GPT...")
    await yandex_gpt.init()
    logger.info("Yandex GPT ready")


async def on_shutdown():
    logger.info("Closing Yandex GPT client...")
    await yandex_gpt.close()

    logger.info("Disconnecting from database...")
    await db.disconnect()
    logger.info("Database disconnected")


async def main():
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting AQUADOKS bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
