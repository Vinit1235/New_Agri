"""/api/devices — register and link devices to fields.

Devices are owned by the field's owner. The plaintext token is returned ONLY once
at registration; afterwards only the hashed value is stored.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import (
    generate_device_token,
    get_current_user,
    hash_device_token,
)
from ..database import get_db

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post("/register", response_model=schemas.DeviceWithToken, status_code=201)
def register_device(
    payload: schemas.DeviceRegister,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # device_id must be globally unique
    if db.query(models.Device).filter(models.Device.device_id == payload.device_id).first():
        raise HTTPException(status_code=400, detail="device_id already registered")

    # If a field is specified, it must belong to the user
    if payload.field_id is not None:
        f = (
            db.query(models.Field)
            .filter(models.Field.id == payload.field_id, models.Field.user_id == user.id)
            .first()
        )
        if not f:
            raise HTTPException(status_code=404, detail="Field not found")

    plaintext = generate_device_token()
    device = models.Device(
        device_id=payload.device_id,
        name=payload.name,
        token_hash=hash_device_token(plaintext),
        field_id=payload.field_id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    return schemas.DeviceWithToken(
        id=device.id,
        device_id=device.device_id,
        name=device.name,
        field_id=device.field_id,
        last_seen=device.last_seen,
        created_at=device.created_at,
        token=plaintext,  # only time it's ever returned
    )


@router.post("/{device_pk}/link", response_model=schemas.DeviceOut)
def link_device(
    device_pk: int,
    payload: schemas.DeviceLink,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Link/unlink a device to a field. Pass field_id=null to unlink."""
    device = db.query(models.Device).filter(models.Device.id == device_pk).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # If linking, verify the user owns the field
    if payload.field_id is not None:
        f = (
            db.query(models.Field)
            .filter(models.Field.id == payload.field_id, models.Field.user_id == user.id)
            .first()
        )
        if not f:
            raise HTTPException(status_code=404, detail="Field not found")

    device.field_id = payload.field_id
    db.commit()
    db.refresh(device)
    return device


@router.get("", response_model=list[schemas.DeviceOut])
def list_my_devices(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all devices linked to fields owned by the current user."""
    return (
        db.query(models.Device)
        .join(models.Field, models.Field.id == models.Device.field_id)
        .filter(models.Field.user_id == user.id)
        .order_by(models.Device.id.asc())
        .all()
    )
