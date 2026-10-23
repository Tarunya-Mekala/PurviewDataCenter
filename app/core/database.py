import logging
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger("ai_datacenter.database")

# Ensure base data folders exist
for folder in [settings.UPLOAD_DIR, settings.EXTRACTED_DIR, settings.PROCESSED_DIR, settings.REPORT_DIR]:
    Path(folder).mkdir(parents=True, exist_ok=True)


def _init_engine():
    target_url = settings.DATABASE_URL
    connect_args = {}
    is_sqlite = target_url.startswith("sqlite")

    if is_sqlite:
        connect_args = {"check_same_thread": False}

    pool_kwargs = {}
    if not is_sqlite:
        pool_kwargs = {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE,
        }

    try:
        eng = create_engine(
            target_url,
            connect_args=connect_args,
            pool_pre_ping=not is_sqlite,
            **pool_kwargs,
        )
        # Test connection
        with eng.connect():
            pass
        return eng
    except Exception as e:
        if not is_sqlite:
            logger.warning(
                f"Could not connect to PostgreSQL ({e}). Falling back to local SQLite database in ./data/ai_datacenter.db"
            )
            fallback_path = Path(settings.UPLOAD_DIR).parent / "ai_datacenter.db"
            sqlite_url = f"sqlite:///{fallback_path}"
            return create_engine(
                sqlite_url,
                connect_args={"check_same_thread": False},
                pool_pre_ping=False,
            )
        raise e


engine = _init_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()