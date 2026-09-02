"""/api/auth — register and login."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenOut, status_code=201)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        category=payload.category,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token, expires_in = create_access_token(subject=str(user.id))
    return schemas.TokenOut(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=schemas.UserOut.model_validate(user),
    )


@router.post("/login", response_model=schemas.TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 form login (frontend posts application/x-www-form-urlencoded)."""
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token, expires_in = create_access_token(subject=str(user.id))
    return schemas.TokenOut(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=schemas.UserOut.model_validate(user),
    )


@router.post("/login-json", response_model=schemas.TokenOut)
def login_json(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    """Same as /login but takes a JSON body — convenient for the JS dashboard."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token, expires_in = create_access_token(subject=str(user.id))
    return schemas.TokenOut(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=schemas.UserOut.model_validate(user),
    )


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user
