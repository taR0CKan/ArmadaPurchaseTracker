from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
import os
import logging

from commands import router as commands_router
from bot import messages_router

import asyncio

from reminders import (
    reminder_chat_id,
    reminders_enabled,
    run_daily_reminders,
)

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()
dp.include_routers(commands_router, messages_router)

async def  main():
    if reminders_enabled():
        reminder_chat_id()

    async with bot:
        reminder_task = (
            asyncio.create_task(run_daily_reminders(bot))
            if reminders_enabled()
            else None
        )
        if reminder_task is None:
            logging.info("Purchase deadline reminders are disabled")
        try:
            await dp.start_polling(
                bot,
                allowed_updates=["message", "message_reaction"],
                drop_pending_updates=False,
            )
        finally:
            if reminder_task is not None:
                reminder_task.cancel()
                try:
                    await reminder_task
                except asyncio.CancelledError:
                    pass

if __name__ == ("__main__"):
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())