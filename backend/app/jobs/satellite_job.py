"""Background job that refreshes Sentinel NDVI/NDWI for every field on a 5-day cadence."""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from .. import models
from ..database import SessionLocal
from ..services.health_rules import compute_health
from ..services.sentinel import get_client

logger = logging.getLogger("soiledge.satellite_job")


def refresh_field_satellite(db: Session, field: models.Field) -> Optional[models.SatelliteObservation]:
    """Fetch new indices for one field, persist + update field health."""
    try:
        client = get_client()
        indices = client.fetch_indices(field)
    except Exception as e:  # noqa: BLE001
        logger.exception("Sentinel fetch failed for field %s: %s", field.id, e)
        return None

    if indices.ndvi is None and indices.ndwi is None:
        logger.warning("No indices returned for field %s", field.id)
        return None

    # Previous observation for trend
    prev = (
        db.query(models.SatelliteObservation)
        .filter(models.SatelliteObservation.field_id == field.id)
        .order_by(models.SatelliteObservation.date.desc())
        .first()
    )

    # Latest soil reading for cross-modality reasoning
    latest_reading = (
        db.query(models.SensorReading)
        .filter(models.SensorReading.field_id == field.id)
        .order_by(models.SensorReading.timestamp.desc())
        .first()
    )

    verdict = compute_health(
        crop_type=field.crop_type,
        planting_date=field.planting_date,
        ndvi=indices.ndvi,
        ndwi=indices.ndwi,
        cloud_pct=indices.cloud_pct,
        prev_ndvi=prev.ndvi if prev else None,
        latest_moisture=latest_reading.moisture if latest_reading else None,
        latest_ec=latest_reading.ec if latest_reading else None,
    )

    obs = models.SatelliteObservation(
        date=indices.scene_date or date.today(),
        ndvi=indices.ndvi,
        ndwi=indices.ndwi,
        cloud_pct=indices.cloud_pct,
        health_status=verdict.status,
        reason=verdict.reason,
        source=indices.source,
        field_id=field.id,
    )
    db.add(obs)
    field.health_status = verdict.status
    field.health_reason = verdict.reason
    field.health_updated_at = obs.date
    db.commit()
    db.refresh(obs)
    logger.info("Satellite refresh: field=%s ndvi=%.2f ndwi=%.2f -> %s",
                field.id, indices.ndvi or -1, indices.ndwi or -1, verdict.status)
    return obs


def refresh_all_fields() -> int:
    """Refresh every field. Returns the number of fields successfully refreshed."""
    db: Session = SessionLocal()
    refreshed = 0
    try:
        fields = db.query(models.Field).all()
        for f in fields:
            try:
                if refresh_field_satellite(db, f) is not None:
                    refreshed += 1
            except Exception:
                logger.exception("Refresh failed for field %s", f.id)
    finally:
        db.close()
    return refreshed


_scheduler: Optional[BackgroundScheduler] = None


def start_scheduler(interval_days: int = 5) -> BackgroundScheduler:
    """Start the background scheduler. Idempotent — safe to call from main.py."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        refresh_all_fields,
        trigger=IntervalTrigger(days=interval_days),
        id="satellite_refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _scheduler = sched
    logger.info("Satellite scheduler started (every %d day(s))", interval_days)
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
