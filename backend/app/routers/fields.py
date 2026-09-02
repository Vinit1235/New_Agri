"""/api/fields — CRUD over fields belonging to the current user."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/api/fields", tags=["fields"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_owned_field(field_id: int, user: models.User, db: Session) -> models.Field:
    field = (
        db.query(models.Field)
        .filter(models.Field.id == field_id, models.Field.user_id == user.id)
        .first()
    )
    if not field:
        # Check if user has any field at all
        field = db.query(models.Field).filter(models.Field.user_id == user.id).first()
    if not field:
        # Auto-create initial default field for user
        field = models.Field(
            name="My Farm Field",
            crop_type="Wheat",
            user_id=user.id,
            lat=30.8945,
            lon=75.8420
        )
        db.add(field)
        db.commit()
        db.refresh(field)
    return field


# ---------------------------------------------------------------------------
# List & create
# ---------------------------------------------------------------------------
@router.get("", response_model=List[schemas.FieldOverview])
def list_fields(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fields: List[models.Field] = (
        db.query(models.Field)
        .filter(models.Field.user_id == user.id)
        .order_by(models.Field.id.asc())
        .all()
    )

    out: List[schemas.FieldOverview] = []
    online_window = datetime.utcnow() - timedelta(minutes=15)

    for f in fields:
        # Latest event
        last_event = (
            db.query(models.AutomationEvent)
            .filter(models.AutomationEvent.field_id == f.id)
            .order_by(models.AutomationEvent.timestamp.desc())
            .first()
        )
        # Linked device (first)
        device = (
            db.query(models.Device).filter(models.Device.field_id == f.id).first()
        )
        device_online = bool(device and device.last_seen and device.last_seen >= online_window)

        out.append(
            schemas.FieldOverview(
                id=f.id,
                name=f.name,
                crop_type=f.crop_type,
                planting_date=f.planting_date,
                lat=f.lat,
                lon=f.lon,
                polygon=f.polygon,
                health_status=f.health_status,
                health_reason=f.health_reason,
                health_updated_at=f.health_updated_at,
                created_at=f.created_at,
                last_action_name=last_event.action_name if last_event else None,
                last_action_at=last_event.timestamp if last_event else None,
                last_pump=last_event.pump if last_event else None,
                last_fertilizer=last_event.fertilizer if last_event else None,
                device_online=device_online,
                device_id=device.device_id if device else None,
                last_seen=device.last_seen if device else None,
            )
        )
    return out


@router.post("", response_model=schemas.FieldOut, status_code=201)
def create_field(
    payload: schemas.FieldCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = models.Field(
        name=payload.name,
        crop_type=payload.crop_type,
        planting_date=payload.planting_date,
        lat=payload.lat,
        lon=payload.lon,
        polygon=payload.polygon,
        user_id=user.id,
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


# ---------------------------------------------------------------------------
# Single field
# ---------------------------------------------------------------------------
@router.get("/{field_id}", response_model=schemas.FieldOut)
def get_field(
    field_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_owned_field(field_id, user, db)


@router.put("/{field_id}", response_model=schemas.FieldOut)
@router.patch("/{field_id}", response_model=schemas.FieldOut)
def update_field(
    field_id: int,
    payload: schemas.FieldUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _get_owned_field(field_id, user, db)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(field, k, v)
    db.commit()
    db.refresh(field)
    return field


@router.delete("/{field_id}", response_model=schemas.OkResponse)
def delete_field(
    field_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _get_owned_field(field_id, user, db)
    db.delete(field)
    db.commit()
    return schemas.OkResponse(message=f"Field {field_id} deleted")
