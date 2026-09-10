# SoilEdge Smart Farming System

SoilEdge is an end-to-end IoT and AI-powered smart farming platform. It integrates a physical ESP32 sensor node, a FastAPI backend, an interactive Voice Assistant, and a modern Web Dashboard to monitor soil health, automate irrigation, and analyze satellite crop data.

## 🌟 Key Features

* **ESP32 IoT Node:** Reads Soil Moisture and DHT11 (Temperature/Humidity) sensors, hosting a local fallback web dashboard.
* **Live Telemetry Sync:** Seamlessly posts sensor data to the backend via Wi-Fi.
* **AI Voice Assistant:** An interactive voice-to-voice (and text) agent that can analyze field data, trigger irrigation, and answer agricultural questions using Gemini.
* **FastAPI Backend:** Handles device registration, telemetry ingestion, user auth, and satellite data fetching (Sentinel-2 NDVI/NDWI).
* **Modern Web Dashboard:** A responsive, dark-themed vanilla HTML/JS frontend with live charts, interactive irrigation controls, and a floating AI Voice Assistant widget.

---

## 🏗️ System Architecture

| Component | Role | Technology |
|---|---|---|
| **ESP32 Field Node** | Reads sensors (Moisture, DHT11), hosts local dashboard, posts telemetry via HTTP. | C++ (Arduino IDE) |
| **Backend API** | Auth, field/device registry, telemetry ingest, satellite health scoring, Voice API. | Python (FastAPI) |
| **Frontend Dashboard** | Login, field overview, live sensor charts, AI Voice Assistant widget. | HTML / CSS / JS |

---

## 🚀 Quick Start Guide

### 1. Run the Backend & Frontend
The backend handles the API and automatically serves the frontend dashboard.

```bash
# Navigate to the backend directory
cd backend

# Create and activate a virtual environment
python -m venv .venv
# On Windows: .venv\Scripts\activate
# On Mac/Linux: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the server (binds to all network interfaces for ESP32 access)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

* **Website Dashboard:** Open [http://localhost:8000/login.html](http://localhost:8000/login.html)
  * *Demo Account:* `farmer@soiledge.com` / `farmer123`
* **API Documentation:** Open [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Configure the ESP32
1. Open `esp32-firmware/SoilEdge_FieldNode/SoilEdge_FieldNode.ino` in Arduino IDE.
2. Update the Wi-Fi credentials (`ssid` and `password`).
3. Update `API_BASE` with your computer's local Wi-Fi IP address (e.g., `http://192.168.1.50:8000`).
4. Ensure `SEND_TO_BACKEND = true;` to sync data to your dashboard.
5. Upload to your ESP32.

**Wiring Check:**
* **DHT11:** VCC to 3.3V, GND to GND, DATA to Pin 4.
* **Soil Sensor:** VCC to 3.3V, GND to GND, AOUT to Pin 34.

---

## 🎙️ AI Voice Assistant
The platform includes a floating AI Voice widget integrated into the frontend. 
* Click the microphone icon in the bottom right of the dashboard.
* Speak naturally (e.g., *"What is my soil moisture today?"* or *"Turn on the water pump"*).
* The assistant fetches live telemetry from the SQLite database and responds audibly using text-to-speech.

---

## 📁 Repository Layout

```text
SoilEdge-Field-System/
├── backend/                     ← Python FastAPI service
│   ├── app/                     ← Routers, models, auth, and voice services
│   ├── ml/                      ← Training pipeline for decision tree
│   └── requirements.txt
├── docs/                        ← Project specifications
├── esp32-firmware/              ← Arduino sketch for the field node
│   └── SoilEdge_FieldNode/      ← Main ESP32 code
└── frontend/                    ← HTML/CSS/JS web application
    ├── dashboard.html           ← Main telemetry dashboard
    ├── smart-watering.html      ← Irrigation controls
    ├── voice-assistant.html     ← Standalone voice interface
    └── js/                      ← Voice widget and chart logic
```
