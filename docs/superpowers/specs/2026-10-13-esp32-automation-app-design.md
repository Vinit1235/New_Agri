# 🌾 SoilEdge: ESP32 Automation, Scheduling & AI Vision System Design

**Date:** 2026-10-13  
**Status:** Approved  
**Topic:** ESP32 Bidirectional Automation, Scheduling Engine, Dynamic Gemini AI Voice & Vision Hub, and Full Application Creation Specification

---

## 1. Executive Summary & Goals

The goal of this system is to provide a complete, offline-resilient, precision agriculture management application for the **SoilEdge (Krishinayan)** ecosystem. The system bridges physical ESP32 IoT hardware nodes, a FastAPI backend gateway, and a Liquid Glass client application.

Key capabilities:
1. **Bidirectional ESP32 Control & Synchronization**:
   - 4 Operating Modes: `EDGE_AUTO` (default firmware hysteresis), `SCHEDULED`, `MANUAL`, and `CUSTOM_RULES`.
   - Dual-Connectivity: Cloud sync via regular HTTP telemetry response piggybacking + Local LAN direct REST API on ESP32 (`:80`).
   - Hard edge safety watchdogs (max pump runtime, salinity/EC interlocks, automatic reversion to `EDGE_AUTO` on connection loss).
2. **Flexible Automation Scheduling & Rule Creation**:
   - Web/App UI and backend APIs to create, edit, toggle, and delete daily time slots and custom sensor threshold rules.
3. **Dynamic, Non-Hardcoded Gemini AI Hub**:
   - User-configurable Gemini API Key and **manual Gemini model selection** (e.g. `gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`, or custom user-entered model string).
   - Multilingual Voice Assistant (Hindi, Marathi, English) with real-time farm sensor context and voice-triggered farm commands.
   - Camera/Image Plant Health & Disease Vision Diagnostic Engine with remedies and soil adjustment advice.
4. **Master App Creation Blueprint (`SOIL_EDGE_APP_CREATION_GUIDE.md`)**:
   - Complete technical specification, UI wireframes, Liquid Glass design tokens, REST/WebSocket API contracts, and an end-to-end prompt for building or generating the complete app in AI Studio, web, or mobile platforms.

---

## 2. Architecture & Data Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CLIENT APPLICATION                              │
│  • Liquid Glass Interface (Dashboard, Schedules, Vision, Voice)        │
│  • Dynamic Config: User Gemini API Key & Manual Model Input            │
│  • Dual-Link Switcher: Cloud Backend URL vs Local ESP32 LAN IP        │
└───────────────┬────────────────────────────────────────┬───────────────┘
                │ REST / WebSocket                       │ Direct Local LAN
                ▼                                        ▼ (Port 80)
┌─────────────────────────────────┐      ┌───────────────────────────────┐
│     FASTAPI BACKEND GATEWAY     │      │        ESP32 FIELD NODE       │
│  • /api/automation (CRUD)       │      │  • WebServer (Port 80)        │
│  • /api/telemetry (Piggyback)   │◄────►│  • Soil, DHT11, Turbidity,    │
│  • /api/vision/diagnose         │ HTTP │    Flow Meter Sensors         │
│  • /api/voice/chat              │ Sync │  • Relay Actuators (Pump,     │
│  • SQLite / PostgreSQL Storage  │      │    Fertilizer Valve)          │
└────────────────┬────────────────┘      │  • 4-Mode Edge Engine         │
                 │                       │  • Safety Watchdog (180s max) │
                 ▼                       └───────────────────────────────┘
