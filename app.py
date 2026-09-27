"""
Ilova kirish nuqtasi.

Bot polling o'rniga WEBHOOK rejimida ishlaydi — bu Render kabi platformalarda
muhim: deploy paytida eski va yangi nusxa bir necha soniya parallel ishlashi
mumkin, va ikkita polling bir vaqtda ishlasa Telegram "409 Conflict" xatosini
qaytaradi. Webhook rejimida bu muammo umuman yo'q, chunki Telegram
so'rovlarni to'g'ridan-to'g'ri shu web-serverga yuboradi.
"""
import hashlib
import logging
from contextlib import asynccontextmanager

from aiogram.types import Update
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Header, HTTPException, Request

from config import (
    BOT_TOKEN, LOG_LEVEL, PORT, REMINDER_HOUR_UTC, REMINDER_MINUTE_UTC, WEBAPP_URL,
)
from webapp_api import app
from bot import bot, dp, send_daily_reminders

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("app")

scheduler = AsyncIOScheduler()

# Webhook manzili bot tokenidan olingan maxfiy qism bilan — taxmin qilib bo'lmaydi
# va Telegram'ning o'zi yuboradigan "secret token" sarlavhasi bilan qo'shimcha tekshiriladi.
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:32]
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{WEBAPP_URL}{WEBHOOK_PATH}"


@asynccontextmanager
async def lifespan(app):
    log.info("🚀 Ishga tushirilmoqda...")

    me = await bot.get_me()
    log.info(f"✅ Bot ulandi: @{me.username}")

    await bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
    )
    log.info(f"🔗 Webhook o'rnatildi: {WEBAPP_URL}/webhook/***")

    scheduler.add_job(send_daily_reminders, "cron", hour=REMINDER_HOUR_UTC, minute=REMINDER_MINUTE_UTC)
    scheduler.start()
    log.info(f"⏰ Scheduler ishga tushdi (har kuni {REMINDER_HOUR_UTC:02d}:{REMINDER_MINUTE_UTC:02d} UTC)")

    try:
        yield
    finally:
        log.info("🛑 To'xtatilmoqda...")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await bot.session.close()
        log.info("✅ To'xtatildi")


app.router.lifespan_context = lifespan


@app.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
):
    """Telegram shu manzilga yangilanishlarni (xabar, tugma bosilishi va h.k.) yuboradi."""
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(403, "Noto'g'ri secret token")

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}


if __name__ == "__main__":
    # Lokal ishga tushirish: python app.py
    # (Render'da startCommand orqali uvicorn to'g'ridan-to'g'ri chaqiriladi)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
