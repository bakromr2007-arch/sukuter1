"""
Markazlashgan konfiguratsiya.
Barcha muhit o'zgaruvchilari shu yerda o'qiladi va tekshiriladi —
noto'g'ri sozlash ilova ishga tushmasdan oldin aniq xato bilan to'xtaydi.
"""
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("config")


def _fail(msg: str):
    # Ilova buzilgan holatda jimgina ishga tushmasligi kerak — aniq xato bilan to'xtaydi.
    print(f"\n❌ KONFIGURATSIYA XATOSI: {msg}\n", file=sys.stderr)
    sys.exit(1)


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        _fail(f"'{key}' .env faylida ko'rsatilmagan yoki bo'sh!")
    return val


def _optional_int(key: str, default: int) -> int:
    val = os.getenv(key, "").strip()
    if not val:
        return default
    if not val.lstrip("-").isdigit():
        _fail(f"'{key}' butun son bo'lishi kerak, olindi: {val!r}")
    return int(val)


def _optional_str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ---------- Bot ----------
BOT_TOKEN = _require("BOT_TOKEN")
BOT_USERNAME = _require("BOT_USERNAME").lstrip("@")

# ---------- Adminlar ----------
# Ikkala format ham qo'llab-quvvatlanadi:
#   ADMIN_ID=123456789                (bitta admin)
#   ADMIN_IDS=123456789,987654321     (bir nechta admin, vergul bilan)
_admin_raw = (os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID") or "").strip()
if not _admin_raw:
    _fail(
        "Kamida bitta admin ID kerak. .env fayliga ADMIN_ID=SIZNING_TELEGRAM_ID "
        "qo'shing (ID'ni @userinfobot orqali bilib olasiz)."
    )

_admin_ids = set()
for part in _admin_raw.split(","):
    part = part.strip()
    if not part:
        continue
    if not part.lstrip("-").isdigit():
        _fail(f"ADMIN_ID/ADMIN_IDS noto'g'ri qiymat: {part!r} — faqat raqam bo'lishi kerak.")
    _admin_ids.add(int(part))

if not _admin_ids:
    _fail("ADMIN_ID/ADMIN_IDS bo'sh — hech bo'lmasa bitta to'g'ri Telegram ID kiriting.")

ADMIN_IDS = frozenset(_admin_ids)
ADMIN_ID = next(iter(ADMIN_IDS))  # eski kodlar bilan moslik uchun

# ---------- Admin parol (fallback kirish usuli) ----------
ADMIN_PASSWORD = _optional_str("ADMIN_PASSWORD") or None
if ADMIN_PASSWORD is None:
    log.warning(
        "⚠️ ADMIN_PASSWORD o'rnatilmagan — parol orqali kirish o'chirilgan, "
        "faqat Telegram initData orqali kirish ishlaydi."
    )

# ---------- WebApp ----------
WEBAPP_URL = _require("WEBAPP_URL").rstrip("/")
if not WEBAPP_URL.startswith("https://"):
    _fail("WEBAPP_URL https:// bilan boshlanishi shart (Telegram WebApp buni talab qiladi)!")

# ---------- Database ----------
DATABASE_URL = _optional_str("DATABASE_URL", "sqlite:///./data/scooter.db")
UPLOAD_DIR = _optional_str("UPLOAD_DIR", "uploads")

# ---------- Yuklama (video) cheklovlari ----------
MAX_UPLOAD_MB = _optional_int("MAX_UPLOAD_MB", 50)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".3gp", ".avi", ".mkv"}
ALLOWED_VIDEO_CONTENT_TYPES = {
    "video/mp4", "video/quicktime", "video/webm", "video/3gpp",
    "video/x-msvideo", "video/x-matroska",
}

# ---------- Telegram initData amal qilish muddati ----------
INIT_DATA_MAX_AGE_SECONDS = _optional_int("INIT_DATA_MAX_AGE_SECONDS", 86400)
ADMIN_SESSION_TTL_SECONDS = _optional_int("ADMIN_SESSION_TTL_SECONDS", 86400)

# ---------- Login urinishlarini cheklash ----------
LOGIN_MAX_ATTEMPTS = _optional_int("LOGIN_MAX_ATTEMPTS", 5)
LOGIN_LOCKOUT_SECONDS = _optional_int("LOGIN_LOCKOUT_SECONDS", 300)

# ---------- CORS ----------
# Bo'sh bo'lsa — hamma joyga ruxsat (dev uchun qulay, prodda WEBAPP_URL bilan cheklash tavsiya etiladi)
_cors_raw = os.getenv("CORS_ORIGINS", "").strip()
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()] or ["*"]

# ---------- Log darajasi ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------- Eslatma vaqti (soat:daqiqa, UTC) ----------
REMINDER_HOUR_UTC = _optional_int("REMINDER_HOUR_UTC", 4)   # 09:00 Toshkent = 04:00 UTC
REMINDER_MINUTE_UTC = _optional_int("REMINDER_MINUTE_UTC", 0)

# ---------- Server porti ----------
# Render $PORT env o'zgaruvchisini beradi (odatda 10000).
# Lokal ishlatish uchun default 8000.
PORT = _optional_int("PORT", 8000)

# ---------- Debug ----------
DEBUG = os.getenv("DEBUG", "0").strip() in ("1", "true", "True", "yes", "YES")

if DEBUG:
    logging.basicConfig(level=LOG_LEVEL)
    log.info("=== CONFIG ===")
    log.info(f"BOT_USERNAME: @{BOT_USERNAME}")
    log.info(f"ADMIN_IDS: {sorted(ADMIN_IDS)}")
    log.info(f"ADMIN_PASSWORD: {'✓' if ADMIN_PASSWORD else '✗'}")
    log.info(f"WEBAPP_URL: {WEBAPP_URL}")
    log.info(f"DATABASE_URL: {DATABASE_URL}")
    log.info(f"UPLOAD_DIR: {UPLOAD_DIR}")
    log.info(f"PORT: {PORT}")
    log.info(f"CORS_ORIGINS: {CORS_ORIGINS}")
    log.info(f"REMINDER: {REMINDER_HOUR_UTC:02d}:{REMINDER_MINUTE_UTC:02d} UTC")
    log.info("==============")
