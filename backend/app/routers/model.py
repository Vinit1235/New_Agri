"""/api/model — diagnostic endpoints around the trained soil-AI model.

The model is trained offline (see backend/ml/train_esp32_model.py) and the
artefacts are loaded at startup. These endpoints let the frontend (and the
operator) verify that the model is loaded, see its training metadata, and
re-score individual readings.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from .. import models
from ..services.soil_model import classify, action_name, derive_pump_fertilizer, model_info

router = APIRouter(prefix="/api/model", tags=["model"])


class ScoreIn(BaseModel):
    ph: float = Field(..., ge=0, le=14)
    temperature: float = Field(..., ge=-40, le=80)
    moisture: float = Field(..., ge=0, le=100)
    ec: float = Field(..., ge=0, le=20)


class ScoreOut(BaseModel):
    action: int
    action_name: str
    pump: bool
    fertilizer: bool


@router.get("/info")
def info(_user: models.User = Depends(get_current_user)):
    """Training metadata: source, accuracy, feature importances, etc."""
    return model_info()


@router.post("/score", response_model=ScoreOut)
def score(payload: ScoreIn, _user: models.User = Depends(get_current_user)):
    """Re-score a sensor reading through the trained tree.

    Useful for the frontend to show 'what the firmware would decide' and
    for operators to sanity-check edge cases.
    """
    code = classify(payload.ph, payload.temperature, payload.moisture, payload.ec)
    pump, fert = derive_pump_fertilizer(code, payload.moisture, payload.ec, payload.ph)
    return ScoreOut(action=code, action_name=action_name(code), pump=pump, fertilizer=fert)