┌─────────────────────────────────┐
│       GOOGLE GEMINI API         │
│  (Dynamic Key & Dynamic Model)  │
│  • Multimodal Vision Diagnostic │
│  • Multilingual Agronomist Chat │
└─────────────────────────────────┘
```

---

## 3. Data Models & Database Schema (`backend/app/models.py`)

### 3.1 `DeviceAutomationConfig`
Stores the active operating mode, manual overrides, and configuration monotonic version for each hardware device:
* `id`: Integer, Primary Key
* `device_id`: Integer, ForeignKey(`devices.id`, unique=True, index=True)
* `mode`: String, Enum (`"EDGE_AUTO"`, `"SCHEDULED"`, `"MANUAL"`, `"CUSTOM_RULES"`), default=`"EDGE_AUTO"`
* `manual_pump`: Boolean, default=False
* `manual_fertilizer`: Boolean, default=False
* `manual_timeout_seconds`: Integer, default=180
* `manual_expires_at`: DateTime, nullable=True
* `version`: Integer, default=1 (increments every time mode, manual command, schedule, or rule changes)
* `updated_at`: DateTime, default=datetime.utcnow

### 3.2 `AutomationSchedule`
Stores scheduled irrigation or fertigation slots:
* `id`: Integer, Primary Key
* `config_id`: Integer, ForeignKey(`device_automation_configs.id`, index=True)
* `name`: String (e.g., "Morning Drip")
* `enabled`: Boolean, default=True
* `start_time`: String (format `"HH:MM"`, e.g. `"06:30"`)
* `duration_minutes`: Integer (default 15)
* `days_of_week`: String (JSON-encoded array, e.g. `'["MON","TUE","WED","THU","FRI","SAT","SUN"]'`)
* `target_actuator`: String (`"pump"` or `"fertilizer"`, default=`"pump"`)
* `created_at`: DateTime, default=datetime.utcnow

### 3.3 `CustomRule`
Stores custom sensor threshold rules:
* `id`: Integer, Primary Key
* `config_id`: Integer, ForeignKey(`device_automation_configs.id`, index=True)
* `name`: String (e.g., "Low Moisture Emergency")
* `enabled`: Boolean, default=True
* `trigger_sensor`: String (`"moisture"`, `"temperature"`, `"turbidity_ntu"`, `"humidity"`)
* `operator`: String (`"<"`, `">"`, `"<="`, `">="`)
* `threshold_value`: Float
* `action_actuator`: String (`"pump"` or `"fertilizer"`)
* `action_state`: Boolean (True = ON, False = OFF)
* `duration_seconds`: Integer (default 300)
* `created_at`: DateTime, default=datetime.utcnow

---

## 4. API Specifications

### 4.1 Backend Automation Endpoints (`backend/app/routers/automation.py`)
* `GET /api/automation/{device_id}`: Fetch complete state (mode, version, manual states, schedules, rules).
* `PUT /api/automation/{device_id}/mode`: Update active mode (`"EDGE_AUTO"`, `"SCHEDULED"`, `"MANUAL"`, `"CUSTOM_RULES"`). Bumps `version`.
* `POST /api/automation/{device_id}/manual`: Dispatch immediate manual command (`pump`, `fertilizer`, `duration_seconds`). Bumps `version`.
* `POST /api/automation/{device_id}/schedules`: Create new timed schedule. Bumps `version`.
* `PUT /api/automation/{device_id}/schedules/{schedule_id}`: Update schedule. Bumps `version`.
* `DELETE /api/automation/{device_id}/schedules/{schedule_id}`: Remove schedule. Bumps `version`.
* `POST /api/automation/{device_id}/rules`: Create new custom rule. Bumps `version`.
* `PUT /api/automation/{device_id}/rules/{rule_id}`: Update custom rule. Bumps `version`.
* `DELETE /api/automation/{device_id}/rules/{rule_id}`: Remove custom rule. Bumps `version`.

### 4.2 Telemetry Piggyback Sync (`backend/app/routers/telemetry.py`)
When ESP32 posts its 5-second telemetry reading to `/api/telemetry`, the response schema is extended:
```json
{
  "ok": true,
  "reading_id": 1420,
  "event_id": null,
  "field_id": 1,
  "config": {
    "version": 8,
    "mode": "EDGE_AUTO",
    "manual": {
      "pump": false,
      "fertilizer": false,
      "timeout_sec": 180
    },
    "schedules": [ ... ],
    "custom_rules": [ ... ]
  }
}
```

### 4.3 Vision & Voice Endpoints with Dynamic Models (`backend/app/routers/vision.py` & `voice.py`)
* `POST /api/vision/diagnose`:
  * Form Data: `image` (file), `api_key` (optional user-provided key, fallback to `.env`), `model_name` (user-selected model, e.g. `gemini-2.0-flash` or custom, default `gemini-2.0-flash`), `crop_type` (optional string).
  * Returns: `disease_name`, `confidence`, `severity`, `symptoms`, `treatment_organic`, `treatment_chemical`, `irrigation_advice`.
* `POST /api/voice/chat`:
  * JSON: `message` (text / transcription), `language` (`hi-IN`, `mr-IN`, `en-US`), `api_key` (optional user key), `model_name` (user-selected model), `device_id` (for live sensor context).
  * Returns: `reply_text`, `action_command` (if user commanded pump/mode change).

### 4.4 ESP32 Local LAN Endpoints (Port 80)
* `GET /api/status`: Real-time sensor readings, current mode, pump state, uptime, free heap.
* `POST /api/control`: Manual override (`{"pump": 1, "timeout": 120}`).
* `POST /api/mode`: Local mode switch (`{"mode": "EDGE_AUTO"}`).
* `POST /api/sync`: Full schedule/rule JSON payload cache for offline persistence in SPIFFS/RTC memory.

---

## 5. ESP32 Firmware Execution & Safety Logic

1. **Hardware Safety Rules (Highest Priority)**:
   * **Max Pump Run Cutout**: 180 seconds continuous run max. Reaching 180s forces a 10-minute lockout cooldown.
   * **Salinity Interlock**: Fertilizer relay remains OFF if EC > 2.2 dS/m or turbidity is out of bounds.
2. **Mode Precedence**:
   * **`EDGE_AUTO` (Default)**: Relays follow soil moisture hysteresis (<25% ON, >=60% OFF) and VPD/dew-point metrics.
   * **`MANUAL`**: Follows manual pulse command. Decrements timer every second; when timer hits 0, turns pump OFF and restores `EDGE_AUTO`.
   * **`SCHEDULED`**: Checks current NTP time against scheduled start times and duration windows.
   * **`CUSTOM_RULES`**: Evaluates rules against live smoothed sensor readings.
3. **Connection Loss Watchdog**:
   * If no telemetry sync response is received for >5 minutes (300s), ESP32 automatically falls back to `EDGE_AUTO`.

---

## 6. Client Application & Creation Details Guide (`SOIL_EDGE_APP_CREATION_GUIDE.md`)

The comprehensive markdown blueprint document covers:
1. **Application Overview & Single-Prompt Generation Blueprint**.
2. **Dynamic AI Settings Hub**: UI components for API Key entry and manual model string selection (no hardcoding).
3. **ESP32 Dual-Connection Manager**: Switch between Cloud API & Local ESP32 IP with live ping.
4. **Live Automation Inspector**: Real-time gauges, mode badges, actuator states.
5. **Scheduler & Custom Rule Builder**: Interactive schedule table, day selector, rule trigger modal.
6. **Plant Health Camera / Vision Diagnostic**: Photo upload / live snapshot view, diagnosis cards.
7. **Multilingual Voice Agronomist**: Floating liquid glass widget with audio visualizer.
8. **Liquid Glass UI Token System**: CSS variables, frosted glass panels, neon glows.
