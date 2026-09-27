import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(f"❌ {key} .env da ko'rsatilmagan!")
    return val


BOT_TOKEN = _require("BOT_TOKEN")
BOT_USERNAME = _require("BOT_USERNAME").lstrip("@")
ADMIN_ID = int(_require("ADMIN_ID"))

WEBAPP_URL = _require("WEBAPP_URL").rstrip("/")
if not WEBAPP_URL.startswith("https://"):
    raise RuntimeError("❌ WEBAPP_URL https:// bilan boshlanishi shart!")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///scooter.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
