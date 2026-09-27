import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import shutil
import time
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl

import httpx
from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Header, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import (
    BOT_TOKEN, ADMIN_IDS, ADMIN_PASSWORD, BOT_USERNAME, UPLOAD_DIR,
    MAX_UPLOAD_BYTES, MAX_UPLOAD_MB, ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_VIDEO_CONTENT_TYPES, INIT_DATA_MAX_AGE_SECONDS,
    ADMIN_SESSION_TTL_SECONDS, LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_SECONDS,
    CORS_ORIGINS,
)
from database import SessionLocal, init_db
from models import Rental, Payment, RentalStatus, AdminSession

log = logging.getLogger("webapp")

app = FastAPI(title="Skuter Kabinet API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Kutilmagan xatoni loglaymiz, lekin foydalanuvchiga stack trace ko'rsatmaymiz
    log.exception(f"Kutilmagan xato: {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Server xatosi. Birozdan so'ng urinib ko'ring."})


# ==================== LOGIN URINISHLARINI CHEKLASH ====================
_login_attempts: dict[str, list[float]] = {}


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_rate_limit(key: str):
    now = time.time()
    attempts = [t for t in _login_attempts.get(key, []) if now - t < LOGIN_LOCKOUT_SECONDS]
    _login_attempts[key] = attempts
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(429, "Juda ko'p urinish. Birozdan so'ng qayta urinib ko'ring.")


def _register_failed_attempt(key: str):
    _login_attempts.setdefault(key, []).append(time.time())


# ==================== ADMIN SESSIYALARI (bazada, restart-bardosh) ====================
def create_admin_session(db) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AdminSession(token=token))
    db.commit()
    return token


def check_admin_session(db, token: str) -> bool:
    if not token:
        return False
    session = db.query(AdminSession).filter(AdminSession.token == token).first()
    if not session:
        return False
    if session.is_expired(ADMIN_SESSION_TTL_SECONDS):
        db.delete(session)
        db.commit()
        return False
    return True


