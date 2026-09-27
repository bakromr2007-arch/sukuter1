import hashlib
import hmac
import json
import os
import shutil
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl

import httpx
from fastapi import FastAPI, HTTPException, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import BOT_TOKEN, ADMIN_ID, BOT_USERNAME
from database import SessionLocal, init_db
from models import Rental, Payment

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def check_telegram_auth(init_data: str) -> dict:
    """Telegram WebApp initData'ni HMAC orqali tekshiradi (soxta kirishning oldini oladi)."""
    parsed = dict(parse_qsl(init_data))
    received_hash = parsed.pop("hash", None)
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not received_hash or computed_hash != received_hash:
        raise HTTPException(status_code=401, detail="Ruxsat etilmagan")
    return json.loads(parsed.get("user", "{}"))


def require_admin(init_data: str) -> dict:
    user = check_telegram_auth(init_data)
    if user.get("id") != ADMIN_ID:
        raise HTTPException(status_code=403, detail="Faqat admin uchun")
    return user


def notify_user(chat_id: int, text: str):
    try:
        httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
    except Exception:
        pass


def serialize_rental(r: Rental) -> dict:
    return {
        "id": r.id,
        "full_name": r.full_name,
        "phone": r.phone,
        "scooter_info": r.scooter_info,
        "daily_rate": r.daily_rate,
        "status": r.status,
        "start_date": r.start_date.strftime("%d.%m.%Y"),
        "paid_until": r.paid_until.strftime("%d.%m.%Y"),
        "total_paid": r.total_paid(),
        "debt": r.debt_amount(),
        "debt_days": r.debt_days(),
        "reg_link": f"https://t.me/{BOT_USERNAME}?start=reg_{r.id}" if r.status == "kutilmoqda" else None,
    }


# ---------------- Kim ekanini aniqlash ----------------
@app.get("/api/whoami")
def whoami(init_data: str):
    user = check_telegram_auth(init_data)
    return {"is_admin": user.get("id") == ADMIN_ID, "name": user.get("first_name", "")}


# ---------------- Ijarachi: o'zi haqida ----------------
@app.get("/api/me")
def get_me(init_data: str):
    user = check_telegram_auth(init_data)
    telegram_id = user.get("id")
    db = SessionLocal()
    try:
        rental = db.query(Rental).filter(Rental.telegram_id == telegram_id).first()
        if not rental:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
        data = serialize_rental(rental)
        data["payments"] = [
            {
                "amount": p.amount,
                "date": p.date.strftime("%d.%m.%Y"),
                "days_covered": round(p.days_covered, 1),
            }
            for p in rental.payments
        ]
        return data
    finally:
        db.close()


# ---------------- Admin: mijozlar ro'yxati ----------------
@app.get("/api/admin/rentals")
def admin_rentals(init_data: str):
    require_admin(init_data)
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


# ---------------- Admin: yangi mijoz qo'shish ----------------
@app.post("/api/admin/rentals")
async def create_rental(
    init_data: str = Form(...),
    full_name: str = Form(...),
    phone: str = Form(...),
    scooter_info: str = Form(...),
    daily_rate: float = Form(...),
    video: UploadFile = File(None),
):
    require_admin(init_data)
    db = SessionLocal()
    try:
        video_path = None
        if video is not None and video.filename:
            ext = os.path.splitext(video.filename)[1] or ".mp4"
            fname = f"{int(datetime.utcnow().timestamp())}{ext}"
            full_path = os.path.join(UPLOAD_DIR, fname)
            with open(full_path, "wb") as f:
                shutil.copyfileobj(video.file, f)
            video_path = f"/uploads/{fname}"

        rental = Rental(
            full_name=full_name,
            phone=phone,
            scooter_info=scooter_info,
            daily_rate=daily_rate,
            video_file_id=video_path,
            status="kutilmoqda",
        )
        db.add(rental)
        db.commit()
        db.refresh(rental)
        return serialize_rental(rental)
    finally:
        db.close()


# ---------------- Admin: to'lov qayd qilish ----------------
@app.post("/api/admin/payments")
async def create_payment(
    init_data: str = Form(...),
    rental_id: int = Form(...),
    amount: float = Form(...),
):
    require_admin(init_data)
    db = SessionLocal()
    try:
        rental = db.query(Rental).filter(Rental.id == rental_id).first()
        if not rental:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")

        days_covered = amount / rental.daily_rate
        base = rental.paid_until if rental.paid_until >= date.today() else date.today()
        rental.paid_until = base + timedelta(days=days_covered)
        db.add(Payment(rental_id=rental.id, amount=amount, days_covered=days_covered))
        db.commit()
        db.refresh(rental)

        if rental.telegram_id:
            notify_user(
                rental.telegram_id,
                f"✅ To'lovingiz qabul qilindi: {amount:,.0f} so'm\n"
                f"Endi {rental.paid_until.strftime('%d.%m.%Y')} sanagacha to'lovingiz yopilgan.",
            )
        return serialize_rental(rental)
    finally:
        db.close()


init_db()
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/", StaticFiles(directory="webapp", html=True), name="webapp")
