import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher

from src.config import settings
from src.db.database import db
from src.admin_bot.handlers import router
from src.admin_bot.sql_agent import sql_agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for admin bot."""
    logger.info("Starting AQUADOKS Admin Bot...")

    if not settings.admin_bot_token:
        logger.error("ADMIN_BOT_TOKEN is not set")
        sys.exit(1)

    if not settings.admin_bot_password:
        logger.error("ADMIN_BOT_PASSWORD is not set")
        sys.exit(1)

    # Initialize database
    logger.info("Connecting to database...")
    await db.connect()
    logger.info("Database connected")

    # Initialize SQL agent
    logger.info("Initializing SQL agent...")
    await sql_agent.init()
    logger.info("SQL agent initialized")

    # Initialize bot and dispatcher
    bot = Bot(token=settings.admin_bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    try:
        logger.info("Starting polling...")
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        await sql_agent.close()
        logger.info("SQL agent closed")
        await db.disconnect()
        logger.info("Database disconnected")


if __name__ == "__main__":
    asyncio.run(main())
