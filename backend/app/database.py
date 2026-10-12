"""SQLAlchemy database setup."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from .config import get_settings

settings = get_settings()

# SQLite needs check_same_thread=False because FastAPI uses thread pool
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Session:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables and seed default demo accounts."""
    from . import models  # noqa: F401  (side-effect import)
    from .auth import hash_password

    Base.metadata.create_all(bind=engine)

    # Ensure default farmer account exists
    db = SessionLocal()
    try:
        farmer = db.query(models.User).filter(models.User.email == "farmer@soiledge.com").first()
        if not farmer:
            farmer = models.User(
                email="farmer@soiledge.com",
                password_hash=hash_password("farmer123"),
                full_name="Krishi Farmer",
            )
            db.add(farmer)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

