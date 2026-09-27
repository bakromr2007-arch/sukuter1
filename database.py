from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DATABASE_URL

db_url = DATABASE_URL
if db_url.startswith("postgres://"):
    # Render eski "postgres://" formatini beradi, SQLAlchemy "postgresql://" talab qiladi
    db_url = db_url.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
engine = create_engine(db_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db():
    import models  # noqa: F401 (jadvallarni ro'yxatdan o'tkazish uchun)
    Base.metadata.create_all(bind=engine)
