"""/api/voice — Gemini-powered voice assistant for farmers.

Handles voice queries in Hindi, Marathi, and English.
Responds with soil context-aware answers using live farm data.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SensorReading, Field
from ..auth import get_current_user_optional

router = APIRouter(prefix="/api/voice", tags=["voice"])


class ChatRequest(BaseModel):
    """Voice chat request with text and optional sensor overrides."""
    text: str
    field_id: Optional[int] = None
    # Optional manual overrides for demo (if no DB data available)
    moisture: Optional[float] = None
    ph: Optional[float] = None
    ec: Optional[float] = None
    temperature: Optional[float] = None
    last_action: Optional[str] = None


class ChatResponse(BaseModel):
    """Voice chat response."""
    answer: str
    context_used: dict


def get_gemini_client():
    """Lazy-load Gemini client."""
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
            raise ValueError("GEMINI_API_KEY not configured in .env")
        return genai.Client(api_key=api_key)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="google-genai not installed. Run: pip install google-genai"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini setup error: {str(e)}"
        )


def get_latest_reading(field_id: int, db: Session) -> Optional[SensorReading]:
    """Get the most recent sensor reading for a field."""
    return (
        db.query(SensorReading)
        .filter(SensorReading.field_id == field_id)
        .order_by(SensorReading.timestamp.desc())
        .first()
    )


def get_field_name(field_id: int, db: Session) -> str:
    """Get field name or return 'Unknown Field'."""
    field = db.query(Field).filter(Field.id == field_id).first()
    return field.name if field else "Unknown Field"


@router.post("/chat", response_model=ChatResponse)
async def voice_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Process voice/text query with Gemini AI using live soil context.
    
    Works in 3 modes:
    1. With field_id: Fetches real sensor data from DB
    2. With manual values: Uses provided moisture/ph/ec
    3. Demo mode: Uses placeholder values
    """
    
    # Get Gemini client
    client = get_gemini_client()
    
    # Determine data source
    context = {}
    
    if request.field_id:
        # Mode 1: Fetch real data from database
        reading = get_latest_reading(request.field_id, db)
        field_name = get_field_name(request.field_id, db)
        
        if reading:
            context = {
                "field_name": field_name,
                "moisture": round(reading.moisture, 1),
                "ph": round(reading.ph, 2),
                "ec": round(reading.ec, 2),
                "temperature": round(reading.temperature, 1),
                "timestamp": reading.timestamp.strftime("%Y-%m-%d %H:%M"),
                "source": "live_database"
            }
        else:
            context = {
                "field_name": field_name,
                "moisture": request.moisture or 0,
                "ph": request.ph or 0,
                "ec": request.ec or 0,
                "temperature": request.temperature or 0,
                "source": "no_data_available"
            }
    
    elif any([request.moisture, request.ph, request.ec, request.temperature]):
        # Mode 2: Use manual overrides
        context = {
            "field_name": "Demo Field",
            "moisture": request.moisture or 28.5,
            "ph": request.ph or 6.7,
            "ec": request.ec or 5.4,
            "temperature": request.temperature or 28.0,
            "last_action": request.last_action or "Monitoring",
            "source": "manual_override"
        }
    
    else:
        # Mode 3: Demo values
        context = {
            "field_name": "Demo Field",
            "moisture": 28.5,
            "ph": 6.7,
            "ec": 5.4,
            "temperature": 28.0,
            "last_action": "Fertilizer blocked (high EC)",
            "source": "demo_mode"
        }
    
    # Build Gemini prompt with agricultural context
    prompt = f"""You are SoilEdge, an intelligent farm voice assistant helping Indian farmers.

**LANGUAGE RULES:**
- Detect user's language (Hindi, Marathi, or English) from their question
- Reply in the SAME language they used
- Keep answers SHORT and PRACTICAL (2-3 sentences max)
- Use simple farming terms farmers understand

**CURRENT FARM DATA:**
Field: {context.get('field_name', 'Farm')}
Soil Moisture: {context.get('moisture', 0)}%
pH Level: {context.get('ph', 0)}
EC (Salinity): {context.get('ec', 0)} dS/m
Temperature: {context.get('temperature', 0)}°C
{f"Last Action: {context.get('last_action', 'Monitoring')}" if 'last_action' in context else ""}
{f"Data from: {context.get('timestamp', 'Now')}" if 'timestamp' in context else ""}

**AGRICULTURAL RULES YOU MUST FOLLOW:**
1. High EC (>4.0) means soil is too salty → BLOCK fertilizer, recommend leaching/drainage
2. Low moisture (<20%) → Recommend irrigation
3. Optimal pH for most crops: 6.0-7.5
4. EC 0-2: Low salinity (good); 2-4: Medium; 4-8: High (problem); >8: Very high (critical)
5. If fertilizer is blocked, explain it's because EC is too high
6. Never invent numbers - only use the data provided above

**FARMER'S QUESTION:**
{request.text}

**YOUR ANSWER (in same language as question):**"""
    
    try:
        # Call Gemini API
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",  # Fast model for voice
            contents=prompt,
        )
        
        answer = response.text.strip()
        
        return ChatResponse(
            answer=answer,
            context_used=context
        )
    
    except Exception as e:
        # Fallback response if Gemini fails
        error_msg = str(e)
        if "hindi" in request.text.lower() or any(ord(c) > 2304 for c in request.text):
            # Hindi detected
            fallback = f"माफ़ करें, मैं अभी आपकी मदद नहीं कर सकता। तकनीकी समस्या है। आपकी मिट्टी का EC {context.get('ec', 0)} है और नमी {context.get('moisture', 0)}% है।"
        else:
            fallback = f"Sorry, I'm having technical difficulties. Your soil EC is {context.get('ec', 0)} and moisture is {context.get('moisture', 0)}%."
        
        return ChatResponse(
            answer=fallback,
            context_used={**context, "error": error_msg}
        )
