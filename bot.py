import logging
from datetime import date

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)

from config import BOT_TOKEN, ADMIN_IDS, WEBAPP_URL
from database import SessionLocal
from models import Rental

log = logging.getLogger(__name__)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

webapp_kb = ReplyKeyboardMarkup(
    keyboard=[[
        KeyboardButton(
            text="📱 Kabinetni ochish",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    ]],
    resize_keyboard=True,
)


# ==================== /start ====================
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    args = command.args
    db = SessionLocal()
    try:
        # Ro'yxatdan o'tish havolasi: /start reg_5
        if args and args.startswith("reg_"):
            raw = args.replace("reg_", "").strip()
            if not raw.isdigit():
                await message.answer("❌ Havola noto'g'ri.")
                return

            rental = db.query(Rental).filter(Rental.id == int(raw)).first()
            if not rental:
                await message.answer("❌ Ariza topilmadi. Admin bilan bog'laning.")
                return

            if rental.telegram_id and rental.telegram_id != message.from_user.id:
                await message.answer("❌ Bu havola boshqa foydalanuvchi uchun.")
                return

            rental.telegram_id = message.from_user.id
            rental.status = "faol"
            rental.start_date = date.today()
            rental.paid_until = date.today()
            db.commit()

            await message.answer(
                f"Assalomu alaykum, <b>{rental.full_name}</b>!\n\n"
                f"🛴 Skuter: {rental.scooter_info}\n"
                f"💰 Kunlik: {rental.daily_rate:,.0f} so'm\n"
                f"📅 To'lov turi: {rental.payment_type}\n\n"
                f"Kabinetni ochib, to'lovlaringizni kuzatib boring.",
                reply_markup=webapp_kb,
                parse_mode="HTML",
            )
            log.info(f"✅ Yangi mijoz: {rental.full_name} (id={rental.id})")

            # Adminlarga xabar
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        f"🆕 Yangi mijoz faollashdi\n\n"
                        f"👤 {rental.full_name}\n"
                        f"📞 {rental.phone or '—'}\n"
                        f"🛴 {rental.scooter_info}",
                    )
                except Exception:
                    pass
            return

        # Admin yoki oddiy foydalanuvchi
        is_admin = message.from_user.id in ADMIN_IDS
        greeting = "Salom, Admin! 👋" if is_admin else "Salom! 👋"
        await message.answer(
            f"{greeting}\n\n"
            f"{'Boshqaruv paneli' if is_admin else 'Kabinet'}"
            f"ni ochish uchun pastdagi tugmani bosing.",
            reply_markup=webapp_kb,
        )
    finally:
        db.close()


# ==================== /holat ====================
@router.message(Command("holat"))
async def cmd_holat(message: Message):
    db = SessionLocal()
    try:
        rental = db.query(Rental).filter(
            Rental.telegram_id == message.from_user.id
        ).first()
        if not rental:
            await message.answer("Siz mijoz sifatida ro'yxatdan o'tmagansiz.")
            return

        debt = rental.debt_amount()
        days_left = rental.days_left()

        text = f"📊 <b>Sizning holatingiz</b>\n\n"
        text += f"🛴 {rental.scooter_info}\n"
        text += f"💰 Kunlik: {rental.daily_rate:,.0f} so'm\n\n"

        if debt > 0:
            text += f"⚠️ <b>Qarz: {debt:,.0f} so'm</b>\n"
            text += f"📅 {rental.debt_days()} kundan beri to'lanmagan\n"
        else:
            text += f"✅ Qarz yo'q\n"
            text += f"📅 To'lov {rental.paid_until.strftime('%d.%m.%Y')} gacha yopilgan\n"
            text += f"⏳ {days_left} kun qoldi\n"

        text += f"\n💵 Jami to'langan: {rental.total_paid():,.0f} so'm"

        await message.answer(text, parse_mode="HTML")
    finally:
        db.close()


# ==================== /yordam ====================
@router.message(Command("yordam"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Buyruqlar</b>\n\n"
        "/start — boshlash\n"
        "/holat — qarz va to'lov holati\n"
        "/yordam — bu xabar\n\n"
        "To'liq ma'lumot uchun pastdagi <b>📱 Kabinetni ochish</b> tugmasini bosing.",
        parse_mode="HTML",
    )


# ==================== Har kunlik eslatma ====================
async def send_daily_reminders():
    db = SessionLocal()
    try:
        rentals = db.query(Rental).filter(Rental.status == "faol").all()
        admin_debtors = []
        admin_soon = []
        today = date.today()

        for r in rentals:
            debt = r.debt_amount()

            # 1) Qarzdorlar
            if debt > 0 and r.telegram_id:
                try:
                    await bot.send_message(
                        r.telegram_id,
                        f"⚠️ <b>To'lov eslatmasi</b>\n\n"
                        f"🛴 {r.scooter_info}\n"
                        f"💰 Qarz: <b>{debt:,.0f} so'm</b>\n"
                        f"📅 {r.debt_days()} kundan beri to'lanmagan\n\n"
                        f"Iltimos, tezroq to'lovni amalga oshiring.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    log.warning(f"Xabar yuborilmadi ({r.telegram_id}): {e}")
                admin_debtors.append(
                    f"• {r.full_name}: {debt:,.0f} so'm ({r.debt_days()} kun)"
                )

            # 2) To'lov tugashiga 0-2 kun qolgan
            elif r.telegram_id and r.paid_until:
                days_left = (r.paid_until - today).days
                if days_left in (0, 1, 2):
                    try:
                        await bot.send_message(
                            r.telegram_id,
                            f"⏰ <b>To'lov yaqinlashdi</b>\n\n"
                            f"🛴 {r.scooter_info}\n"
                            f"📅 {r.paid_until.strftime('%d.%m.%Y')} da tugaydi\n"
                            f"⏳ {days_left} kun qoldi\n\n"
                            f"Kunlik: {r.daily_rate:,.0f} so'm",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
                    admin_soon.append(
                        f"• {r.full_name}: {days_left} kun qoldi"
                    )

        # Adminlarga hisobot
        if admin_debtors or admin_soon:
            report = "📋 <b>Bugungi hisobot</b>\n\n"
            if admin_debtors:
                report += f"🔴 <b>Qarzdorlar ({len(admin_debtors)}):</b>\n"
                report += "\n".join(admin_debtors) + "\n\n"
            if admin_soon:
                report += f"🟡 <b>To'lov yaqinlashgan ({len(admin_soon)}):</b>\n"
                report += "\n".join(admin_soon)

            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, report, parse_mode="HTML")
                except Exception as e:
                    log.warning(f"Admin {admin_id}ga yuborilmadi: {e}")

    except Exception as e:
        log.exception(f"Eslatma yuborishda xato: {e}")
    finally:
        db.close()
