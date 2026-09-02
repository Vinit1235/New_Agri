"""SQLAlchemy ORM models for SoilEdge Field System."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Date, ForeignKey, Text, JSON, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    fields: Mapped[List["Field"]] = relationship(
        "Field", back_populates="owner", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Field
# ---------------------------------------------------------------------------
class Field(Base):
    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    crop_type: Mapped[str] = mapped_column(String(60), nullable=False, default="general")
    planting_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Optional polygon as GeoJSON dict, e.g. {"type":"Polygon","coordinates":[[...]]}
    polygon: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Cached latest health snapshot (denormalised for fast dashboard)
    health_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    health_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    health_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    owner: Mapped["User"] = relationship("User", back_populates="fields")
    devices: Mapped[List["Device"]] = relationship(
        "Device", back_populates="field", cascade="all, delete-orphan"
    )
    readings: Mapped[List["SensorReading"]] = relationship(
        "SensorReading", back_populates="field", cascade="all, delete-orphan"
    )
    events: Mapped[List["AutomationEvent"]] = relationship(
        "AutomationEvent", back_populates="field", cascade="all, delete-orphan"
    )
    satellite_observations: Mapped[List["SatelliteObservation"]] = relationship(
        "SatelliteObservation", back_populates="field", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------
class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    field_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("fields.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    field: Mapped[Optional["Field"]] = relationship("Field", back_populates="devices")


# ---------------------------------------------------------------------------
# Sensor reading (telemetry from ESP32)
# ---------------------------------------------------------------------------
class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    moisture: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ph: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    field_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("fields.id", ondelete="SET NULL"), index=True, nullable=True
    )

    device: Mapped["Device"] = relationship("Device")
    field: Mapped[Optional["Field"]] = relationship("Field", back_populates="readings")


# ---------------------------------------------------------------------------
# Automation event (ESP32 decision: pump / fertilizer + action label)
# ---------------------------------------------------------------------------
class AutomationEvent(Base):
    __tablename__ = "automation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    action: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    pump: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fertilizer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    field_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("fields.id", ondelete="SET NULL"), index=True, nullable=True
    )

    field: Mapped[Optional["Field"]] = relationship("Field", back_populates="events")
    device: Mapped["Device"] = relationship("Device")


# ---------------------------------------------------------------------------
# Satellite observation (NDVI / NDWI for a field)
# ---------------------------------------------------------------------------
class SatelliteObservation(Base):
    __tablename__ = "satellite_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    ndvi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ndwi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cloud_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    health_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="copernicus", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    field_id: Mapped[int] = mapped_column(
        ForeignKey("fields.id", ondelete="CASCADE"), index=True
    )
    field: Mapped["Field"] = relationship("Field", back_populates="satellite_observations")


# Composite index used heavily for "latest reading for field" queries
Index("ix_readings_field_ts", SensorReading.field_id, SensorReading.timestamp.desc())
Index("ix_events_field_ts", AutomationEvent.field_id, AutomationEvent.timestamp.desc())
Index("ix_sat_field_date", SatelliteObservation.field_id, SatelliteObservation.date.desc())
