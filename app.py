import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from webapp_api import app  # FastAPI ilova va barcha /api/... endpointlar shu yerdan
from bot import bot, dp, send_daily_reminders

logging.basicConfig(level=logging.INFO)

scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def start_background_services():
    me = await bot.get_me()
    logging.info(f"Bot ulandi: @{me.username}")

    scheduler.add_job(send_daily_reminders, "cron", hour=9, minute=0)
    scheduler.start()

    # Bot pollingni asosiy web-server bilan bitta process ichida, fonda ishga tushiramiz
    asyncio.create_task(dp.start_polling(bot))
