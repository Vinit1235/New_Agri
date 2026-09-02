"""Empirical NDVI bands loaded from `ml/artifacts/ndvi_bands.json`.

These were derived from real Sentinel-2 / MODIS NDVI time series
(CY-Bench dataset, wheat + maize, ES + NL, 2001-2023) by
`backend/ml/derive_ndvi_bands.py`. See that file for the full data lineage.

The JSON file shape is:

  {
    "generated_at": "...",
    "source_datasets": [...],
    "scaling": "...",
    "profiles": {
      "<crop_type>": {
        "source": "...",
        "stages": [
          {"stage": "seedling",   "doy_window": [...], "ndvi_low": 0.25, "ndvi_high": 0.54},
          ...
        ]
      }
    }
  }

If the file is missing (i.e. you cloned the repo without running the
training script) we fall back to conservative agronomic estimates, so the
backend still boots.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger("soiledge.ndvi_profiles")

ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "ml" / "artifacts"
BANDS_PATH = ARTIFACTS / "ndvi_bands.json"


# Hard-coded fallback (used only if the JSON is missing)
FALLBACK_PROFILES: dict[str, list[tuple[str, tuple, float, float]]] = {
    "general": [
        ("seedling",   (0,  20), 0.10, 0.30),
        ("vegetative", (21, 60), 0.30, 0.70),
        ("flowering",  (61, 90), 0.55, 0.85),
        ("ripening",   (91, 130),0.40, 0.75),
        ("fallow",     (131, 9999), 0.10, 0.50),
    ],
}


@lru_cache(maxsize=1)
def _load() -> dict:
    if not BANDS_PATH.exists():
        logger.warning("ndvi_bands.json not found at %s — using fallback", BANDS_PATH)
        return {"profiles": {}}
    try:
        return json.loads(BANDS_PATH.read_text())
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to load %s: %s", BANDS_PATH, e)
        return {"profiles": {}}


def get_profile_stages(crop_type: str) -> list[tuple[str, tuple, float, float]]:
    """Return [(stage_name, doy_window, ndvi_low, ndvi_high), ...] for a crop.

    Falls back to the 'general' profile if the requested crop is unknown.
    """
    data = _load()
    profiles = data.get("profiles", {})
    key = (crop_type or "general").lower()
    prof = profiles.get(key) or profiles.get("general") or {}
    stages_raw = prof.get("stages", [])
    out: list[tuple[str, tuple, float, float]] = []
    for s in stages_raw:
        out.append((
            s["stage"],
            tuple(s["doy_window"]),
            float(s["ndvi_low"]),
            float(s["ndvi_high"]),
        ))
    if not out:
        out = FALLBACK_PROFILES["general"]
    return out


def get_metadata() -> dict:
    """Return the top-level metadata (sources, scaling, generation time)."""
    return _load()


def get_day_of_year(d) -> int:
    """Return 1..366 day-of-year for a date or datetime."""
    if hasattr(d, "timetuple"):
        return d.timetuple().tm_yday
    return 1


def in_window(doy: int, win) -> bool:
    if len(win) == 2:
        lo, hi = win
        return lo <= doy <= hi
    lo1, hi1, lo2, hi2 = win
    return lo1 <= doy <= hi1 or lo2 <= doy <= hi2
