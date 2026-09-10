"""Simplified soil classification — moisture + temperature based.

With pH and EC sensors removed, the classification is now based on
soil moisture and temperature thresholds. The original decision tree
(model_tree.json) used pH/EC which are no longer available.

Action codes:
  0 = Monitor (all good)
  1 = Irrigate (moisture too low)
  2 = Reduce watering (moisture too high / waterlogging risk)
  3 = Heat stress alert (high temperature + low moisture)
  4 = Critical — immediate irrigation needed
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("soiledge.soil_model")

ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "ml" / "artifacts"
META_PATH = ARTIFACTS / "model_meta.json"


def classify(temperature: float, moisture: float) -> int:
    """Moisture + temperature based classification. Returns 0..4."""
    # Critical: very dry soil
    if moisture < 10:
        return 4  # Critical — immediate irrigation
    # Heat stress + dry soil
    if temperature > 40 and moisture < 25:
        return 3  # Heat stress alert
    # Low moisture — needs irrigation
    if moisture < 20:
        return 1  # Irrigate
    # Waterlogged / too wet
    if moisture > 70:
        return 2  # Reduce watering
    # Normal range
    return 0  # Monitor


ACTION_NAMES = {
    0: "Maintain regular soil monitoring",
    1: "Improve irrigation scheduling",
    2: "Reduce watering — waterlogging risk",
    3: "Heat stress — irrigate and shade crops",
    4: "Immediate irrigation needed",
}


def action_name(code: int) -> str:
    return ACTION_NAMES.get(code, f"action_{code}")


def derive_pump_fertilizer(action: int, moisture: float | None = None) -> tuple[bool, bool]:
    """Map the action to (pump, fertilizer) booleans."""
    if action in (1, 3, 4):
        return True, False   # pump ON
    if action == 0 and moisture is not None and 20 <= moisture <= 40:
        return False, True   # safe to fertilize
    return False, False


def model_info() -> dict:
    """Return model metadata."""
    meta: dict = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text())
    meta["classification"] = "moisture + temperature thresholds"
    meta["sensors"] = ["soil_moisture", "dht11_temperature", "dht11_humidity"]
    return meta

