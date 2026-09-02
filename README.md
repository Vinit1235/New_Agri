# SoilEdge Field System

End-to-end smart-farming system with three components:

| Component | Role | Tech |
|---|---|---|
| **ESP32 field node** | Read sensors → run AI model → drive pump + fertilizer relays, fully offline | Arduino / C |
| **Backend API** | User auth, field/device registry, telemetry ingest, Sentinel-2 health scoring | Python (FastAPI) |
| **Frontend dashboard** | Login, field overview, live soil, Sentinel NDVI/NDWI charts, automation log | HTML / CSS / JS (vanilla) |

This repository contains the **backend** + **ML pipeline** + **ESP32 firmware
scaffold** + the **training data** needed to reproduce the trained model.

---

## Repository layout

```
SoilEdge-Field-System/
├── README.md                    ← you are here
├── backend/                     ← Python FastAPI service
│   ├── app/                     ← routers, models, services
│   ├── ml/                      ← training pipeline + trained artefacts
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── datasets/                    ← raw training data
│   ├── Smart-Agriculture.csv    ← 10K samples, primary soil-AI training set
│   ├── Irrigation-Dataset.xlsx  ← 150 ESP32 field readings (CV reference)
│   ├── ndvi_wheat_ES.csv        ← CY-Bench NDVI for wheat (Spain, 2001-2023)
│   ├── ndvi_wheat_NL.csv        ← CY-Bench NDVI for wheat (Netherlands)
│   ├── ndvi_maize_ES.csv
│   ├── ndvi_maize_NL.csv
│   └── README.md                ← data lineage + how to re-fetch
├── docs/
│   └── 01-Smart-Farming-System-Project-Plan.md   ← the original spec
└── esp32-firmware/              ← Arduino sketch scaffold for the field node
    ├── SoilEdge_FieldNode/
    └── README.md
```

---

## Quick start (backend)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set SECRET_KEY and (optionally) Copernicus credentials
uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000/docs for the auto-generated Swagger UI.

To re-train the soil-AI model or refresh the empirical NDVI bands:

```bash
cd backend
python3 ml/train_esp32_model.py     # → ml/artifacts/model_*
python3 ml/derive_ndvi_bands.py     # → ml/artifacts/ndvi_bands.json
bash     ml/smoke_test.sh           # end-to-end cURL test (server must be running)
```

---

## How the pieces fit together

```
ESP32 sensors (pH, T, moisture, EC)
        │
        ▼
ESP32 decision tree (ml/artifacts/model_tree.c)
        │  ← trained on 10K real samples (Smart-Agriculture)
        │  ← 99.95% 5-fold CV accuracy
        │
        ├──> Pump relay / fertilizer relay (offline automation)
        │
        └──> HTTP POST /api/telemetry
                │
                ▼
          FastAPI backend
                │
                ├──> Stores reading + automation event in SQLite
                ├──> Updates device.last_seen
                │
                └──> Every 5 days (APScheduler)
                       │
                       ▼
                  Copernicus / Sentinel-2 Process API
                       │
                       ▼
                  NDVI + NDWI per field
                       │
                       ▼
                  Empirical stage band (from CY-Bench 137K obs)
                       │
                       ▼
                  health verdict (healthy / moderate / high_stress / unknown)
                       │
                       ▼
                  Frontend dashboard
```

---

## Tech summary

| Layer | Technology |
|---|---|
| Backend | Python 3.11 + FastAPI + SQLAlchemy + APScheduler |
| Database | SQLite (dev) / PostgreSQL (prod-ready, swap `DATABASE_URL`) |
| Auth | JWT (HS256) for users, SHA-256 hashed tokens for devices |
| Satellite | Copernicus Dataspace / Sentinel Hub Process API |
| Model | Hand-rolled CART decision tree (5-class, depth ≤ 5) |
| Model source | 10K real sensor samples (ramonjsi/Smart-Agriculture) |
| NDVI bands | Empirical from 137K real NDVI obs (WUR-AI/AgML-CY-Bench) |
| ESP32 firmware | Drop-in C, 60 lines, no libc, no heap |

---

## Hand-off contracts

* **Backend ↔ Frontend** — REST API; see `backend/README.md` for the full table
* **ESP32 → Backend** — HTTP `POST /api/telemetry` with device-token auth;
  payload shape in `backend/README.md` § "ESP32 telemetry payload"
* **Backend → Copernicus** — Sentinel Hub Process API, evalscript in
  `backend/app/services/sentinel.py`
