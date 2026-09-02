"""/api/health — liveness probe for the backend itself."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from .. import models
from ..config import get_settings
from ..database import get_db

router = APIRouter(prefix="/api", tags=["server"])
settings = get_settings()


@router.get("/health")
def server_health(db: Session = Depends(get_db)):
    db_ok = True
    db_error: str | None = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        db_ok = False
        db_error = str(e)

    return {
        "ok": db_ok,
        "app": settings.app_name,
        "env": settings.app_env,
        "time": datetime.utcnow().isoformat() + "Z",
        "database_ok": db_ok,
        "db_error": db_error,
    }