# ==================== TELEGRAM AUTH ====================
def check_telegram_auth(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(401, "initData bo'sh")

    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except Exception:
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
    if (datetime.utcnow().timestamp() - auth_date) > INIT_DATA_MAX_AGE_SECONDS:
        raise HTTPException(401, "initData eskirgan — botni qayta oching")

    user = json.loads(parsed.get("user", "{}"))
    return user


def is_admin_by_telegram(init_data: str) -> bool:
    try:
        user = check_telegram_auth(init_data)
        return user.get("id") in ADMIN_IDS
    except HTTPException:
        return False


def require_admin_api(db, init_data: str = "", x_admin_token: str = "") -> str:
    """
    Ikkita usuldan birini qabul qiladi:
    1. X-Admin-Token sarlavhasi (parol orqali kirgan bo'lsa)
    2. Telegram initData (agar foydalanuvchi ADMIN_IDS da bo'lsa)
    """
    if x_admin_token and check_admin_session(db, x_admin_token):
        return "session"

    if init_data:
        user = check_telegram_auth(init_data)
        if user.get("id") in ADMIN_IDS:
            return "telegram"

    raise HTTPException(403, "Faqat admin uchun")


# ==================== XABAR ====================
def notify_user(chat_id: int, text: str):
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        if resp.status_code != 200:
            log.warning(f"Telegramga xabar yuborilmadi: {resp.status_code} {resp.text}")
    except httpx.HTTPError as e:
        log.warning(f"Xabar yuborilmadi (tarmoq xatosi): {e}")


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
        "video_selfie_url": r.video_selfie or None,
        "video_scooter_url": r.video_scooter or None,
        "has_selfie": bool(r.video_selfie),
        "has_scooter_video": bool(r.video_scooter),
        "notes": r.notes,
        "reg_link": (
            f"https://t.me/{BOT_USERNAME}?start=reg_{r.id}"
            if r.status == RentalStatus.PENDING else None
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


# ==================== UPLOAD VALIDATSIYASI ====================
async def save_video(v: UploadFile | None, prefix: str) -> str | None:
    if not v or not v.filename:
        return None

    ext = os.path.splitext(v.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        # ✅ Python 3.11 uchun mos: backslashsiz
        ext_display = ext or "noma'lum"
        raise HTTPException(400, f"Video formati qo'llab-quvvatlanmaydi: {ext_display}")

    if v.content_type and v.content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
        raise HTTPException(400, f"Video turi qo'llab-quvvatlanmaydi: {v.content_type}")

    fname = f"{prefix}_{int(datetime.utcnow().timestamp())}_{secrets.token_hex(4)}{ext}"
    full_path = os.path.join(UPLOAD_DIR, fname)

    size = 0
    chunk_size = 1024 * 1024
    try:
        with open(full_path, "wb") as f:
            while True:
                chunk = await v.read(chunk_size)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    f.close()
                    os.remove(full_path)
                    raise HTTPException(
                        400,
                        f"Video hajmi {MAX_UPLOAD_MB}MB dan katta bo'lmasligi kerak",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception:
        if os.path.exists(full_path):
            os.remove(full_path)
        raise HTTPException(500, "Video saqlashda xatolik")

    return f"/uploads/{fname}"


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
def whoami(init_data: str = "", x_admin_token: str = Header("", alias="X-Admin-Token")):
    db = SessionLocal()
    try:
        if x_admin_token and check_admin_session(db, x_admin_token):
            return {"is_admin": True, "via": "password", "name": "Admin", "user_id": None}

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
    finally:
        db.close()


# ==================== PAROL ORQALI KIRISH ====================
@app.post("/api/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    key = _client_key(request)
    _check_rate_limit(key)

    if not ADMIN_PASSWORD:
        raise HTTPException(500, "Admin parol o'rnatilmagan")
    if password != ADMIN_PASSWORD:
        _register_failed_attempt(key)
        log.warning(f"❌ Noto'g'ri parol kiritildi ({key})")
        raise HTTPException(401, "Parol noto'g'ri")

    db = SessionLocal()
    try:
        token = create_admin_session(db)
    finally:
        db.close()
    log.info("🔑 Admin parol orqali kirdi")
    return {"ok": True, "token": token}


@app.post("/api/admin/logout")
def admin_logout(x_admin_token: str = Header("", alias="X-Admin-Token")):
    if x_admin_token:
        db = SessionLocal()
        try:
            session = db.query(AdminSession).filter(AdminSession.token == x_admin_token).first()
            if session:
                db.delete(session)
                db.commit()
        finally:
            db.close()
    return {"ok": True}


# ==================== USER: KABINET ====================
@app.get("/api/me")
def get_me(init_data: str):
    user = check_telegram_auth(init_data)
    db = SessionLocal()
    try:
        rental = db.query(Rental).filter(Rental.telegram_id == user.get("id")).first()
        if not rental:
            raise HTTPException(404, "Mijoz topilmadi")
        data = serialize_rental(rental)
        data["payments"] = [serialize_payment(p) for p in rental.payments]
        return data
    finally:
        db.close()


# ==================== ADMIN: RO'YXAT (qidiruv + filtr) ====================
@app.get("/api/admin/rentals")
def admin_rentals(
    init_data: str = "",
    x_admin_token: str = Header("", alias="X-Admin-Token"),
    status: str = Query("", description="faol / kutilmoqda / tugagan / bo'sh=hammasi (tugagandan tashqari)"),
    search: str = Query("", description="Ism, telefon yoki skuter bo'yicha qidiruv"),
):
    db = SessionLocal()
    try:
        require_admin_api(db, init_data, x_admin_token)

        q = db.query(Rental)
        if status and status in RentalStatus.ALL:
            q = q.filter(Rental.status == status)
        else:
            q = q.filter(Rental.status.in_([RentalStatus.ACTIVE, RentalStatus.PENDING]))

        if search:
            like = f"%{search.strip()}%"
            q = q.filter(
                (Rental.full_name.ilike(like))
                | (Rental.phone.ilike(like))
                | (Rental.scooter_info.ilike(like))
            )

        rentals = q.order_by(Rental.created_at.desc()).all()
        return [serialize_rental(r) for r in rentals]
    finally:
        db.close()


@app.get("/api/admin/rentals/{rental_id}")
def admin_rental_detail(
    rental_id: int,
    init_data: str = "",
    x_admin_token: str = Header("", alias="X-Admin-Token"),
):
    db = SessionLocal()
    try:
        require_admin_api(db, init_data, x_admin_token)
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
    x_admin_token: str = Header("", alias="X-Admin-Token"),
):
    db = SessionLocal()
    try:
        require_admin_api(db, init_data, x_admin_token)

        full_name = full_name.strip()
        phone = phone.strip()
        scooter_info = scooter_info.strip()

        if not full_name:
            raise HTTPException(400, "Ism kiritilishi shart")
        if not scooter_info:
            raise HTTPException(400, "Skuter ma'lumoti kiritilishi shart")
        if daily_rate <= 0:
            raise HTTPException(400, "Kunlik narx musbat bo'lishi kerak")

        selfie_url = await save_video(video_selfie, "selfie")
        scooter_url = await save_video(video_scooter, "scooter")

        rental = Rental(
            full_name=full_name,
            phone=phone,
            passport=passport.strip() or None,
            scooter_info=scooter_info,
            daily_rate=daily_rate,
            payment_type=payment_type,
            notes=notes.strip() or None,
            video_selfie=selfie_url,
            video_scooter=scooter_url,
            status=RentalStatus.PENDING,
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
    x_admin_token: str = Header("", alias="X-Admin-Token"),
):
    db = SessionLocal()
    try:
        require_admin_api(db, init_data, x_admin_token)

        if amount <= 0:
            raise HTTPException(400, "Summa musbat bo'lishi kerak")

        rental = db.query(Rental).filter(Rental.id == rental_id).first()
        if not rental:
            raise HTTPException(404, "Mijoz topilmadi")
        if rental.status != RentalStatus.ACTIVE:
            raise HTTPException(400, "Ijara faol emas")

        days_covered = amount / rental.daily_rate
        base = rental.paid_until if rental.paid_until and rental.paid_until >= date.today() else date.today()
        rental.paid_until = base + timedelta(days=days_covered)

        db.add(Payment(
            rental_id=rental.id,
            amount=amount,
            days_covered=days_covered,
            method=method,
            note=note.strip() or None,
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
    x_admin_token: str = Header("", alias="X-Admin-Token"),
):
    db = SessionLocal()
    try:
        require_admin_api(db, init_data, x_admin_token)
        rental = db.query(Rental).filter(Rental.id == rental_id).first()
        if not rental:
            raise HTTPException(404, "Topilmadi")
        rental.status = RentalStatus.FINISHED
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


@app.delete("/api/admin/rentals/{rental_id}")
def delete_rental(
    rental_id: int,
    init_data: str = "",
    x_admin_token: str = Header("", alias="X-Admin-Token"),
):
    """Xato kiritilgan (masalan hali faollashmagan) yozuvni butunlay o'chirish."""
    db = SessionLocal()
    try:
        require_admin_api(db, init_data, x_admin_token)
        rental = db.query(Rental).filter(Rental.id == rental_id).first()
        if not rental:
            raise HTTPException(404, "Topilmadi")
        if rental.status == RentalStatus.ACTIVE:
            raise HTTPException(400, "Faol ijarani o'chirib bo'lmaydi — avval yakunlang")
        db.delete(rental)
        db.commit()
        log.info(f"🗑 O'chirildi: id={rental_id}")
        return {"ok": True}
    finally:
        db.close()


# ==================== STATIC ====================
def mount_static():
    init_db()
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

    # ✅ webapp papkasi mavjudligini tekshirish
    if os.path.isdir("webapp"):
        app.mount("/", StaticFiles(directory="webapp", html=True), name="webapp")
    else:
        log.warning("⚠️ 'webapp' papkasi topilmadi — statik fayllar xizmat qilmaydi")


mount_static()
