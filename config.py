"""
Markazlashgan konfiguratsiya.
Barcha muhit o'zgaruvchilari shu yerda o'qiladi va tekshiriladi —
noto'g'ri sozlash ilova ishga tushmasdan oldin aniq xato bilan to'xtaydi.
"""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# MUHIM: barcha fayl yo'llari loyiha papkasiga nisbatan absolyut bo'lishi kerak,
# aks holda uvicorn boshqa papkadan ishga tushirilsa "webapp papkasi topilmadi"
# xatosi chiqadi.
BASE_DIR = Path(__file__).resolve().parent

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
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip() or None
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
# Nisbiy SQLite yo'lini absolyut qilamiz — CWD muammosini oldini oladi.
_db_url_env = os.getenv("DATABASE_URL", "").strip()
if not _db_url_env:
    DATABASE_URL = f"sqlite:///{BASE_DIR / 'data' / 'scooter.db'}"
elif _db_url_env.startswith("sqlite:///") and not _db_url_env.startswith("sqlite:////"):
    # sqlite:///./data/scooter.db → absolyut
    rel = _db_url_env[len("sqlite:///"):]
    if not os.path.isabs(rel):
        DATABASE_URL = f"sqlite:///{BASE_DIR / rel}"
    else:
        DATABASE_URL = _db_url_env
else:
    DATABASE_URL = _db_url_env

# ---------- Yuklama (video) ----------
_upload_env = os.getenv("UPLOAD_DIR", "").strip()
if _upload_env:
    UPLOAD_DIR = _upload_env if os.path.isabs(_upload_env) else str(BASE_DIR / _upload_env)
else:
    UPLOAD_DIR = str(BASE_DIR / "uploads")

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
_cors_raw = os.getenv("CORS_ORIGINS", "").strip()
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()] or ["*"]

# ---------- Log darajasi ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------- Eslatma vaqti (soat:daqiqa, UTC) ----------
REMINDER_HOUR_UTC = _optional_int("REMINDER_HOUR_UTC", 4)   # 09:00 Toshkent = 04:00 UTC
REMINDER_MINUTE_UTC = _optional_int("REMINDER_MINUTE_UTC", 0)
