"""Health scoring for a field — uses empirically-derived NDVI bands.

The crop stage bands are loaded from `ml/artifacts/ndvi_bands.json`,
which was generated from real Sentinel-2 / MODIS NDVI time series
(see `backend/ml/derive_ndvi_bands.py` for the data lineage).

A small layer of rules on top combines:
  * absolute NDVI vs the empirical stage band
  * trend vs the previous observation
  * the latest soil sensor reading (moisture / EC)
  * NDWI as a cross-check for water stress

…and emits a verdict + a human-readable reason string.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .ndvi_profiles import get_profile_stages, get_day_of_year, in_window

logger = logging.getLogger("soiledge.health_rules")


# ---------------------------------------------------------------------------
# Stage + NDVI expected range
# ---------------------------------------------------------------------------
def growth_stage(crop_type: str, planting_date: Optional[date], on: Optional[date] = None) -> str:
    if planting_date is None:
        return "unknown"
    on = on or date.today()
    days = max(0, (on - planting_date).days)
    for stage_name, _, _, _ in get_profile_stages(crop_type):
        # The profile stores a day-of-year window, but growth_stage is
        # called with days-since-planting. We need stage windows in
        # days-since-planting. Derive from the "vegetative" stage mid-point
        # and the crop's typical cycle length.
        pass
    return "unknown"  # placeholder, see below


def _stage_windows_in_days(crop_type: str) -> list[tuple[str, int, int]]:
    """Return (stage_name, days_since_planting_lo, days_since_planting_hi).

    For each profile stage we map the (doy_window) to a days-since-planting
    window using a typical cycle length assumption per crop. Wheat ~ 200
    days, maize ~ 150 days, rice ~ 150 days, vegetables ~ 100 days, etc.
    """
    cycle_lengths = {
        "wheat": 200, "cereals": 200, "maize": 150, "rice": 150,
        "vegetables": 100, "pulses": 120, "general": 130,
    }
    cl = cycle_lengths.get(crop_type.lower(), 130) if crop_type else 130
    stages = get_profile_stages(crop_type)
    # Split the cycle into 5 roughly equal windows corresponding to the
    # 5 stages (seedling, vegetative, flowering, ripening, fallow)
    splits = [0, int(cl * 0.15), int(cl * 0.45), int(cl * 0.70), int(cl * 0.90), cl]
    out: list[tuple[str, int, int]] = []
    for i, (stage_name, _doy_win, _lo, _hi) in enumerate(stages[:5]):
        out.append((stage_name, splits[i], splits[i + 1]))
    # 'fallow' covers everything past the cycle end
    if len(out) == 5:
        out[4] = (out[4][0], out[4][1], 9999)
    return out


def growth_stage(crop_type: str, planting_date: Optional[date], on: Optional[date] = None) -> str:
    if planting_date is None:
        return "unknown"
    on = on or date.today()
    days = max(0, (on - planting_date).days)
    for stage_name, lo, hi in _stage_windows_in_days(crop_type or "general"):
        if lo <= days <= hi:
            return stage_name
    return "unknown"


def expected_ndvi_range(crop_type: str, planting_date: Optional[date], on: Optional[date] = None) -> tuple[float, float]:
    if planting_date is None:
        return 0.0, 1.0
    on = on or date.today()
    days = max(0, (on - planting_date).days)
    stages = get_profile_stages(crop_type or "general")
    # Map days-since-planting to the stage window to find the matching band
    for i, (stage_name, lo, hi) in enumerate(_stage_windows_in_days(crop_type or "general")):
        if lo <= days <= hi and i < len(stages):
            return float(stages[i][2]), float(stages[i][3])
    return 0.0, 1.0


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
@dataclass
class HealthVerdict:
    status: str            # "healthy" | "moderate" | "high_stress" | "unknown"
    reason: str
    ndvi_trend: Optional[float] = None


def _fmt_range(lo: float, hi: float) -> str:
    return f"{lo:.2f}–{hi:.2f}"


def compute_health(
    *,
    crop_type: str,
    planting_date: Optional[date],
    ndvi: Optional[float],
    ndwi: Optional[float],
    cloud_pct: Optional[float],
    prev_ndvi: Optional[float],
    latest_moisture: Optional[float],
    latest_ec: Optional[float],
) -> HealthVerdict:
    if ndvi is None:
        return HealthVerdict(status="unknown", reason="No satellite data available yet for this field.")

    if cloud_pct is not None and cloud_pct > 60:
        return HealthVerdict(
            status="unknown",
            reason=f"Latest scene is too cloudy ({cloud_pct:.0f}%). Waiting for a clearer pass.",
        )

    stage = growth_stage(crop_type, planting_date)
    ndvi_lo, ndvi_hi = expected_ndvi_range(crop_type, planting_date)
    trend = (ndvi - prev_ndvi) if (ndvi is not None and prev_ndvi is not None) else None

    notes: list[str] = []
    stress = 0

    # 1. Absolute NDVI vs empirical stage band
    if ndvi < ndvi_lo - 0.10:
        stress += 2
        notes.append(
            f"NDVI {ndvi:.2f} is well below the expected {stage} range "
            f"({_fmt_range(ndvi_lo, ndvi_hi)})"
        )
    elif ndvi < ndvi_lo:
        stress += 1
        notes.append(
            f"NDVI {ndvi:.2f} is slightly below the expected {stage} range "
            f"({_fmt_range(ndvi_lo, ndvi_hi)})"
        )
    elif ndvi > ndvi_hi:
        notes.append(
            f"NDVI {ndvi:.2f} is above the expected {stage} range "
            f"({_fmt_range(ndvi_lo, ndvi_hi)})"
        )
    else:
        notes.append(
            f"NDVI {ndvi:.2f} is within the expected {stage} range "
            f"({_fmt_range(ndvi_lo, ndvi_hi)})"
        )

    # 2. Trend vs previous
    if trend is not None:
        if trend < -0.10:
            stress += 2
            notes.append(f"sharp NDVI drop vs previous pass ({trend:+.2f})")
        elif trend < -0.05:
            stress += 1
            notes.append(f"NDVI is trending down vs previous pass ({trend:+.2f})")
        elif trend > 0.05:
            notes.append(f"NDVI is recovering vs previous pass ({trend:+.2f})")

    # 3. NDWI cross-check
    if ndwi is not None:
        if ndwi < -0.20:
            stress += 1
            notes.append(f"low NDWI ({ndwi:.2f}) suggests canopy water stress")
        elif ndwi > 0.30:
            notes.append(f"high NDWI ({ndwi:.2f}) suggests very wet canopy / waterlogging risk")

    # 4. Soil sensor cross-check
    soil_interp: list[str] = []
    if latest_moisture is not None:
        if latest_moisture < 18:
            stress += 1
            soil_interp.append(f"soil moisture low ({latest_moisture:.1f}%)")
        elif latest_moisture > 40:
            soil_interp.append(f"soil moisture high ({latest_moisture:.1f}%)")
    if latest_ec is not None:
        if latest_ec >= 4.0:
            stress += 2
            soil_interp.append(f"soil EC high ({latest_ec:.2f} dS/m) — salt stress likely")
        elif latest_ec >= 2.2:
            stress += 1
            soil_interp.append(f"soil EC elevated ({latest_ec:.2f} dS/m)")
    if soil_interp:
        notes.append("; ".join(soil_interp))

    # 5. Cross-modality reasoning
    if trend is not None and trend < -0.05 and latest_moisture is not None and latest_moisture < 22:
        stress += 1
        notes.append("canopy drop coincides with low soil moisture → likely water stress")
    if trend is not None and trend < -0.05 and latest_ec is not None and latest_ec >= 4.0:
        stress += 1
        notes.append("canopy drop coincides with high EC → likely salt stress")

    if stress >= 3:
        status = "high_stress"
    elif stress >= 1:
        status = "moderate"
    else:
        status = "healthy"

    reason = "; ".join(notes) if notes else "All signals within expected range."
    return HealthVerdict(status=status, reason=reason, ndvi_trend=trend)
