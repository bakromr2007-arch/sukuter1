import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from webapp_api import app
from bot import bot, dp, send_daily_reminders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("app")

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app):
    log.info("🚀 Ishga tushirilmoqda...")

    me = await bot.get_me()
    log.info(f"✅ Bot ulandi: @{me.username}")

    # Har kuni 09:00 Toshkent (04:00 UTC)
    scheduler.add_job(send_daily_reminders, "cron", hour=4, minute=0)
    scheduler.start()
    log.info("⏰ Scheduler ishga tushdi (har kuni 09:00 Toshkent)")

    polling_task = asyncio.create_task(dp.start_polling(bot))
    log.info("🤖 Bot polling boshlandi")

    try:
        yield
    finally:
        log.info("🛑 To'xtatilmoqda...")
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await bot.session.close()
        log.info("✅ To'xtatildi")


app.router.lifespan_context = lifespan
