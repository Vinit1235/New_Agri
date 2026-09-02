# Smart Farming System — Detailed Project Plan

**Project name:** SoilEdge Field System  
**Goal:** Independent ESP32 AI automation for irrigation and fertilizer decisions, plus software-based crop health monitoring using Sentinel-2 (NDVI / NDWI) every 5 days.

---

## 1. Vision

Build a two-layer smart farming system:

| Layer | Role | Frequency | Depends on PC? |
|-------|------|-----------|----------------|
| **Field node (ESP32)** | Read soil sensors, run AI model, control pump and fertilizer | Every 5–15 minutes | **No** — fully offline |
| **Software dashboard** | Health monitoring, history, alerts, optional remote settings | Live sensors + **Sentinel every 5 days** | Yes (cloud/app) |

**Core principle:**  
The ESP32 must take automation actions in the field without the PC. The software monitors crop health and trends; it does not need to approve every pump cycle.

---

## 2. Problem Statement

- Different crops need different irrigation and salinity handling.
- Cheap soil sensors (moisture, temperature, pH, EC) can drive real-time decisions.
- Collecting hundreds of field samples for training is impractical.
- Heavy neural networks do not fit well on a resource-limited PC or ESP32.
- Satellite data (Sentinel-2) can monitor canopy health, but only every few days and not for minute-by-minute control.
- One global NDVI threshold cannot define “healthy” for all crops.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    SOFTWARE (Dashboard)                  │
│  • Live ESP32 readings (when online)                    │
│  • Sentinel-2 NDVI / NDWI every 5 days                  │
│  • Crop profiles + health status                        │
│  • History, alerts, optional threshold updates          │
└──────────────────────────▲──────────────────────────────┘
                           │ WiFi / MQTT / HTTP (optional)
┌──────────────────────────┴──────────────────────────────┐
│                 FIELD NODE (ESP32)                       │
│  Sensors → Tiny AI model → Relays                       │
│  • Moisture, Temperature, pH, EC                        │
│  • Pump ON/OFF, Fertilizer dose / block                 │
│  • Works with battery even if WiFi is down              │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Hardware Plan

### 4.1 Sensors and board

| Component | Purpose | Notes |
|-----------|---------|--------|
| ESP32 (WROOM-32) | Brain + WiFi | ADC max 3.3 V on GPIO |
| Soil moisture | Dry / wet | Capacitive preferred |
| Temperature | Heat stress | DHT22 or soil temp probe |
| pH probe + module | Acidity / alkalinity | Calibrate with buffers |
| EC probe + module | Salinity | Calibrate with standard solution |
| 12 V battery + DC-DC (5 V) | Field power | 5 V to ESP32 VIN only |
| Relay module | Actuators | Isolate pump/valve from ESP32 |

### 4.2 Suggested GPIO map

| Signal | GPIO | Notes |
|--------|------|--------|
| DHT data | 4 | Temperature / humidity |
| Moisture analog | 32 | 12-bit ADC |
| pH analog | 34 | Input-only ADC |
| EC analog | 35 | Input-only ADC |
| Pump relay | 26 | Active HIGH or LOW per module |
| Fertilizer relay | 27 | Short pulses only |

### 4.3 Actuators

| Actuator | Action |
|----------|--------|
| Irrigation pump | Water when dry; leach when EC high |
| Fertilizer valve / dosing pump | Dose only when safe; blocked on high EC or bad pH |

**Safety rules in firmware:**

- Never leave fertilizer valve open across long cycles.
- Cap maximum continuous pump time.
- Prefer “block fertilizer” when uncertain.

---

## 5. AI Model Plan (ESP32 automation)

### 5.1 Why a tiny model

- Limited PC resources for training.
- ESP32 has limited RAM/flash.
- Need offline, deterministic decisions.

**Choice:** Shallow **decision tree** trained on PC, exported as C `if` statements (or TinyML only if needed later).

### 5.2 Inputs (4 features)

1. Soil moisture (%)  
2. Soil / air temperature (°C)  
3. pH  
4. Electrical conductivity EC (dS/m)

### 5.3 Outputs (actions)

Aligned with salinity dataset style recommendations:

| Class | Recommended action | Pump | Fertilizer |
|-------|--------------------|------|------------|
| 0 | Maintain regular soil monitoring | Off (or light top-up if slightly dry) | Optional light dose if safe |
| 1 | Improve irrigation scheduling | On | Off |
| 2 | Use salt-tolerant crops / soil amendment | Off | Off |
| 3 | Apply leaching and drainage control | On (leach) | Off |
| 4 | Immediate reclamation / salinity control | On | Off |

### 5.4 Agronomic decision rules (base knowledge)

- `EC ≥ 8` → class 4 (critical salinity)  
- `EC ≥ 4` → class 3 (leach)  
- `EC ≥ ~2.2` → class 2 (amend / salt-tolerant)  
- Low moisture (crop-dependent) → class 1 (irrigate)  
- Else → class 0 (monitor)

