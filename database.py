import logging
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DATABASE_URL, LOG_LEVEL

log = logging.getLogger("database")

db_url = DATABASE_URL
if db_url.startswith("postgres://"):
    # SQLAlchemy 1.4+ endi "postgres://" ni qabul qilmaydi
    db_url = db_url.replace("postgres://", "postgresql://", 1)

is_sqlite = db_url.startswith("sqlite")

if is_sqlite:
    path = db_url.replace("sqlite:///", "", 1)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)

connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_kwargs = dict(
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=(LOG_LEVEL == "DEBUG"),
)
if not is_sqlite:
    # Postgres uchun ulanishlar puli — bir nechta ishchi jarayon/so'rov ostida barqaror ishlaydi
    engine_kwargs.update(pool_size=10, max_overflow=20, pool_recycle=1800)

engine = create_engine(db_url, **engine_kwargs)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        # WAL rejimi — bir vaqtda o'qish/yozish tezligini va barqarorligini oshiradi
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def init_db():
    import models  # noqa: F401  (jadval metama'lumotlarini ro'yxatdan o'tkazish uchun)
    Base.metadata.create_all(bind=engine)
    log.info("✅ Baza jadvallari tayyor")
