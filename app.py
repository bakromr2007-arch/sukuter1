"""
app.py — asosiy kirish nuqtasi.

Bir vaqtning o'zida:
  1. FastAPI (WebApp + admin panel) ni ishga tushiradi
  2. Aiogram botni polling rejimida ishga tushiradi
  3. APScheduler orqali kunlik eslatmalarni yuboradi

Render.com uchun moslashtirilgan:
  - PORT muhit o'zgaruvchisidan o'qiladi (Render avtomatik beradi)
  - HOST 0.0.0.0 (Render tashqi trafikni shu manzilga yuboradi)
  - lifespan orqali bot + scheduler to'g'ri ishga tushadi va to'xtaydi
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import LOG_LEVEL, REMINDER_HOUR_UTC, REMINDER_MINUTE_UTC
from webapp_api import app
from bot import bot, dp, send_daily_reminders

# ---------- LOGGING ----------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,  # Render loglarni stdout orqali oladi
)
log = logging.getLogger("app")

# ---------- SCHEDULER ----------
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app):
    """
    FastAPI ishga tushganda va to'xtaganda bajariladigan amallar.
    Bot polling va scheduler shu yerda boshqariladi.
    """
    log.info("🚀 Ishga tushirilmoqda...")

    # --- Botni tekshirish ---
    try:
        me = await bot.get_me()
        log.info(f"✅ Bot ulandi: @{me.username}")
    except Exception as e:
        log.exception(f"❌ Botga ulanib bo'lmadi: {e}")
        raise

    # --- Scheduler ---
    scheduler.add_job(
        send_daily_reminders,
        "cron",
        hour=REMINDER_HOUR_UTC,
        minute=REMINDER_MINUTE_UTC,
        id="daily_reminders",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        f"⏰ Scheduler ishga tushdi "
        f"(har kuni {REMINDER_HOUR_UTC:02d}:{REMINDER_MINUTE_UTC:02d} UTC)"
    )

    # --- Bot polling (fon vazifasi sifatida) ---
    polling_task = asyncio.create_task(dp.start_polling(bot))
    log.info("🤖 Bot polling boshlandi")

    try:
        yield
    finally:
        log.info("🛑 To'xtatilmoqda...")

        # Pollingni to'xtatish
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Pollingni to'xtatishda xato")

        # Schedulerni to'xtatish
        if scheduler.running:
            scheduler.shutdown(wait=False)

        # Bot sessiyasini yopish
        try:
            await bot.session.close()
        except Exception:
            log.exception("Bot sessiyasini yopishda xato")

        log.info("✅ To'xtatildi")


# FastAPI ga lifespan ni ulash
app.router.lifespan_context = lifespan


# ---------- RENDER UCHUN PORT ----------
# Render $PORT ni avtomatik beradi (odatda 10000 yoki shunga yaqin).
# Lokal ishga tushirganda 8000 ishlatiladi.
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")


if __name__ == "__main__":
    log.info(f"🌐 Server {HOST}:{PORT} da ishga tushmoqda")
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower(),
        access_log=False,  # Render o'z access loglarini yuritadi
    )