**Fertilizer allowed only if:**

- Action is monitor (class 0)  
- EC is low  
- pH roughly 6.0–7.5  
- Moisture not extreme  
- pH not outside 5.5–7.8 (else “fix pH first”)

### 5.5 Crop profiles (multi-crop)

| Profile | Moisture low threshold (example) | Notes |
|---------|----------------------------------|--------|
| General | ~22% | Default mixed field |
| Vegetables | ~28% | Irrigate sooner |
| Cereals | ~20% | Slightly more drought tolerant |
| Pulses | ~18% | Avoid waterlogging |

Store planting date later for stage-aware satellite health (not required for ESP32 pump logic).

### 5.6 Training workflow

1. Generate or load labeled samples (public salinity / sensor datasets + rules).  
2. Train shallow tree (depth ~5–7) on PC or in-browser tool.  
3. Export:
   - `classify()` C function  
   - Full Arduino sketch  
   - Optional JSON model for software mirror  
4. Flash to ESP32.  
5. Calibrate ADC → physical units once in the field.

### 5.7 Datasets useful for soil AI

- Soil Salinity Sensor Dataset (includes EC, pH, moisture, temperature, Recommended_Action)  
- Edge Assisted Agricultural Sensor Dataset (moisture, temp, pH, crop health)  
- Other multi-sensor agronomy sets for fusion after column renaming and scaling  

**Note:** Sensor value ranges differ by hardware. Always normalize / calibrate; do not expect exact numeric match without calibration.

---

## 6. Satellite Health Monitoring Plan (Software)

### 6.1 Role of Sentinel-2

| Product | Meaning | Cadence |
|---------|---------|---------|
| **NDVI** | Greenness / canopy vigor | Target every **5 days** (cloud-free scenes) |
| **NDWI** | Water-related / moisture stress signal | Same |

**NDVI ≠ NDWI**

- NDVI ≈ how green the crop is  
- NDWI ≈ water-related stress / moisture signal from canopy  

Neither replaces the soil moisture probe. They complement it.

### 6.2 Why crop-specific health is required

Different crops have different healthy NDVI ranges and different phenology:

- Seedling stage → low NDVI is normal  
- Peak vegetative → high NDVI expected  
- Ripening → NDVI drop can be normal  

**Do not use one global NDVI cutoff for all crops.**

### 6.3 Health determination method

For each field store:

1. Crop type  
2. Planting date (estimate growth stage)  
3. NDVI time series (every available 5-day window)  
4. NDWI time series  
5. Optional baseline = recent healthy period for **that same field**

**Classify health using:**

1. **Crop + stage expected range**  
2. **Trend vs last 5–10 days** (relative drop is critical)  
3. **Merge with ESP32 soil data**

| Satellite | Soil sensors | Likely interpretation |
|-----------|--------------|------------------------|
| NDVI/NDWI dropping | Moisture low | Water stress → irrigate |
| Dropping | EC high | Salt stress → leach, no fertilizer |
| Dropping | Moisture & EC OK | Pest / disease / nutrient — inspect |
| Stable | Sensors normal | Healthy |

### 6.4 Datasets useful for NDVI / NDWI learning

| Dataset | NDVI | NDWI | Crops / notes |
|---------|------|------|----------------|
| Remote Sensing + Ag Ground Truths (Karnal) | Yes | Yes | Wheat, fortnightly |
| HR-VPP phenology NDVI (Mendeley) | Yes (5-day) | No | Barley, wheat, peas, maize, sunflower |
| Jianghan Plain indices | Yes | Yes | Cultivated land, multi-year |
| Multi-source crop classification (IEEE) | Yes + others | No | Rice, maize, coconut, sugarcane |
| Canadian Cropland (Sentinel-2) | Yes | No | 10 crop types |
| Crop Health & Environmental Stress (Kaggle) | Yes | No | Stress-oriented |

**Operational path:** For production, compute NDVI/NDWI for **your field polygon** from Sentinel-2 (Google Earth Engine, Sentinel Hub, or Copernicus), rather than relying only on static public CSVs.

### 6.5 Software jobs every 5 days

1. Fetch latest cloud-masked Sentinel-2 scene intersecting the field.  
2. Compute mean NDVI and NDWI inside field boundary.  
3. Save values + date + cloud percentage.  
4. Update health status (Healthy / Moderate stress / High stress).  
5. Generate alert if sharp drop or conflict with soil EC/moisture.  
6. Show trend chart (last 30–90 days).

---

## 7. Software Dashboard Plan

### 7.1 Main screens

1. **Overview**  
   - Field list  
   - Latest health badge (5-day satellite)  
   - Latest ESP32 action (if online)

2. **Live soil**  
   - Moisture, temperature, pH, EC  
   - Last AI decision (irrigate / leach / block fertilizer / monitor)

3. **Health (Sentinel)**  
   - NDVI / NDWI current values  
   - 5-day trend  
   - Crop-specific interpretation text

