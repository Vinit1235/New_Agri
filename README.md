<div align="center">

# 🌾 Krishinayan / SoilEdge Smart Farming System

### **Offline-First Edge AI • Copernicus Sentinel-2 Satellite Intelligence • Multilingual Gemini Voice Assistant • Liquid Glass IoT Command Hub**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![ESP32](https://img.shields.io/badge/Hardware-ESP32%20DevKit-E7352C.svg?style=for-the-badge&logo=espressif&logoColor=white)](https://www.espressif.com)
[![Copernicus Sentinel-2](https://img.shields.io/badge/Satellite-Sentinel--2%20L2A-005BBB.svg?style=for-the-badge&logo=esa&logoColor=white)](https://dataspace.copernicus.eu)
[![Google Gemini](https://img.shields.io/badge/AI-Gemini%202.0%20Flash-4285F4.svg?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)

<br/>

**Krishinayan (SoilEdge)** is a full-stack, precision agricultural management ecosystem that bridges physical edge IoT sensor nodes, on-chip autonomous intelligence, satellite earth observation, and generative AI advisory. Designed for both connected and intermittent/offline field environments, it protects crops, conserves water, and prevents soil salinity damage through data-driven closed-loop automation.

</div>

---

## 📑 Table of Contents

- [System Architecture](#-system-architecture)
- [Key Pillars & Core Features](#-key-pillars--core-features)
  - [1. ESP32 Field Node v3.0 & On-Chip Edge Intelligence](#1-esp32-field-node-v30--on-chip-edge-intelligence)
  - [2. Live USB Serial Monitor & Zero-WiFi Debugging](#2-live-usb-serial-monitor--zero-wifi-debugging)
  - [3. Multilingual AI Agronomist Voice Assistant](#3-multilingual-ai-agronomist-voice-assistant)
  - [4. Copernicus Sentinel-2 Satellite Crop Health (NDVI / NDWI)](#4-copernicus-sentinel-2-satellite-crop-health-ndvi--ndwi)
  - [5. Smart Fertigation & Soil Salinity Interlocks](#5-smart-fertigation--soil-salinity-interlocks)
  - [6. Liquid Glass Web Dashboard Suite](#6-liquid-glass-web-dashboard-suite)
- [Hardware Wiring & Pinout Reference](#-hardware-wiring--pinout-reference)
- [Repository Layout](#-repository-layout)
- [Quick Start Guide](#-quick-start-guide)
  - [Prerequisites](#prerequisites)
  - [1. Backend Setup](#1-backend-setup)
  - [2. ESP32 Firmware Flashing](#2-esp32-firmware-flashing)
  - [3. Running the Hardware Simulator (No ESP32 Needed)](#3-running-the-hardware-simulator-no-esp32-needed)
- [Environment Configuration (`.env`)](#-environment-configuration-env)
- [API Reference Overview](#-api-reference-overview)
- [Automated Testing & Verification](#-automated-testing--verification)
- [License](#-license)

---

## 🏗️ System Architecture

```mermaid
graph TD
    subgraph Edge Hardware ["🌱 Edge IoT Layer (ESP32 DevKit)"]
        S_Moist["Capacitive Soil Sensor (GPIO32)"] -->|ADC1 via 2N2222 Switch| ESP32["ESP32 Microcontroller"]
        S_DHT["DHT11 Air Temp & Humidity (GPIO4)"] -->|OneWire Protocol| ESP32
        S_Turb["Turbidity Sensor (GPIO34)"] -->|ADC1 Voltage Divider| ESP32
        S_Flow["Hall-Effect Flow Meter (GPIO27)"] -->|Falling-Edge ISR Pulses| ESP32
        ESP32 -->|GPIO26 Relay Output| Pump["Irrigation Pump / Solenoid Valve"]
        ESP32 -->|Local Edge Math| EdgeEngine["Edge Intelligence Engine<br/>• VPD (kPa) & Dew Point<br/>• Fungal Risk & Wilting ETA<br/>• Autonomous Hysteresis Loop"]
        ESP32 -.->|Local HTTP Webserver| LocalDash["ESP32 AP Fallback Dashboard (:80)"]
    end

    subgraph Backend Layer ["⚡ FastAPI Central Gateway (:8000)"]
        API["FastAPI App Gateway"]
        AuthServ["JWT Authentication & RBAC"]
        TelemetryIngest["Telemetry Ingestion & Aggregation"]
        SatScheduler["Copernicus Sentinel-2 Scheduler (5-Day Job)"]
        VoiceService["Gemini 2.0 Flash Agronomy Engine"]
        SerialService["PySerial SSE Streaming Router (/api/serial)"]
        DB[("SQLite / PostgreSQL Database")]

        API --> AuthServ
        API --> TelemetryIngest
        API --> SatScheduler
        API --> VoiceService
        API --> SerialService
        TelemetryIngest --> DB
    end

    subgraph External Cloud ["🛰️ Cloud & Geospatial Services"]
        CopernicusAPI["Copernicus Data Space Ecosystem (Sentinel-2 L2A)"]
        GeminiAPI["Google Gemini AI Studio API"]
        SatScheduler -->|Bands B04, B08, B8A, B11| CopernicusAPI
        VoiceService -->|Context-Aware Prompts| GeminiAPI
    end

    subgraph Frontend Layer ["🖥️ Liquid Glass Web Dashboard"]
        ExecDash["Executive Farm Command Dashboard (dashboard.html)"]
        IrrigationHub["Smart Watering & VPD Control (smart-watering.html)"]
        SatGIS["Sentinel-2 Multispectral GIS (crop-health.html)"]
        FertHub["Smart Fertilizer & Salinity (smart-fertilizer.html)"]
        YieldForecaster["AI Yield Forecaster (ai-yield-prediction.html)"]
        SerialMonitor["USB Hardware Monitor (esp32-monitor.html)"]
        VoiceWidget["Multilingual Voice Widget (Hindi, Marathi, English)"]
    end

    ESP32 -->|HTTP POST /api/telemetry| TelemetryIngest
    ESP32 -.->|USB COM Port / 115200 Baud| SerialService
    Frontend Layer -->|REST API + Bearer JWT| API
    Frontend Layer -->|Server-Sent Events / SSE| SerialService
```

---

## 🌟 Key Pillars & Core Features

### 1. ESP32 Field Node v3.0 & On-Chip Edge Intelligence
- **Multi-Sensor Acquisition:** Reads soil moisture (Capacitive), ambient temperature and relative humidity (DHT11), water turbidity (NTU), and water flow rate via hall-effect ISR pulse counting.
- **Transistor Corrosion Protection:** Uses a 2N2222 NPN transistor on GPIO25 to power the soil probe only during measurement intervals, preventing galvanic degradation and extending probe lifespan.
- **On-Chip Microclimatic Edge Math:**
  - **Vapor Pressure Deficit (VPD):** Calculated in kPa to quantify atmospheric transpiration stress.
  - **Dew Point:** Computed via the Magnus-Tetens formula to determine condensation thresholds.
  - **Fungal Pathogen Risk Index:** Evaluates combined high-humidity and temperature sustained exposure.
  - **Soil Depletion Rate & Wilting ETA:** Real-time percentage drop rate per hour predicting hours remaining until wilting point.
- **Autonomous Hysteresis Irrigation Loop:** Runs locally without cloud connectivity. Automatically engages irrigation when soil moisture drops below **25%** and terminates once moisture reaches **60%**, protected by a **3-minute max-run failsafe cutout** and a **10-minute anti-cycling cooldown**.
- **RTC Deep-Sleep Power Optimization:** Preserves cumulative water volume across deep-sleep cycles using `RTC_DATA_ATTR`.
- **Embedded Webserver:** Serves a standalone local dark-mode diagnostic dashboard and `/data` JSON endpoint directly over Wi-Fi AP.

### 2. Live USB Serial Monitor & Zero-WiFi Debugging
- **Zero-Network Hardware Diagnostics:** Streams raw and structured serial telemetry directly from ESP32 DevKit to the browser over USB via Server-Sent Events (`/api/serial/stream`).
- **Interactive Web Terminal (`esp32-monitor.html`):** Real-time baud selector, auto-scroll terminal, actuator command toggles (`FAN:ON`, `FAN:OFF`, `AUTO:ON`, `SET:TEMP:xx`), and live telemetry graphs for temperature, humidity, and moisture.
- **Visual Breadboard Wiring Reference:** Interactive SVG breadboard pinout visualizer embedded directly into the monitor interface (`esp32_breadboard_map.html` and `esp32_wiring_reference.html`).

### 3. Multilingual AI Agronomist Voice Assistant
- **Gemini 2.0 Flash Inference:** Ingests live telemetry (soil moisture, temperature, humidity, pH, EC, water usage, and pump state) into the AI agronomist context.
- **Trilingual Speech & Dialogue:** Full conversational voice support in **English**, **Hindi (हिंदी)**, and **Marathi (मराठी)**.
- **Dual Form Factor:**
  - Dedicated full-page voice console (`voice-assistant.html`).
  - Floating interactive voice widget embedded across every page in the dashboard.
- **Hands-Free Operation:** Web Speech API continuous recognition and text-to-speech synthesis with automatic fallback.

### 4. Copernicus Sentinel-2 Satellite Crop Health (NDVI / NDWI)
- **Automated 5-Day Orbital Synchronization:** Background scheduler queries the Copernicus Data Space Ecosystem for cloud-filtered Sentinel-2 L2A tiles.
- **Vegetation Indices Calculated:**
  - **NDVI (Normalized Difference Vegetation Index):** Canopy biomass, chlorophyll vitality, and growth stages.
  - **NDWI (Normalized Difference Water Index):** Plant water content and internal canopy hydration stress.
  - **EVI (Enhanced Vegetation Index):** Atmospheric aerosol correction for dense vegetation.
- **Zoning & Alert Matrix:** Generates high-resolution spatial health heatmaps and sends automatic alerts when canopy stress is detected.

### 5. Smart Fertigation & Soil Salinity Interlocks
- **Salinity Protection Interlock:** Continuously monitors soil Electrical Conductivity (EC) and pH. If salt build-up exceeds safe crop tolerances, chemical fertilizer injection is **strictly blocked** and a soil leaching cycle is initiated to protect root structures.
- **Targeted NPK Nutrition:** Dynamic macronutrient recommendation algorithms tailored to specific crop stages and soil test results.

### 6. Liquid Glass Web Dashboard Suite
- **Aesthetic Neu-Glassmorphic UI:** Modern dark theme featuring translucent glass surfaces, dynamic gradients, responsive micro-animations, and CSS token architecture.
- **Application Pages:**
  - 📊 `dashboard.html` — Live telemetry streams, multi-parameter charting, system alarms, and quick pump overrides.
  - 💧 `smart-watering.html` — Closed-loop automation controls, moisture hysteresis, VPD monitoring, and flow records.
  - 🛰️ `crop-health.html` — Multispectral Sentinel-2 satellite imagery, GIS crop boundaries, and vegetation index timeline.
  - 🧪 `smart-fertilizer.html` — NPK prescription scheduler, EC salinity interlocks, and soil pH monitoring.
  - 📈 `ai-yield-prediction.html` — Machine learning crop yield forecaster and historical production benchmarks.
  - 🔌 `esp32-monitor.html` — Real-time USB Serial streaming monitor with interactive breadboard layout.
  - 🎙️ `voice-assistant.html` — Standalone multilingual AI agronomist interface.
  - 🔐 `login.html` & `signup.html` — JWT-based user authentication and farm registration.

---

## 🔌 Hardware Wiring & Pinout Reference

| Component | ESP32 Pin | Signal / Pin Type | Function | Notes / External Circuitry |
|---|---|---|---|---|
| **Soil Moisture Sensor** | `GPIO32` | Analog In (`ADC1_CH4`) | Soil volumetric water content | Powered via 2N2222 switch on GPIO25 |
| **DHT11 Sensor** | `GPIO4` | Digital I/O | Air Temperature & Relative Humidity | 10kΩ pull-up resistor to 3.3V |
| **Turbidity Sensor** | `GPIO34` | Analog In (`ADC1_CH6`) | Water clarity & NTU measurement | 5V output divided via 5.6kΩ / 10kΩ divider |
| **Water Flow Sensor** | `GPIO27` | Digital In (Interrupt) | Pulse frequency = L/min flow rate | Hall-effect sensor; 10kΩ pull-up to 3.3V |
| **Soil Sensor Power Switch** | `GPIO25` | Digital Out | Anti-corrosion power gating | Drives 2N2222 NPN base via 1kΩ resistor |
| **Relay / Pump Actuator** | `GPIO26` | Digital Out | Irrigation pump / Solenoid control | HIGH = Active / Pump ON |
| **Status Indicator LED** | `GPIO2` | Digital Out | Visual pump / heartbeat indicator | Built-in onboard blue LED |
| **Serial USB Interface** | `UART0` (TX0/RX0) | USB Serial | Live logging & command interface | 115200 Baud |

> [!TIP]
> Open [esp32_breadboard_map.html](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/esp32_breadboard_map.html) or [esp32_wiring_reference.html](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/esp32_wiring_reference.html) in your browser for the full interactive wiring diagram and breadboard schematic.

---

## 📁 Repository Layout

```text
SoilEdge-Field-System/
├── backend/                             # FastAPI Python Core
│   ├── app/
│   │   ├── config.py                    # Environment settings (Pydantic Settings)
│   │   ├── database.py                  # SQLAlchemy engine & session factory
│   │   ├── models.py                    # DB ORM schemas (Users, Fields, Devices, Telemetry)
│   │   ├── schemas.py                   # Pydantic request & response models
│   │   ├── main.py                      # FastAPI entrypoint & static mount
│   │   ├── jobs/
│   │   │   └── satellite_job.py         # 5-day Copernicus Sentinel-2 scheduler
│   │   └── routers/
│   │       ├── auth.py                  # User authentication & JWT issuance
│   │       ├── data.py                  # Data aggregation & analytics
│   │       ├── devices.py               # ESP32 hardware registration & tokens
│   │       ├── fields.py                # Field polygon mapping & crop configuration
│   │       ├── health.py                # Satellite NDVI/NDWI calculation endpoints
│   │       ├── model.py                 # ML decision-tree rules & yield prediction
│   │       ├── serial_monitor.py        # USB serial port detection & SSE streaming
│   │       ├── server.py                # Network discovery & host IP resolution
│   │       ├── telemetry.py             # High-throughput ESP32 data ingestion
│   │       └── voice.py                 # Gemini 2.0 Flash Multilingual Voice AI
│   └── requirements.txt                 # Backend Python dependencies
├── esp32-firmware/
│   ├── SoilEdge_FieldNode_v3/           # Production Firmware (Flow meter + Turbidity + VPD + Hysteresis)
│   │   └── SoilEdge_FieldNode_v3.ino
│   └── SoilEdge_FieldNode/              # Standard Edition Firmware
│       └── SoilEdge_FieldNode.ino
├── esp32_firmware_Final/                # USB Serial & Dryer Controller Firmware
│   └── esp32_firmware_Final.ino
├── frontend/                            # Liquid Glass Web Application Suite
│   ├── dashboard.html                   # Central IoT telemetry dashboard
│   ├── smart-watering.html              # Closed-loop irrigation & flow metering
│   ├── crop-health.html                 # Copernicus Sentinel-2 NDVI/NDWI GIS maps
│   ├── smart-fertilizer.html            # NPK advisory & EC salinity interlocks
│   ├── ai-yield-prediction.html         # Harvest forecasting & crop analytics
│   ├── esp32-monitor.html               # Real-time USB Serial streaming interface
│   ├── voice-assistant.html             # Standalone multilingual AI agronomist
│   ├── login.html / signup.html         # JWT authentication pages
│   └── js/                              # Reusable voice widgets & chart modules
├── docs/                                # Technical specifications & architecture plans
├── esp32_breadboard_map.html            # Visual breadboard circuit wiring map
├── esp32_wiring_reference.html          # Hardware schematics & pin configuration
├── test_esp32_simulation.py             # Standalone software IoT simulator
└── run_tests.ps1                        # Complete automated system test suite
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.10+**
- **Arduino IDE 2.x** (with ESP32 Board Package installed)
- **Google Gemini API Key** (for multilingual voice assistance)
- **Copernicus Data Space Credentials** *(Optional for live satellite imagery)*

---

### 1. Backend Setup

```bash
# 1. Clone repository and navigate to backend directory
cd backend

# 2. Create and activate a virtual environment
# Windows:
python -m venv .venv
.venv\Scripts\activate
# Linux/macOS:
python3 -m venv .venv
source .venv/bin/activate

# 3. Install required Python packages
pip install -r requirements.txt

# 4. Configure your environment variables (.env)
# Create a .env file from the template below if needed

# 5. Start the FastAPI server (accessible on local network for ESP32)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Once started:
- 🌐 **Web Dashboard:** [http://localhost:8000/login.html](http://localhost:8000/login.html)
- 📚 **Interactive Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- 🔌 **Live USB Serial Monitor:** [http://localhost:8000/esp32-monitor.html](http://localhost:8000/esp32-monitor.html)

**Demo Credentials:**
- **Email:** `farmer@soiledge.com` (or create a new user via `signup.html`)
- **Password:** `farmer123`

---

### 2. ESP32 Firmware Flashing

1. Open Arduino IDE and install required libraries:
   - `DHT sensor library` by Adafruit
   - `Adafruit Unified Sensor`
2. Open [`esp32-firmware/SoilEdge_FieldNode_v3/SoilEdge_FieldNode_v3.ino`](file:///c:/Users/VINIT/Desktop/Smile_Clinc/New_Agri/esp32-firmware/SoilEdge_FieldNode_v3/SoilEdge_FieldNode_v3.ino).
3. Update your local Wi-Fi and server configuration:
   ```cpp
   const char* ssid            = "YOUR_WIFI_SSID";
   const char* password        = "YOUR_WIFI_PASSWORD";
   const char* API_BASE        = "http://192.168.1.50:8000"; // Your PC's LAN IP
   const char* DEVICE_TOKEN    = "esp32_secret_token_123";
   const char* DEVICE_ID       = "esp32-01";
   const bool  SEND_TO_BACKEND = true;
   ```
4. Select board **ESP32 Dev Module** and the correct COM Port.
5. Click **Upload**.
6. Open Serial Monitor at **115200 Baud** to verify Wi-Fi association and initial sensor readings.

---

### 3. Running the Hardware Simulator (No ESP32 Needed)

You can run the full end-to-end platform without physical hardware using the built-in field simulator:

```bash
python test_esp32_simulation.py
```

This simulator generates realistic sensor telemetry (dynamic soil moisture curves, day/night ambient temperature oscillations, calculated VPD, and automated hysteresis irrigation loops) and posts it directly to your running FastAPI server.

---

## ⚙️ Environment Configuration (`.env`)

Create a `.env` file in the `backend/` directory with the following variables:

```ini
# Application Settings
APP_NAME="SoilEdge Field System"
APP_ENV=dev
APP_PORT=8000
SECRET_KEY="replace-with-a-secure-random-32-character-secret-key"
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Database Connection (SQLite by default, PostgreSQL supported)
DATABASE_URL="sqlite:///./soiledge.db"

# Google Gemini Voice Assistant
GEMINI_API_KEY="your-gemini-api-key-here"

# Copernicus Data Space Ecosystem (Sentinel-2 Satellites)
COPERNICUS_CLIENT_ID=""
COPERNICUS_CLIENT_SECRET=""
COPERNICUS_LOOKBACK_DAYS=15
COPERNICUS_MAX_CLOUD_PCT=30

# Telemetry Rate Limiting
TELEMETRY_RATE_PER_MIN=60
```

---

## 📡 API Reference Overview

| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/register` | `POST` | Create a new farmer account |
| `/api/auth/login` | `POST` | Authenticate user and receive Bearer JWT |
| `/api/fields` | `GET` / `POST` | List or register agricultural field parcels & GeoJSON polygons |
| `/api/devices` | `GET` / `POST` | Register ESP32 hardware devices and retrieve authentication tokens |
| `/api/telemetry` | `POST` | Ingest real-time ESP32 sensor telemetry (Moisture, Temp, Humidity, Turbidity, Flow) |
| `/api/telemetry/latest` | `GET` | Fetch latest telemetry for a field/device |
| `/api/health/calculate` | `POST` | Calculate Sentinel-2 NDVI/NDWI crop health indices |
| `/api/voice/chat` | `POST` | Conversational agronomy AI chat in English, Hindi, and Marathi via Gemini 2.0 |
| `/api/serial/ports` | `GET` | List available USB COM serial ports |
| `/api/serial/stream` | `GET` | Server-Sent Events (SSE) live serial stream from connected ESP32 |
| `/api/serial/command` | `POST` | Transmit serial command strings (`FAN:ON`, `PUMP:TOGGLE`, etc.) to ESP32 |

---

## 🧪 Automated Testing & Verification

The project includes PowerShell automated test suites to validate API integrity, telemetry ingestion, token authentication, and data pipelines:

```powershell
# Run the complete test suite
.\run_tests.ps1

# Run end-to-end integration flow validation
.\test_complete_flow.ps1

# Run clean system verification
.\test_system_clean.ps1
```

---

## 📄 License

This project is licensed under the **MIT License**. Feel free to use, modify, and distribute for educational, research, and commercial precision agriculture deployments.
