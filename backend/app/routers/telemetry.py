"""/api/telemetry — ingestion endpoint for the ESP32 field node.

Authentication: device token is sent via either:
  * Authorization: Bearer <device_token>   (preferred)
  * X-Device-Token: <device_token>         (header fallback)

The device sends a sensor reading + its automation decision. We persist
both and bump the device's `last_seen`. The field comes from the device
record itself (field_id column), not from the request body.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import check_telemetry_rate, get_device_by_token
from ..config import get_settings
from ..database import get_db

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

settings = get_settings()


def _extract_device_token(
    authorization: Optional[str], x_device_token: Optional[str]
) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    if x_device_token:
        return x_device_token.strip()
    return None


@router.post("", response_model=schemas.TelemetryAck, status_code=201)
def ingest_telemetry(
    payload: schemas.TelemetryIn,
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
    x_device_token: Optional[str] = Header(default=None, alias="X-Device-Token"),
):
    token = _extract_device_token(authorization, x_device_token)
    if not token:
        raise HTTPException(status_code=401, detail="Missing device token")

    device = get_device_by_token(token, db)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid device token")

    # Token in payload must match the device id we authenticated
    if payload.device_id != device.device_id:
        raise HTTPException(
            status_code=400,
            detail="payload.device_id does not match authenticated device",
        )

    if not check_telemetry_rate(device.id, settings.telemetry_rate_per_min):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for device")

    ts = payload.timestamp or datetime.utcnow()

    reading = models.SensorReading(
        moisture=payload.moisture,
        temperature=payload.temperature,
        ph=payload.ph,
        ec=payload.ec,
        timestamp=ts,
        device_id=device.id,
        field_id=device.field_id,
    )
    db.add(reading)
    db.flush()  # assign reading.id

    event: Optional[models.AutomationEvent] = None
    # Only create an automation event if the ESP32 actually sent a decision
    if payload.action is not None or payload.action_name is not None or payload.pump or payload.fertilizer:
        event = models.AutomationEvent(
            action=payload.action,
            action_name=payload.action_name,
            pump=payload.pump,
            fertilizer=payload.fertilizer,
            timestamp=ts,
            device_id=device.id,
            field_id=device.field_id,
        )
        db.add(event)
        db.flush()

    device.last_seen = ts
    db.commit()
    db.refresh(reading)

    return schemas.TelemetryAck(
        ok=True,
        reading_id=reading.id,
        event_id=event.id if event else None,
        field_id=device.field_id,
    )
