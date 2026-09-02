"""/api/fields/{id}/... — readings, events, latest values (for the frontend)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/api/fields", tags=["data"])


def _owned_field(field_id: int, user: models.User, db: Session) -> models.Field:
    f = (
        db.query(models.Field)
        .filter(models.Field.id == field_id, models.Field.user_id == user.id)
        .first()
    )
    if not f:
        raise HTTPException(status_code=404, detail="Field not found")
    return f


def _serialize_reading(r: models.SensorReading) -> schemas.ReadingOut:
    return schemas.ReadingOut(
        id=r.id,
        moisture=r.moisture,
        temperature=r.temperature,
        ph=r.ph,
        ec=r.ec,
        timestamp=r.timestamp,
        device_id=r.device.device_id if r.device else "",
    )


def _serialize_event(e: models.AutomationEvent) -> schemas.EventOut:
    return schemas.EventOut(
        id=e.id,
        action=e.action,
        action_name=e.action_name,
        pump=e.pump,
        fertilizer=e.fertilizer,
        timestamp=e.timestamp,
        device_id=e.device.device_id if e.device else None,
    )


# ---------------------------------------------------------------------------
# Latest reading
# ---------------------------------------------------------------------------
@router.get("/{field_id}/readings/latest", response_model=schemas.ReadingOut)
def latest_reading(
    field_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned_field(field_id, user, db)
    r = (
        db.query(models.SensorReading)
        .options(joinedload(models.SensorReading.device))
        .filter(models.SensorReading.field_id == field_id)
        .order_by(models.SensorReading.timestamp.desc())
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="No readings yet for this field")
    return _serialize_reading(r)


# ---------------------------------------------------------------------------
# Reading range
# ---------------------------------------------------------------------------
@router.get("/{field_id}/readings", response_model=List[schemas.ReadingOut])
def list_readings(
    field_id: int,
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned_field(field_id, user, db)
    q = (
        db.query(models.SensorReading)
        .options(joinedload(models.SensorReading.device))
        .filter(models.SensorReading.field_id == field_id)
    )
    if from_ is not None:
        q = q.filter(models.SensorReading.timestamp >= from_)
    if to is not None:
        q = q.filter(models.SensorReading.timestamp <= to)
    q = q.order_by(models.SensorReading.timestamp.asc()).limit(limit)
    return [_serialize_reading(r) for r in q.all()]


# ---------------------------------------------------------------------------
# Automation events
# ---------------------------------------------------------------------------
@router.get("/{field_id}/events", response_model=List[schemas.EventOut])
def list_events(
    field_id: int,
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned_field(field_id, user, db)
    q = (
        db.query(models.AutomationEvent)
        .options(joinedload(models.AutomationEvent.device))
        .filter(models.AutomationEvent.field_id == field_id)
    )
    if from_ is not None:
        q = q.filter(models.AutomationEvent.timestamp >= from_)
    if to is not None:
        q = q.filter(models.AutomationEvent.timestamp <= to)
    q = q.order_by(models.AutomationEvent.timestamp.desc()).limit(limit)
    return [_serialize_event(e) for e in q.all()]