4. **Automation log**  
   - Timestamped pump / fertilizer events from ESP32

5. **Settings**  
   - Crop profile  
   - Planting date  
   - Moisture thresholds  
   - Relay safety limits  
   - Field polygon / coordinates for Sentinel

### 7.2 Connectivity

| Mode | Behavior |
|------|----------|
| ESP32 online | Publish sensor JSON + action via MQTT/HTTP |
| ESP32 offline | Automation continues; dashboard shows last known state |
| Software only | Still updates Sentinel health every 5 days |

Suggested payload from ESP32:

```json
{
  "device_id": "field_1",
  "moisture": 28.5,
  "temperature": 26.1,
  "ph": 6.7,
  "ec": 1.4,
  "action": 1,
  "action_name": "Improve irrigation scheduling",
  "pump": true,
  "fertilizer": false,
  "timestamp": "2026-08-31T09:00:00Z"
}
```

---

## 8. Implementation Phases

### Phase 0 — Foundations (1 week)

- Finalize wiring diagram and relay safety.  
- Confirm crop list for v1 (e.g. general, vegetables, cereals, pulses).  
- Create field ID + coordinates in software.

### Phase 1 — ESP32 automation MVP (1–2 weeks)

- Read 4 sensors with calibration placeholders.  
- Implement rule-based + exported tree `classify()`.  
- Drive pump and fertilizer relays.  
- Serial log of decisions.  
- **Success criteria:** Board irrigates when dry and blocks fertilizer when EC is high, with PC disconnected.

### Phase 2 — Model training pipeline (3–5 days)

- Train shallow tree from salinity/sensor datasets + agronomic rules.  
- Export Arduino sketch + model JSON.  
- Document calibration steps for moisture, pH, EC.

### Phase 3 — Optional telemetry (3–5 days)

- MQTT or HTTP publish from ESP32 when WiFi available.  
- Dashboard live soil panel.  
- Does not block offline automation.

### Phase 4 — Sentinel health module (1–2 weeks)

- Field polygon storage.  
- 5-day NDVI / NDWI fetch and store.  
- Crop + stage health rules + trend alerts.  
- Merge view: satellite health + soil EC/moisture.

### Phase 5 — Hardening (ongoing)

- Fail-safes (max pump time, fertilizer pulse limit).  
- Cloud-cover handling for Sentinel.  
- Per-crop threshold tuning from real seasons.  
- Battery and brown-out behavior.

---

## 9. Risk and Mitigation

| Risk | Mitigation |
|------|------------|
| Cheap probes inaccurate | One-time calibration; prefer relative trends + conservative fertilizer block |
| Model mismatch vs real soil | Start with rules; refine tree after one season of logs |
| Clouds block Sentinel | Keep last good scene; extend window; do not stop ESP32 automation |
| Wrong crop NDVI baseline | Crop profiles + field self-baseline + stage from planting date |
| Relay stuck ON | Max runtime timers; fertilizer never continuous |
| WiFi unreliable | Design automation fully offline first |

---

## 10. Success Metrics

| Metric | Target |
|--------|--------|
| Offline automation | ESP32 runs decisions with no PC/WiFi |
| Water response | Pump activates when moisture below crop threshold |
| Salinity safety | Fertilizer blocked when EC high |
| Health monitoring | NDVI/NDWI updated ~every 5 days when sky is clear |
| Multi-crop | At least 3 crop profiles with different moisture / NDVI expectations |
| Operator clarity | Dashboard shows both soil action and canopy health in plain language |

---

## 11. Deliverables Checklist

### Field

- [ ] Wired ESP32 node with sensors and relays  
- [ ] Calibrated moisture, pH, EC conversion formulas  
- [ ] Flashed firmware with local AI decisions  
- [ ] Proven offline pump / fertilizer behavior  

### Model

- [ ] Training pipeline (tree) for moisture, temp, pH, EC  
- [ ] Exported C `classify()` embedded in sketch  
- [ ] Crop profile thresholds documented  

### Software

- [ ] Device telemetry intake (optional but recommended)  
- [ ] Field registry (crop, planting date, polygon)  
- [ ] Sentinel NDVI/NDWI 5-day job  
- [ ] Health status + trend charts  
- [ ] Combined alerts (satellite + soil)  

### Documentation

- [ ] Wiring and GPIO map  
- [ ] Calibration procedure  
- [ ] Action meaning table for farmers  
- [ ] This plan kept updated after each phase  

---

## 12. Recommended Build Order (practical)

1. **ESP32 rule-based automation** (works this week)  
2. **Train and flash decision tree** (replace/enhance rules)  
3. **Dashboard live soil view**  
4. **Sentinel NDVI every 5 days for one field**  
5. **Add NDWI + crop-specific health logic**  
6. **Scale to multiple fields / crops**

---

## 13. One-Line Summary

**ESP32 decides and acts in the field every few minutes; software watches crop health from Sentinel every 5 days and helps the farmer understand stress — without blocking offline automation.**
