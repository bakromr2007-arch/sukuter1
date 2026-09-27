import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(f"❌ {key} .env da ko'rsatilmagan!")
    return val


# ---------- Bot ----------
BOT_TOKEN = _require("BOT_TOKEN")
BOT_USERNAME = _require("BOT_USERNAME").lstrip("@")

# ---------- Adminlar (bir yoki bir nechta) ----------
_admin_raw = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID") or ""
ADMIN_IDS = {int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()}

if not ADMIN_IDS:
    raise RuntimeError("❌ ADMIN_IDS .env da ko'rsatilmagan yoki noto'g'ri!")

# Orqaga moslik uchun
ADMIN_ID = next(iter(ADMIN_IDS))

# ---------- WebApp ----------
WEBAPP_URL = _require("WEBAPP_URL").rstrip("/")
if not WEBAPP_URL.startswith("https://"):
    raise RuntimeError("❌ WEBAPP_URL https:// bilan boshlanishi shart!")

# ---------- Database ----------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///scooter.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

# ---------- Debug ----------
if os.getenv("DEBUG_AUTH", "0") == "1":
    import logging
    logging.basicConfig(level=logging.INFO)
    logging.info(f"✅ ADMIN_IDS: {ADMIN_IDS}")
    logging.info(f"✅ WEBAPP_URL: {WEBAPP_URL}")
    logging.info(f"✅ BOT_USERNAME: @{BOT_USERNAME}")
