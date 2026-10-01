import asyncio
import argparse
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from app.handlers import register_bot_routes
from app.core.bot import bot
from app.core.dispatcher import dp
from app.config import config
from app.models import Base
from app.database import engine
from app.logger import *


async def start_polling(info):
    dp["bot_info"] = info
    await register_bot_routes(dp)
    print("✅ Bot is running in polling mode...")
    await dp.start_polling(bot)


async def start_webhook(info, port):
    async def on_startup(app):
        await bot.set_webhook(config.WEBHOOK_URL, secret_token=config.SECRET)

    async def on_shutdown(app):
        await bot.delete_webhook()
    
    dp["bot_info"] = info
    await register_bot_routes(dp)
    
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=config.SECRET).register(app, path=config.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    print("✅ Bot is running in webhook mode...")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    await asyncio.Event().wait()


async def main(mode: str, port: int = 8000):
    print("Checking database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    bot_info = await bot.get_me()
    
    if mode == "polling":
        await start_polling(bot_info)
    elif mode == "webhook":
        await start_webhook(bot_info, port)
    else:
        print("❌ Invalid mode! Use 'polling' or 'webhook'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the bot in polling or webhook mode.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-p", "--polling", action="store_true", help="Run the bot in polling mode")
    group.add_argument("-w", "--webhook", action="store_true", help="Run the bot in webhook mode")
    parser.add_argument("--port", type=int, default=8000, help="Port number for webhook mode (default: 8000)")

    args = parser.parse_args()
    mode = "polling" if args.polling else "webhook"
    asyncio.run(main(mode, args.port))
