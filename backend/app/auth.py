"""Authentication helpers: password hashing, JWT, and FastAPI dependencies."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from . import models

settings = get_settings()

# pwd_context is the standard passlib bcrypt wrapper
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Where the OAuth2PasswordBearer looks for the Bearer token.
# The frontend typically sends "Authorization: Bearer <jwt>".
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def create_access_token(subject: str, extra: Optional[dict] = None) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    expire_seconds = settings.access_token_expire_minutes * 60
    expire_at = datetime.utcnow() + timedelta(seconds=expire_seconds)
    payload: dict = {
        "sub": subject,                 # user id (as string) or "device:<device_id>"
        "exp": expire_at,
        "iat": datetime.utcnow(),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return token, expire_seconds


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    sub = payload.get("sub")
    if not sub or not str(sub).isdigit():
        raise HTTPException(status_code=401, detail="Bad token subject")

    user = db.query(models.User).filter(models.User.id == int(sub)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """Like get_current_user but returns None instead of raising if no token."""
    if not token:
        return None
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if not sub or not str(sub).isdigit():
            return None
        user = db.query(models.User).filter(models.User.id == int(sub)).first()
        return user
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Device token: stored as SHA-256 hash, plaintext shown only once at registration
# ---------------------------------------------------------------------------
def generate_device_token() -> str:
    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_device_by_token(
    token: str,
    db: Session,
) -> Optional[models.Device]:
    if not token:
        return None
    digest = hash_device_token(token)
    return db.query(models.Device).filter(models.Device.token_hash == digest).first()


# Simple in-memory rate limiter (per device, per minute).
# For production, swap for Redis.
_rate_window: dict[int, list[float]] = {}


def check_telemetry_rate(device_id: int, limit_per_min: int) -> bool:
    """Returns True if within rate limit, False if exceeded."""
    import time

    now = time.time()
    window_start = now - 60.0
    bucket = _rate_window.setdefault(device_id, [])
    # Drop old entries
    while bucket and bucket[0] < window_start:
        bucket.pop(0)
    if len(bucket) >= limit_per_min:
        return False
    bucket.append(now)
    return True
