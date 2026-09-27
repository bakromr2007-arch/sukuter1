import asyncio
import logging
from datetime import date

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID, WEBAPP_URL
from database import SessionLocal, init_db
from models import Rental

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

webapp_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Ochish", web_app=WebAppInfo(url=WEBAPP_URL))]],
    resize_keyboard=True,
)


# ---------------- /start ----------------
# Butun boshqaruv (mijoz qo'shish, to'lov qayd qilish, ro'yxatlar) endi
# WebApp ichida amalga oshiriladi. Bot faqat: 1) mijozni ro'yxatdan o'tkazadi
# (havola orqali kirganda), 2) WebApp tugmasini beradi, 3) eslatmalarni yuboradi.
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    args = command.args
    db = SessionLocal()
    try:
        if args and args.startswith("reg_"):
            try:
                rental_id = int(args.replace("reg_", ""))
            except ValueError:
                await message.answer("Havola noto'g'ri.")
                return
            rental = db.query(Rental).filter(Rental.id == rental_id).first()
            if not rental:
                await message.answer("Ariza topilmadi. Admin bilan bog'laning.")
                return
            rental.telegram_id = message.from_user.id
            rental.status = "faol"
            rental.start_date = date.today()
            rental.paid_until = date.today()
            db.commit()
            await message.answer(
                f"Assalomu alaykum, {rental.full_name}!\n"
                f"Siz {rental.scooter_info} skuterini ijaraga oldingiz.\n"
                f"Kunlik narx: {rental.daily_rate:,.0f} so'm.\n\n"
                "To'lovlaringiz va qarzingizni pastdagi tugma orqali kuzatib boring.",
                reply_markup=webapp_kb,
            )
            return

        greeting = "Salom, Admin!" if message.from_user.id == ADMIN_ID else "Salom!"
        await message.answer(
            f"{greeting}\nKabinetni ochish uchun pastdagi tugmani bosing.",
            reply_markup=webapp_kb,
        )
    finally:
        db.close()


# ---------------- Kunlik eslatma ----------------
async def send_daily_reminders():
    db = SessionLocal()
    try:
        rentals = db.query(Rental).filter(Rental.status == "faol").all()
        admin_lines = []
        for r in rentals:
            debt = r.debt_amount()
            if debt > 0 and r.telegram_id:
                try:
                    await bot.send_message(
                        r.telegram_id,
                        "⚠️ Eslatma: to'lov muddatingiz o'tgan.\n"
                        f"Qarz: {debt:,.0f} so'm ({r.debt_days()} kun)\n"
                        "Iltimos to'lovni amalga oshiring.",
                    )
                except Exception:
                    pass
                admin_lines.append(f"{r.full_name}: {debt:,.0f} so'm")
        if admin_lines and ADMIN_ID:
            await bot.send_message(ADMIN_ID, "📋 Bugungi qarzdorlar:\n" + "\n".join(admin_lines))
    finally:
        db.close()


async def main():
    init_db()
    me = await bot.get_me()
    logging.info(f"Bot ishga tushdi: @{me.username}  (buni config.py'dagi BOT_USERNAME ga qo'ying)")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_reminders, "cron", hour=9, minute=0)  # har kuni 09:00
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
