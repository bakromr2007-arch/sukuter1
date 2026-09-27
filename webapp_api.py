import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import time
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl

import httpx
from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import (
    BOT_TOKEN, ADMIN_IDS, ADMIN_PASSWORD, BOT_USERNAME, UPLOAD_DIR
)
from database import SessionLocal, init_db
from models import Rental, Payment

log = logging.getLogger("webapp")

app = FastAPI(title="Skuter Kabinet")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ==================== PAROL SESSIYALARI ====================
# Oddiy xotiradagi token ombori. Render qayta ishga tushsa — tozalanadi.
# Kichik loyiha uchun yetarli. Katta loyiha uchun Redis ishlatish kerak.
ADMIN_SESSIONS = {}  # {token: {"created": timestamp}}


def create_admin_session() -> str:
    token = secrets.token_urlsafe(32)
    ADMIN_SESSIONS[token] = {"created": time.time()}
    return token


def check_admin_session(token: str) -> bool:
    """Token 24 soat amal qiladi."""
    if not token:
        return False
    data = ADMIN_SESSIONS.get(token)
    if not data:
        return False
    if time.time() - data["created"] > 86400:
        ADMIN_SESSIONS.pop(token, None)
        return False
    return True


# ==================== TELEGRAM AUTH ====================
def check_telegram_auth(init_data: str) -> dict:
    if not init_data:
        log.warning("❌ initData bo'sh keldi")
        raise HTTPException(401, "initData bo'sh")

    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except Exception as e:
        log.warning(f"❌ initData parse xato: {e}")
        raise HTTPException(401, "initData formati noto'g'ri")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "hash yo'q")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        log.warning("❌ initData imzo noto'g'ri")
        raise HTTPException(401, "Imzo noto'g'ri")

    auth_date = int(parsed.get("auth_date", 0))
    if (datetime.utcnow().timestamp() - auth_date) > 86400:
        raise HTTPException(401, "initData eskirgan")

    user = json.loads(parsed.get("user", "{}"))
    log.info(f"👤 Foydalanuvchi: {user.get('id')} ({user.get('first_name', '')})")
    return user


def is_admin_by_telegram(init_data: str) -> bool:
    """initData orqali admin ekanligini tekshiradi."""
    try:
        user = check_telegram_auth(init_data)
        return user.get("id") in ADMIN_IDS
    except Exception:
        return False


def require_admin_api(
    init_data: str = "",
    x_admin_token: str = "",
) -> str:
    """
    Ikkita usuldan birini qabul qiladi:
    1. Telegram initData (agar ADMIN_IDS da bo'lsa)
    2. X-Admin-Token sarlavhasi (parol orqali kirgan bo'lsa)
    """
    # Usul 1: parol tokeni
    if x_admin_token and check_admin_session(x_admin_token):
        return "session"

    # Usul 2: Telegram initData
    if init_data:
        user = check_telegram_auth(init_data)
        if user.get("id") in ADMIN_IDS:
            return "telegram"

    raise HTTPException(403, "Faqat admin uchun")


# ==================== XABAR ====================
def notify_user(chat_id: int, text: str):
    try:
        httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as e:
        log.warning(f"Xabar yuborilmadi: {e}")


# ==================== SERIALIZER ====================
def serialize_rental(r: Rental) -> dict:
    return {
        "id": r.id,
        "full_name": r.full_name,
        "phone": r.phone or "—",
        "passport": r.passport or "—",
        "scooter_info": r.scooter_info,
        "daily_rate": r.daily_rate,
        "payment_type": r.payment_type,
        "status": r.status,
        "start_date": r.start_date.strftime("%d.%m.%Y") if r.start_date else "—",
        "paid_until": r.paid_until.strftime("%d.%m.%Y") if r.paid_until else "—",
        "paid_until_iso": r.paid_until.isoformat() if r.paid_until else None,
        "total_paid": r.total_paid(),
        "paid_days": r.paid_days(),
        "debt": r.debt_amount(),
        "debt_days": r.debt_days(),
        "days_left": r.days_left(),
        # Video URL'lar (to'liq yo'l)
        "video_selfie_url": r.video_selfie if r.video_selfie else None,
        "video_scooter_url": r.video_scooter if r.video_scooter else None,
        "has_selfie": bool(r.video_selfie),
        "has_scooter_video": bool(r.video_scooter),
        "notes": r.notes,
        "reg_link": (
            f"https://t.me/{BOT_USERNAME}?start=reg_{r.id}"
            if r.status == "kutilmoqda" else None
        ),
        "telegram_linked": bool(r.telegram_id),
    }


