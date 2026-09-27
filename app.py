import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import LOG_LEVEL, REMINDER_HOUR_UTC, REMINDER_MINUTE_UTC
from webapp_api import app
from bot import bot, dp, send_daily_reminders

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("app")

scheduler = AsyncIOScheduler()


async def run_polling():
    """Botni fon jarayonida ishga tushiradi. Xatolik bo'lsa jim o'lib qolmasdan,
    to'liq traceback bilan Render loglariga yozadi — shunda muammoni ko'rish oson."""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("❌ BOT POLLING TO'XTAB QOLDI:")


@asynccontextmanager
async def lifespan(app):
    log.info("🚀 Ishga tushirilmoqda...")

    try:
        me = await bot.get_me()
        log.info(f"✅ Bot ulandi: @{me.username}")
    except Exception:
        # Bot bilan ulanib bo'lmasa ham, WebApp (admin panel/kabinet) ishlab
        # tursin — faqat botning o'zi javob bermaydi. Butun xizmat qulab
        # tushmasligi kerak.
        log.exception("❌ BOT_TOKEN bilan ulanib bo'lmadi — WebApp baribir ishlaydi:")

    scheduler.add_job(send_daily_reminders, "cron", hour=REMINDER_HOUR_UTC, minute=REMINDER_MINUTE_UTC)
    scheduler.start()
    log.info(f"⏰ Scheduler ishga tushdi (har kuni {REMINDER_HOUR_UTC:02d}:{REMINDER_MINUTE_UTC:02d} UTC)")

    polling_task = asyncio.create_task(run_polling())
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
