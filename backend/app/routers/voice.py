"""/api/voice — Gemini-powered voice assistant for farmers.

Handles voice queries in Hindi, Marathi, and English.
Responds with soil context-aware answers using live farm data.
Includes rate limiting and automatic failover to backup API key.
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator, ValidationError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SensorReading, Field
from ..auth import get_current_user_optional

router = APIRouter(prefix="/api/voice", tags=["voice"])

# Rate limiting: {ip: [(timestamp, count), ...]}
_rate_limiter: dict[str, list[float]] = {}
MAX_REQUESTS_PER_MINUTE = 10
MAX_REQUESTS_PER_HOUR = 50

# API key failover tracking
_api_key_failures: dict[str, int] = {"primary": 0, "backup": 0}
_current_key_index = 0  # 0 = primary, 1 = backup


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
    
    @field_validator("text")
    @classmethod
    def validate_text_length(cls, v: str) -> str:
        """Limit input text to 500 characters to prevent abuse."""
        v = v.strip() if v else ""
        if len(v) == 0:
            raise ValueError("Question cannot be empty")
        if len(v) > 500:
            raise ValueError("Question too long - maximum 500 characters allowed")
        return v


class ChatResponse(BaseModel):
    """Voice chat response."""
    answer: str
    context_used: dict
    api_key_used: Optional[str] = None  # "primary" or "backup"
    rate_limit_remaining: Optional[int] = None


def check_rate_limit(ip: str) -> tuple[bool, int]:
    """
    Check if IP is within rate limits.
    Returns (is_allowed, remaining_requests).
    """
    now = time.time()
    
    # Clean old entries
    if ip in _rate_limiter:
        _rate_limiter[ip] = [t for t in _rate_limiter[ip] if now - t < 3600]  # Keep last hour
    else:
        _rate_limiter[ip] = []
    
    # Check per-minute limit
    recent_minute = [t for t in _rate_limiter[ip] if now - t < 60]
    if len(recent_minute) >= MAX_REQUESTS_PER_MINUTE:
        return False, 0
    
    # Check per-hour limit
    if len(_rate_limiter[ip]) >= MAX_REQUESTS_PER_HOUR:
        return False, 0
    
    # Add current request
    _rate_limiter[ip].append(now)
    
    remaining = MAX_REQUESTS_PER_HOUR - len(_rate_limiter[ip])
    return True, remaining


def get_gemini_client():
    """
    Lazy-load Gemini client with automatic failover to backup key.
    Tries primary key first, then backup if primary fails.
    """
    global _current_key_index
    
    try:
        from google import genai
        from ..config import get_settings
        settings = get_settings()
        
        # Try primary key first
        if _current_key_index == 0 or _api_key_failures["backup"] > 3:
            api_key = settings.gemini_api_key
            key_name = "primary"
            
            if not api_key or api_key in ["YOUR_GEMINI_API_KEY_HERE", ""]:
                # Try backup immediately if primary not configured
                api_key = settings.gemini_api_key_1
                key_name = "backup"
                _current_key_index = 1
        else:
            # Use backup key
            api_key = settings.gemini_api_key_1
            key_name = "backup"
        
        if not api_key or api_key in ["YOUR_GEMINI_API_KEY_HERE", ""]:
            raise ValueError("No valid GEMINI_API_KEY configured in .env")
        
        client = genai.Client(api_key=api_key)
        
        # Reset failure count on successful creation
        _api_key_failures[key_name] = 0
        
        return client, key_name
        
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


def switch_to_backup_key():
    """Switch to backup API key after primary fails."""
    global _current_key_index
    _api_key_failures["primary"] += 1
    if _api_key_failures["primary"] >= 3:
        _current_key_index = 1
        print(f"⚠️ Switching to backup API key after {_api_key_failures['primary']} failures")


def truncate_answer(text: str, max_words: int = 100) -> str:
    """
    Truncate answer to maximum word count to save API costs.
    Preserves sentence boundaries when possible.
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    
    # Try to end at a sentence
    truncated = " ".join(words[:max_words])
    
    # Find last sentence-ending punctuation
    for punct in ['.', '।', '?', '!']:
        last_idx = truncated.rfind(punct)
        if last_idx > len(truncated) * 0.7:  # If we found one in last 30%
            return truncated[:last_idx + 1]
    
    # No good sentence boundary, just cut at word limit
    return truncated + "..."


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
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Process voice/text query with Gemini AI using live soil context.
    
    Features:
    - Rate limiting: 10 requests/minute, 50 requests/hour per IP
    - Input validation: Max 500 characters
    - Output truncation: Max 100 words to save costs
    - Automatic API key failover to backup
    
    Works in 3 modes:
    1. With field_id: Fetches real sensor data from DB
    2. With manual values: Uses provided moisture/ph/ec
    3. Demo mode: Uses placeholder values
    """
    
    # Rate limiting
    client_ip = http_request.client.host
    is_allowed, remaining = check_rate_limit(client_ip)
    
    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Please wait before making more requests. "
                   f"Limit: {MAX_REQUESTS_PER_MINUTE} requests/minute, {MAX_REQUESTS_PER_HOUR} requests/hour."
        )
    
    # Get Gemini client (with failover support)
    client, key_used = get_gemini_client()
    
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

**YOUR ANSWER (in same language as question):**
Keep your answer SHORT - maximum 2-3 sentences or 50 words."""
    
    try:
        # Call Gemini API
        response = client.models.generate_content(
            model="gemini-2.5-flash",  # Latest Flash model
            contents=prompt,
        )
        
        answer = response.text.strip()
        
        # Truncate answer to save costs and reduce TTS time
        answer = truncate_answer(answer, max_words=100)
        
        return ChatResponse(
            answer=answer,
            context_used=context,
            api_key_used=key_used,
            rate_limit_remaining=remaining
        )
    
    except Exception as e:
        # Try to switch to backup key on primary failure
        if key_used == "primary":
            switch_to_backup_key()
            
        error_msg = str(e)
        
        # Fallback response if Gemini fails
        if "hindi" in request.text.lower() or any(ord(c) > 2304 for c in request.text):
            # Hindi detected
            fallback = f"माफ़ करें, मैं अभी आपकी मदद नहीं कर सकता। तकनीकी समस्या है। आपकी मिट्टी का EC {context.get('ec', 0)} है और नमी {context.get('moisture', 0)}% है।"
        else:
            fallback = f"Sorry, I'm having technical difficulties. Your soil EC is {context.get('ec', 0)} and moisture is {context.get('moisture', 0)}%."
        
        return ChatResponse(
            answer=fallback,
            context_used={**context, "error": error_msg},
            api_key_used=key_used,
            rate_limit_remaining=remaining
        )
