"""Python mirror of the ESP32 decision tree.

This module loads the trained tree from `ml/artifacts/model_tree.json` at
startup and exposes a `classify(ph, temperature, moisture, ec)` function
that returns the same integer action code the ESP32 firmware will return.

Why have a Python mirror?
  * The backend can re-score incoming telemetry (useful for calibration,
    drift detection, and "what would the firmware have done?" comparisons).
  * The frontend can show a "model predicted" badge.
  * A future dashboard could replay historical readings through the model.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("soiledge.soil_model")

ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "ml" / "artifacts"
TREE_PATH = ARTIFACTS / "model_tree.json"
META_PATH = ARTIFACTS / "model_meta.json"


@lru_cache(maxsize=1)
def _load_tree() -> tuple[dict, dict]:
    if not TREE_PATH.exists():
        raise FileNotFoundError(
            f"Model tree not found at {TREE_PATH}. "
            "Run `python -m ml.train_esp32_model` first."
        )
    tree = json.loads(TREE_PATH.read_text())
    meta: dict = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text())
    logger.info("Loaded ESP32 soil model: %s (CV acc=%s)",
                meta.get("source"), meta.get("cv_accuracy_5fold"))
    return tree, meta


def classify(ph: float, temperature: float, moisture: float, ec: float) -> int:
    """Run the trained decision tree. Returns 0..4 (the spec's action code)."""
    tree, _ = _load_tree()
    node: Any = tree
    while not isinstance(node, int):
        f_name, t = node["f"], node["t"]
        x = {"ph": ph, "temperature": temperature, "moisture": moisture, "ec": ec}[f_name]
        node = node["l"] if x <= t else node["r"]
    return int(node)


def action_name(code: int) -> str:
    _, meta = _load_tree()
    return meta.get("action_names", {}).get(str(code), f"action_{code}")


def derive_pump_fertilizer(action: int, moisture: float | None = None,
                            ec: float | None = None, ph: float | None = None) -> tuple[bool, bool]:
    """Map the model action to (pump, fertilizer) booleans matching the firmware."""
    if action == 0:
        # Monitor; fertilizer only when conditions are safe
        if (
            moisture is not None and ec is not None and ph is not None
            and ec < 2.2 and 6.0 <= ph <= 7.5 and 18.0 <= moisture <= 40.0
        ):
            return False, True
        return False, False
    if action in (1, 3, 4):
        return True, False
    # action == 2 (amend) — pump off, fertilizer off
    return False, False


def model_info() -> dict:
    """Return training metadata (source, accuracy, feature importances, ...)."""
    _, meta = _load_tree()
    return dict(meta)
