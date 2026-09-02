"""Pydantic schemas for request / response bodies."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List, Any, Dict, Literal

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: Optional[str] = None
    created_at: datetime


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------------------------------------------------------------------------
# Field
# ---------------------------------------------------------------------------
class FieldBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    crop_type: str = Field(default="general", max_length=60)
    planting_date: Optional[date] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    polygon: Optional[Dict[str, Any]] = None


class FieldCreate(FieldBase):
    pass


class FieldUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    crop_type: Optional[str] = Field(default=None, max_length=60)
    planting_date: Optional[date] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    polygon: Optional[Dict[str, Any]] = None


class FieldOut(FieldBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    health_status: Optional[str] = None
    health_reason: Optional[str] = None
    health_updated_at: Optional[datetime] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------
class DeviceRegister(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    name: Optional[str] = Field(default=None, max_length=120)
    field_id: Optional[int] = None


class DeviceLink(BaseModel):
    field_id: Optional[int] = None  # None = unlink


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    name: Optional[str] = None
    field_id: Optional[int] = None
    last_seen: Optional[datetime] = None
    created_at: datetime


class DeviceWithToken(DeviceOut):
    """Returned ONLY at registration time. Plaintext token cannot be retrieved later."""

    token: str


# ---------------------------------------------------------------------------
# Telemetry (ESP32)
# ---------------------------------------------------------------------------
class TelemetryIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    moisture: Optional[float] = Field(default=None, ge=0, le=100)
    temperature: Optional[float] = Field(default=None, ge=-40, le=80)
    ph: Optional[float] = Field(default=None, ge=0, le=14)
    ec: Optional[float] = Field(default=None, ge=0, le=20)
    action: Optional[int] = Field(default=None, ge=0, le=10)
    action_name: Optional[str] = Field(default=None, max_length=120)
    pump: bool = False
    fertilizer: bool = False
    timestamp: Optional[datetime] = None  # default: server time


class TelemetryAck(BaseModel):
    ok: bool = True
    reading_id: int
    event_id: Optional[int] = None
    field_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Readings / Events (frontend)
# ---------------------------------------------------------------------------
class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    moisture: Optional[float] = None
    temperature: Optional[float] = None
    ph: Optional[float] = None
    ec: Optional[float] = None
    timestamp: datetime
    device_id: str  # joined from device table


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: Optional[int] = None
    action_name: Optional[str] = None
    pump: bool
    fertilizer: bool
    timestamp: datetime
    device_id: Optional[str] = None  # joined


# ---------------------------------------------------------------------------
# Satellite / Health
# ---------------------------------------------------------------------------
class SatelliteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    ndvi: Optional[float] = None
    ndwi: Optional[float] = None
    cloud_pct: Optional[float] = None
    health_status: Optional[str] = None
    reason: Optional[str] = None
    source: str


class HealthOut(BaseModel):
    field_id: int
    status: Literal["healthy", "moderate", "high_stress", "unknown"]
    reason: str
    ndvi: Optional[float] = None
    ndwi: Optional[float] = None
    cloud_pct: Optional[float] = None
    observed_at: Optional[date] = None
    soil: Optional[Dict[str, Any]] = None  # latest moisture/EC + interpretation


class HealthTrendPoint(BaseModel):
    date: date
    ndvi: Optional[float] = None
    ndwi: Optional[float] = None
    health_status: Optional[str] = None


class HealthTrendOut(BaseModel):
    field_id: int
    points: List[HealthTrendPoint]


# ---------------------------------------------------------------------------
# Dashboard overview
# ---------------------------------------------------------------------------
class FieldOverview(FieldOut):
    last_action_name: Optional[str] = None
    last_action_at: Optional[datetime] = None
    last_pump: Optional[bool] = None
    last_fertilizer: Optional[bool] = None
    device_online: bool = False
    device_id: Optional[str] = None
    last_seen: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------
class OkResponse(BaseModel):
    ok: bool = True
    message: Optional[str] = None
