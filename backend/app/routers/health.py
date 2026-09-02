"""/api/fields/{id}/health and /api/fields/{id}/satellite

  * GET  /api/fields/{id}/satellite            — list of observations
  * GET  /api/fields/{id}/health              — current verdict + soil context
  * GET  /api/fields/{id}/health/trend        — last N points for the chart
  * POST /api/fields/{id}/satellite/refresh   — manual refresh (returns new obs)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..jobs.satellite_job import refresh_field_satellite
from ..services.health_rules import compute_health, growth_stage, expected_ndvi_range

router = APIRouter(prefix="/api/fields", tags=["health"])


def _owned_field(field_id: int, user: models.User, db: Session) -> models.Field:
    f = (
        db.query(models.Field)
        .filter(models.Field.id == field_id, models.Field.user_id == user.id)
        .first()
    )
    if not f:
        raise HTTPException(status_code=404, detail="Field not found")
    return f


# ---------------------------------------------------------------------------
# Satellite observations list
# ---------------------------------------------------------------------------
@router.get("/{field_id}/satellite", response_model=List[schemas.SatelliteOut])
def list_satellite(
    field_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=90, ge=1, le=730),
):
    _owned_field(field_id, user, db)
    obs = (
        db.query(models.SatelliteObservation)
        .filter(models.SatelliteObservation.field_id == field_id)
        .order_by(models.SatelliteObservation.date.desc())
        .limit(limit)
        .all()
    )
    return obs


# ---------------------------------------------------------------------------
# Current health
# ---------------------------------------------------------------------------
@router.get("/{field_id}/health", response_model=schemas.HealthOut)
def current_health(
    field_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _owned_field(field_id, user, db)
    obs = (
        db.query(models.SatelliteObservation)
        .filter(models.SatelliteObservation.field_id == field_id)
        .order_by(models.SatelliteObservation.date.desc())
        .first()
    )
    reading = (
        db.query(models.SensorReading)
        .filter(models.SensorReading.field_id == field_id)
        .order_by(models.SensorReading.timestamp.desc())
        .first()
    )

    ndvi = obs.ndvi if obs else None
    ndwi = obs.ndwi if obs else None
    cloud = obs.cloud_pct if obs else None

    verdict = compute_health(
        crop_type=field.crop_type,
        planting_date=field.planting_date,
        ndvi=ndvi,
        ndwi=ndwi,
        cloud_pct=cloud,
        prev_ndvi=None,  # trend handled in refresh; here we just report snapshot
        latest_moisture=reading.moisture if reading else None,
        latest_ec=reading.ec if reading else None,
    )

    soil_ctx = None
    if reading is not None:
        soil_ctx = {
            "moisture": reading.moisture,
            "temperature": reading.temperature,
            "ph": reading.ph,
            "ec": reading.ec,
            "timestamp": reading.timestamp.isoformat(),
        }

    return schemas.HealthOut(
        field_id=field.id,
        status=verdict.status,
        reason=verdict.reason,
        ndvi=ndvi,
        ndwi=ndwi,
        cloud_pct=cloud,
        observed_at=obs.date if obs else None,
        soil=soil_ctx,
    )


# ---------------------------------------------------------------------------
# Trend chart
# ---------------------------------------------------------------------------
@router.get("/{field_id}/health/trend", response_model=schemas.HealthTrendOut)
def health_trend(
    field_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(default=90, ge=1, le=730),
):
    _owned_field(field_id, user, db)
    since = date.today() - timedelta(days=days)
    obs = (
        db.query(models.SatelliteObservation)
        .filter(
            models.SatelliteObservation.field_id == field_id,
            models.SatelliteObservation.date >= since,
        )
        .order_by(models.SatelliteObservation.date.asc())
        .all()
    )
    return schemas.HealthTrendOut(
        field_id=field_id,
        points=[
            schemas.HealthTrendPoint(
                date=o.date, ndvi=o.ndvi, ndwi=o.ndwi, health_status=o.health_status,
            )
            for o in obs
        ],
    )


from fastapi.responses import Response
from ..services.sentinel import fetch_satellite_raster, _polygon_to_bbox


# ---------------------------------------------------------------------------
# Live Sentinel-2 NDVI & NDWI Raster Layer Overlays
# ---------------------------------------------------------------------------
@router.get("/{field_id}/satellite/raster/{layer_type}")
def get_satellite_raster(
    field_id: int,
    layer_type: str,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _owned_field(field_id, user, db)
    try:
        png_bytes = fetch_satellite_raster(field, layer_type=layer_type)
        return Response(content=png_bytes, media_type="image/png")
    except Exception as err:
        logger.exception("Satellite raster error: %s", err)
        raise HTTPException(status_code=502, detail=f"Failed to fetch satellite imagery: {err}")


# ---------------------------------------------------------------------------
# Manual refresh
# ---------------------------------------------------------------------------
@router.post("/{field_id}/satellite/refresh", response_model=Optional[schemas.SatelliteOut])
def refresh_satellite(
    field_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _owned_field(field_id, user, db)
    obs = refresh_field_satellite(db, field)
    return obs