def serialize_payment(p: Payment) -> dict:
    return {
        "id": p.id,
        "amount": p.amount,
        "days_covered": round(p.days_covered, 1),
        "method": p.method,
        "note": p.note,
        "date": p.date.strftime("%d.%m.%Y %H:%M") if p.date else "—",
    }


# ==================== HEALTH ====================
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "time": datetime.utcnow().isoformat(),
        "admins_count": len(ADMIN_IDS),
    }


# ==================== WHOAMI ====================
@app.get("/api/whoami")
def whoami(init_data: str = "", x_admin_token: str = Header("")):
    # Parol orqali kirilgan bo'lsa
    if x_admin_token and check_admin_session(x_admin_token):
        return {
            "is_admin": True,
            "via": "password",
            "name": "Admin",
            "user_id": None,
        }

    # Telegram orqali
    if not init_data:
        return {"is_admin": False, "via": "none", "name": "", "user_id": None}

    try:
        user = check_telegram_auth(init_data)
        return {
            "is_admin": user.get("id") in ADMIN_IDS,
            "via": "telegram",
            "name": user.get("first_name", ""),
            "user_id": user.get("id"),
        }
    except HTTPException:
        return {"is_admin": False, "via": "none", "name": "", "user_id": None}


# ==================== PAROL ORQALI KIRISH ====================
@app.post("/api/admin/login")
def admin_login(password: str = Form(...)):
    if not ADMIN_PASSWORD:
        raise HTTPException(500, "Admin parol o'rnatilmagan")
    if password != ADMIN_PASSWORD:
        log.warning(f"❌ Noto'g'ri parol kiritildi")
        raise HTTPException(401, "Parol noto'g'ri")

    token = create_admin_session()
    log.info(f"🔑 Admin parol orqali kirdi")
    return {"ok": True, "token": token}


@app.post("/api/admin/logout")
def admin_logout(x_admin_token: str = Header("")):
    if x_admin_token:
        ADMIN_SESSIONS.pop(x_admin_token, None)
    return {"ok": True}


# ==================== USER: KABINET ====================
@app.get("/api/me")
def get_me(init_data: str):
    user = check_telegram_auth(init_data)
    db = SessionLocal()
    try:
        rental = db.query(Rental).filter(
            Rental.telegram_id == user.get("id")
        ).first()
        if not rental:
            raise HTTPException(404, "Mijoz topilmadi")
        data = serialize_rental(rental)
        data["payments"] = [serialize_payment(p) for p in rental.payments]
        return data
    finally:
        db.close()


# ==================== ADMIN ENDPOINTLAR ====================
@app.get("/api/admin/rentals")
def admin_rentals(
    init_data: str = "",
    x_admin_token: str = Header(""),
):
    require_admin_api(init_data, x_admin_token)
    db = SessionLocal()
    try:
        rentals = (
            db.query(Rental)
            .filter(Rental.status.in_(["faol", "kutilmoqda"]))
            .order_by(Rental.created_at.desc())
            .all()
        )
        return [serialize_rental(r) for r in rentals]
    finally:
        db.close()


@app.get("/api/admin/rentals/{rental_id}")
def admin_rental_detail(
    rental_id: int,
    init_data: str = "",
    x_admin_token: str = Header(""),
):
    require_admin_api(init_data, x_admin_token)
    db = SessionLocal()
    try:
        rental = db.query(Rental).filter(Rental.id == rental_id).first()
        if not rental:
            raise HTTPException(404, "Topilmadi")
        data = serialize_rental(rental)
        data["payments"] = [serialize_payment(p) for p in rental.payments]
        return data
    finally:
        db.close()


