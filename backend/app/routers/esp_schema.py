"""/api/esp/schema — Dynamic Configuration Schema Feed for ESP32 Field Nodes."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_device_by_token
from ..database import get_db

router = APIRouter(prefix="/api/esp", tags=["esp-schema"])

# Agronomic crop preset defaults
CROP_THRESHOLDS = {
    "tomato": {"min_moisture": 28.0, "target_moisture": 65.0, "max_runtime": 180},
    "wheat": {"min_moisture": 22.0, "target_moisture": 50.0, "max_runtime": 240},
    "rice": {"min_moisture": 50.0, "target_moisture": 85.0, "max_runtime": 360},
    "cotton": {"min_moisture": 20.0, "target_moisture": 45.0, "max_runtime": 180},
    "sugarcane": {"min_moisture": 35.0, "target_moisture": 70.0, "max_runtime": 300},
    "general": {"min_moisture": 25.0, "target_moisture": 60.0, "max_runtime": 180},
}


def _extract_token(authorization: Optional[str], x_esp_token: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    if x_esp_token:
        return x_esp_token.strip()
    return None


@router.get("/schema")
def get_esp_schema(
    response: Response,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
    x_esp_token: Optional[str] = Header(default=None, alias="X-ESP-TOKEN"),
    x_esp_checksum: Optional[str] = Header(default=None, alias="X-ESP-CHECKSUM"),
):
    """
    Returns the dynamic JSON schema tailored for the querying ESP32 device.
    Supports HTTP 304 Not Modified when X-ESP-CHECKSUM matches.
    """
    token = _extract_token(authorization, x_esp_token)
    device: Optional[models.Device] = None
    field: Optional[models.Field] = None

    if token:
        device = get_device_by_token(token, db)
        if device and device.field_id:
            field = db.query(models.Field).filter(models.Field.id == device.field_id).first()

    crop_name = (field.crop_type if field and field.crop_type else "Tomato").capitalize()
    crop_key = crop_name.lower()
    crop_rule = CROP_THRESHOLDS.get(crop_key, CROP_THRESHOLDS["general"])

    # Compute a deterministic checksum based on crop & thresholds
    checksum_raw = f"{crop_name}-{crop_rule['min_moisture']}-{crop_rule['target_moisture']}-{crop_rule['max_runtime']}"
    checksum = "CRC-" + hashlib.md5(checksum_raw.encode()).hexdigest()[:8].upper()

    # Deduplication check: return 304 if already current
    if x_esp_checksum and x_esp_checksum.strip() == checksum:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    schema_doc = {
        "schema_version": "3.0.0",
        "device_id": device.device_id if device else "esp32-01",
        "zone_id": f"zone_{field.id:02d}" if field else "zone_01",
        "crop_profile": {
            "crop_name": crop_name,
            "stage": field.health_status or "Vegetative" if field else "Vegetative",
        },
        "thresholds": {
            "min_moisture_pct": crop_rule["min_moisture"],
            "target_moisture_pct": crop_rule["target_moisture"],
            "critical_wilting_pct": 15.0,
            "saturation_cutoff_pct": 85.0,
            "max_ec_dsm": 2.5,
            "temp_min_c": 16.0,
            "temp_max_c": 36.0,
        },
        "actuation_rules": {
            "max_pump_runtime_sec": crop_rule["max_runtime"],
            "soak_delay_sec": 180,
            "pulse_mode_enabled": False,
            "pulse_on_seconds": 120,
            "pulse_rest_seconds": 60,
        },
        "hardware_pins": {
            "moisture_adc_pin": 32,
            "soil_power_pin": 25,
            "pump_relay_pin": 23,
            "fertilizer_valve_pin": 22,
            "flow_sensor_pin": 27,
            "turbidity_pin": 34,
            "adc_dry_reading": 3300,
            "adc_wet_reading": 1400,
        },
        "edge_operating": {
            "check_interval_sec": 10,
            "telemetry_publish_interval_sec": 5,
            "schema_checksum": checksum,
        },
    }

    return schema_doc


@router.post("/telemetry")
async def ingest_esp_telemetry(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Direct LAN / Cloud ingestion endpoint for ESP32 Field Nodes.
    Accepts raw JSON telemetry without requiring strict token headers.
    Auto-detects device, updates last_seen, records SensorReading and optional AutomationEvent.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    device_id_str = body.get("device_id") or "esp32-01"
    dev = db.query(models.Device).filter(models.Device.device_id == device_id_str).first()
    if not dev:
        dev = db.query(models.Device).filter(models.Device.device_id.like("%esp%")).first()

    dev_id = dev.id if dev else 1
    field_id = dev.field_id if (dev and dev.field_id) else 1

    now = datetime.utcnow()
    reading = models.SensorReading(
        moisture=body.get("moisture"),
        temperature=body.get("temperature"),
        humidity=body.get("humidity"),
        turbidity_ntu=body.get("turbidity_ntu"),
        flow_rate_lpm=body.get("flow_rate_lpm"),
        session_volume_L=body.get("session_volume_L"),
        total_volume_L=body.get("total_volume_L"),
        timestamp=now,
        device_id=dev_id,
        field_id=field_id,
    )
    db.add(reading)
    db.flush()

    if (
        body.get("action") is not None
        or body.get("action_name") is not None
        or body.get("pump")
        or body.get("fertilizer")
    ):
        event = models.AutomationEvent(
            action=body.get("action"),
            action_name=body.get("action_name"),
            pump=bool(body.get("pump")),
            fertilizer=bool(body.get("fertilizer")),
            flow_rate_lpm=body.get("flow_rate_lpm"),
            session_volume_L=body.get("session_volume_L"),
            total_volume_L=body.get("total_volume_L"),
            timestamp=now,
            device_id=dev_id,
            field_id=field_id,
        )
        db.add(event)
        db.flush()

    if dev:
        dev.last_seen = now
    db.commit()

    return {
        "ok": True,
        "status": "REAL HARDWARE ONLINE",
        "reading_id": reading.id,
        "device_id": device_id_str,
        "field_id": field_id,
    }


@router.get("/status")
def get_esp_status(db: Session = Depends(get_db)):
    """Check hardware connectivity state for dashboard badge."""
    dev = db.query(models.Device).filter(models.Device.device_id == "esp32-01").first()
    latest_r = (
        db.query(models.SensorReading)
        .order_by(models.SensorReading.timestamp.desc())
        .first()
    )
    is_online = False
    age_sec = None
    if latest_r and latest_r.timestamp:
        age_sec = (datetime.utcnow() - latest_r.timestamp).total_seconds()
        is_online = age_sec < 35
    return {
        "device_id": dev.device_id if dev else "esp32-01",
        "online": is_online,
        "age_seconds": round(age_sec, 1) if age_sec is not None else None,
        "last_seen": dev.last_seen if dev else (latest_r.timestamp if latest_r else None),
        "status": "REAL HARDWARE ONLINE" if is_online else "OFFLINE",
    }

