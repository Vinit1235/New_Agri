# 🔍 SoilEdge — Full System Inconsistency & Architectural Audit Report
> Generated on: 2026-10-12  
> Scope: ESP32 Firmware (`SoilEdge_FieldNode_v3.ino`), Backend APIs & Database Models (`FastAPI / SQLAlchemy`), Frontend Applications (`HTML/CSS/JS`), and Machine Learning / Gemini Services.

---

## 📑 Executive Summary

The audit reveals that several core modules across the firmware, backend, database models, and frontend were built independently as isolated prototypes. As a result, critical runtime bugs exist, data schemas do not match between hardware and UI, frontend pages operate with hardcoded mock states, and newly added v3 hardware sensors are neglected in favor of fabricated sensor readings (such as fake NPK, pH, and EC).

---

## 🚨 1. Critical Breaking Bugs (Runtime Crashes)

| Component | File & Line | Cause | Consequence |
| :--- | :--- | :--- | :--- |
| **User Registration** | [`backend/app/routers/auth.py:30`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/backend/app/routers/auth.py#L30) | `models.User(..., category=getattr(payload, 'category', None))` passed to model. `models.User` has **no `category` column**. | **500 Server Error on Signup.** SQLAlchemy throws: `TypeError: 'category' is an invalid keyword argument for User`. User registration is 100% broken. |
| **Satellite Raster API** | [`backend/app/routers/health.py:166`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/backend/app/routers/health.py#L166) | `logger.exception("Satellite raster error: %s", err)` used inside `except` block, but **`logger` is never imported or defined**. | **Uncaught NameError.** If an image fetch fails, Python crashes with `NameError: name 'logger' is not defined` instead of returning HTTP 502. |
| **Voice AI Service** | [`backend/app/routers/voice.py:306`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/backend/app/routers/voice.py#L306) | Invokes `model="gemini-2.5-flash"` via Google GenAI SDK. | **404 Model Not Found.** `gemini-2.5-flash` is not a valid public model identifier. Should be `gemini-2.0-flash` or `gemini-1.5-flash`. |
| **Health Scoring Logic** | [`backend/app/services/health_rules.py:30-41`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/backend/app/services/health_rules.py#L30-L41) | Duplicate stub `def growth_stage(...)` that always returns `"unknown"` precedes the actual implementation at line 69. | Dead / redundant stub code that causes confusion and linting warnings. |

---

## 🧩 2. Hardware vs. Backend vs. Frontend Sensor Disconnect

### Physical Hardware Reality
The field node (`SoilEdge_FieldNode_v3.ino`) physically contains:
1. **Soil Moisture Sensor** (Capacitive analog ADC on `GPIO 34`)
2. **DHT22 Sensor** (Temperature & Relative Humidity on `GPIO 4`)
3. **Turbidity Sensor** (Water clarity analog ADC on `GPIO 35`)
4. **Water Flow Meter** (YF-S201 pulse hall effect interrupt on `GPIO 14`)
5. **Relay Actuator** (Pump switch on `GPIO 26`)

It sends this payload to `POST /api/telemetry`:
```json
{
  "device_id": "node-field-01",
  "moisture": 42.5,
  "temperature": 27.8,
  "humidity": 65.2,
  "turbidity_ntu": 14.5,
  "flow_rate_lpm": 2.15,
  "session_volume_L": 0.45,
  "total_volume_L": 12.8,
  "pump": true,
  "fertilizer": false,
  "action_name": "HYSTERESIS_IRRIGATION_ON"
}
```

### The Frontend & AI Illusion
* **Fabricated NPK, pH, and EC:** 
  In [`frontend/smart-fertilizer.html`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/frontend/smart-fertilizer.html#L1170-L1172), Nitrogen (N), Phosphorus (P), and Potassium (K) levels are artificially fabricated using mock mathematical formulas on moisture and temperature:
  ```js
  nLevel = Math.round(350 + (moisture / 100) * 150 + (temperature / 40) * 80);
  pLevel = Math.round(25 + (humidity / 100) * 15 + (moisture / 100) * 10);
  kLevel = Math.round(140 + (temperature / 40) * 60 + (moisture / 100) * 40);
  ```
  `ph` is hardcoded to `6.8` and `ec` is hardcoded to `1.2`.
* **Voice Assistant Sending Nonexistent Parameters:**
  In [`frontend/voice-assistant.html:551`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/frontend/voice-assistant.html#L551), the frontend sends `ph: 6.7, ec: 5.4` to the backend voice endpoint, which the backend schema doesn't even store or validate.
* **Ignored Hardware Capabilities:**
  The new **turbidity** and **water flow / volume** sensors delivered by v3 firmware are stored in the database but **completely absent** from `dashboard.html`, `smart-watering.html`, and `crop-health.html`. They only appear in `esp32-monitor.html`.

---

## 🌐 3. Frontend Architecture & State Fragmentation

### A. Hardcoded Field ID (`currentFieldId = 1`)
Every page is hardcoded to use field ID `1`:
* `frontend/smart-watering.html` (line 1146): `let currentFieldId = 1;`
* `frontend/smart-fertilizer.html` (line 1146): `let currentFieldId = 1;`
* `frontend/ai-yield-prediction.html` (line 958): `let currentFieldId = 1;`
* `frontend/esp32-monitor.html` (line 541): `fieldIdInput.value || 1;`

**Problem:** If a newly registered user creates their own field (e.g. Field #2 or #5), or if field #1 does not exist, all pages fail with `404 Field Not Found` and display blank/zero data. There is no shared field switcher dropdown.

### B. Inconsistent URL Schemes (Hardcoded vs. Relative)
* **Hardcoded `http://localhost:8000`:** `dashboard.html`, `smart-watering.html`, `smart-fertilizer.html`, `ai-yield-prediction.html`.
* **Relative `/api/...`:** `crop-health.html` uses `fetch('/api/fields/...')`. If opened via VS Code Live Server (port 5500) or file protocol, all requests fail with 404 because they target port 5500 instead of backend port 8000.
* **Configurable `API` variable:** `esp32-monitor.html` and `voice-assistant.html` define `API_BASE`, but each is isolated in its own `<script>` tag.

### C. Duplicate & Conflicting Files
* [`frontend/index.html.html`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/frontend/index.html.html) is an accidental duplicate copy of `index.html`.
* [`frontend/index.html`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/frontend/index.html) (117,503 bytes) and [`frontend/dashboard.html`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/frontend/dashboard.html) (117,579 bytes) are virtually identical duplicates. Updating one leaves the other outdated.
* Upon login/signup, scripts redirect to `index.html`, but sidebar menus across other pages link to `dashboard.html`.

---

## 🔐 4. Device Registration & Ownership Architecture Flaw

In [`backend/app/routers/devices.py:98-103`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/backend/app/routers/devices.py#L98-L103):
```python
@router.get("", response_model=list[schemas.DeviceOut])
def list_my_devices(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(models.Device)
        .join(models.Field, models.Field.id == models.Device.field_id)
        .filter(models.Field.user_id == user.id)
        .all()
    )
```

* `models.Device` has **no `user_id` column**; it only has `field_id`.
* The registration endpoint allows registering a device with `field_id: None`.
* **Consequence:** If an ESP32 is registered before a field is assigned, the inner join on `models.Field` drops it. The device becomes permanently orphaned: invisible to the user, unlisted in `GET /api/devices`, and impossible to link later via the UI.

---

## ⚡ 5. ESP32 Firmware Telemetry Disconnect

In [`esp32-firmware/SoilEdge_FieldNode_v3/SoilEdge_FieldNode_v3.ino`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/esp32-firmware/SoilEdge_FieldNode_v3/SoilEdge_FieldNode_v3.ino):
1. **Hardcoded IP & Empty Token:**
   ```cpp
   const char* API_BASE     = "http://192.168.1.100:8000";
   const char* DEVICE_TOKEN = ""; 
   ```
2. **Instant Rejection by Backend:**
   Because `DEVICE_TOKEN` is blank, the ESP32 sends telemetry without an `Authorization` header. Backend `telemetry.py` strictly checks:
   ```python
   token = _extract_device_token(authorization, x_device_token)
   if not token:
       raise HTTPException(status_code=401, detail="Missing device token")
   ```
   The device gets HTTP 401 on every transmission until the user manually invokes the API, generates a token, edits the C++ file, and reflashes the microcontroller.

---

## 🛠️ Step-by-Step Unification & Fix Roadmap

### Step 1: Repair Critical Backend Crashes
- [ ] **Fix `auth.py`**: Either add `category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)` to `models.User` (and `database.py`) or remove `category` from `models.User(...)` in `auth.py`.
- [ ] **Fix `health.py`**: Add `import logging` and `logger = logging.getLogger("soiledge.health")`.
- [ ] **Fix `voice.py`**: Change model identifier to `gemini-2.0-flash`.
- [ ] **Fix `health_rules.py`**: Remove duplicate `growth_stage` stub.

### Step 2: Establish Single Source of Truth for Frontend State
- [ ] **Create `frontend/js/config.js`**:
  * Unified `API_BASE = 'http://localhost:8000'`.
  * Centralized token management (`krishi_token`, `krishi_user`).
  * Centralized field switcher: fetches `GET /api/fields`, populates a universal field dropdown in the navbar, and stores active field ID in `localStorage.setItem('current_field_id', id)`.
- [ ] **Update all HTML pages**: Include `config.js` and eliminate hardcoded `currentFieldId = 1` and hardcoded `localhost:8000` URLs.

### Step 3: Align Sensor Readings with Real Hardware
- [ ] Replace fabricated NPK and fake pH/EC cards with actual v3 telemetry:
  * **Water Clarity (Turbidity in NTU)**.
  * **Flow Rate (L/min)** and **Total Pumped Water Volume (L)**.
- [ ] If agronomic NPK/pH estimates are displayed, clearly label them as **"Estimated via Soil Stage Rules"** rather than actual sensor telemetry.

### Step 4: Fix Device Ownership Model
- [ ] Add `user_id` foreign key to `models.Device` so devices belong to users directly.
- [ ] Change `list_my_devices` query to filter by `models.Device.user_id == user.id` (or left outer join with `Field`), preventing orphaned unlinked devices.

### Step 5: Clean Codebase Cruft
- [ ] Delete `frontend/index.html.html`.
- [ ] Designate `index.html` as the landing/presentation page and `dashboard.html` as the authenticated app (or unify them into one canonical page).