@app.post("/api/admin/rentals")
async def create_rental(
    init_data: str = Form(""),
    full_name: str = Form(...),
    phone: str = Form(...),
    passport: str = Form(""),
    scooter_info: str = Form(...),
    daily_rate: float = Form(...),
    payment_type: str = Form("kunlik"),
    notes: str = Form(""),
    video_selfie: UploadFile = File(None),
    video_scooter: UploadFile = File(None),
    x_admin_token: str = Header(""),
):
    require_admin_api(init_data, x_admin_token)
    db = SessionLocal()
    try:
        def save_video(v: UploadFile, prefix: str):
            if not v or not v.filename:
                return None
            ext = os.path.splitext(v.filename)[1] or ".mp4"
            fname = f"{prefix}_{int(datetime.utcnow().timestamp())}_{os.urandom(4).hex()}{ext}"
            full = os.path.join(UPLOAD_DIR, fname)
            with open(full, "wb") as f:
                shutil.copyfileobj(v.file, f)
            return f"/uploads/{fname}"

        rental = Rental(
            full_name=full_name,
            phone=phone,
            passport=passport or None,
            scooter_info=scooter_info,
            daily_rate=daily_rate,
            payment_type=payment_type,
            notes=notes or None,
            video_selfie=save_video(video_selfie, "selfie"),
            video_scooter=save_video(video_scooter, "scooter"),
            status="kutilmoqda",
        )
        db.add(rental)
        db.commit()
        db.refresh(rental)
        log.info(f"➕ Yangi mijoz: {rental.full_name} (id={rental.id})")
        return serialize_rental(rental)
    finally:
        db.close()


@app.post("/api/admin/payments")
async def create_payment(
    init_data: str = Form(""),
    rental_id: int = Form(...),
    amount: float = Form(...),
    method: str = Form("naqd"),
    note: str = Form(""),
    x_admin_token: str = Header(""),
):
    require_admin_api(init_data, x_admin_token)
    if amount <= 0:
        raise HTTPException(400, "Summa musbat bo'lishi kerak")

    db = SessionLocal()
    try:
        rental = db.query(Rental).filter(Rental.id == rental_id).first()
        if not rental:
            raise HTTPException(404, "Mijoz topilmadi")
        if rental.status != "faol":
            raise HTTPException(400, "Ijara faol emas")

        days_covered = amount / rental.daily_rate
        base = rental.paid_until if rental.paid_until and rental.paid_until >= date.today() else date.today()
        rental.paid_until = base + timedelta(days=days_covered)

        db.add(Payment(
            rental_id=rental.id,
            amount=amount,
            days_covered=days_covered,
            method=method,
            note=note or None,
        ))
        db.commit()
        db.refresh(rental)

        if rental.telegram_id:
            notify_user(
                rental.telegram_id,
                f"✅ <b>To'lov qabul qilindi</b>\n\n"
                f"💰 Summa: {amount:,.0f} so'm\n"
                f"📅 {rental.paid_until.strftime('%d.%m.%Y')} gacha to'langan\n"
                f"⏳ {(rental.paid_until - date.today()).days} kun qoldi",
            )

        log.info(f"💵 To'lov: {rental.full_name} - {amount:,.0f} so'm")
        return serialize_rental(rental)
    finally:
        db.close()


@app.post("/api/admin/rentals/{rental_id}/finish")
def finish_rental(
    rental_id: int,
    init_data: str = Form(""),
    x_admin_token: str = Header(""),
):
    require_admin_api(init_data, x_admin_token)
    db = SessionLocal()
    try:
        rental = db.query(Rental).filter(Rental.id == rental_id).first()
        if not rental:
            raise HTTPException(404, "Topilmadi")
        rental.status = "tugagan"
        db.commit()

        if rental.telegram_id:
            notify_user(
                rental.telegram_id,
                f"✅ <b>Ijara tugatildi</b>\n\n"
                f"🛴 {rental.scooter_info}\n"
                f"Xizmatimizdan foydalanganingiz uchun rahmat!",
            )
        log.info(f"🏁 Tugatildi: {rental.full_name}")
        return {"ok": True}
    finally:
        db.close()


# ==================== STATIC ====================
def mount_static():
    init_db()
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
    app.mount("/", StaticFiles(directory="webapp", html=True), name="webapp")


mount_static()
