# ESP32 Field Node Firmware

This is the **scaffold** for the firmware agent. It contains:

| File | Role |
|---|---|
| `SoilEdge_FieldNode/SoilEdge_FieldNode.ino` | Arduino sketch — main loop, sensor read, classify, act, upload |
| `SoilEdge_FieldNode/model_tree.h` | Header (you'll copy `backend/ml/artifacts/model_tree.h` here) |
| `SoilEdge_FieldNode/model_tree.c` | The trained tree (you'll copy `backend/ml/artifacts/model_tree.c` here) |

## Quick start (for the firmware agent)

```bash
# 1. Copy the trained model into the sketch folder
cp ../../backend/ml/artifacts/model_tree.c SoilEdge_FieldNode/
cp ../../backend/ml/artifacts/model_tree.h SoilEdge_FieldNode/

# 2. Open SoilEdge_FieldNode.ino in Arduino IDE / PlatformIO
# 3. Edit the configuration block at the top of the .ino:
#      WIFI_SSID, WIFI_PASSWORD, API_BASE, DEVICE_TOKEN, DEVICE_ID
# 4. Fill in the readSensors() function with your actual driver code
# 5. Flash to ESP32
```

## Wiring (from the project spec § 4)

| Signal | GPIO | Notes |
|---|---|---|
| DHT data | 4 | Temperature / humidity (DHT22) |
| Moisture | 32 | 12-bit ADC, capacitive sensor |
| pH | 34 | Input-only ADC, pH probe + module |
| EC | 35 | Input-only ADC, EC probe + module |
| Pump relay | 26 | Active HIGH or LOW per your module |
| Fertilizer relay | 27 | Pulse only — never continuous |

## What's already done

* The full decision tree is in C, 60 lines, no `malloc`, no libc.
* `safe_classify()` wraps it with sensor sanity checks + the
  EC ≥ 8 dS/m "reclamation" (class 4) guard that isn't in the
  training data but IS in the spec.
* The action → (pump, fertilizer) mapping matches
  `backend/app/services/soil_model.derive_pump_fertilizer` — same
  rules on both sides, so the dashboard preview matches the field.
* The HTTP POST to `/api/telemetry` follows the exact payload shape
  the backend expects (see `backend/README.md` § "ESP32 telemetry payload").
* The loop is offline-safe: classify + act happens BEFORE the upload
  attempt. If WiFi is down, automation continues.

## What's still TODO for the firmware agent

1. Implement `readSensors()` — the four ADC / DHT driver functions.
2. Calibrate raw ADC to physical units (moisture %, pH, dS/m, °C).
3. Decide on real polling cadence (10 min in scaffold — adjust to
   your battery budget and crop needs).
4. Add OTA update support so the model can be updated remotely.
5. Add deep-sleep between polls if running on battery.
6. (Optional) Add local SD-card logging when WiFi is down, so no
   telemetry is lost.

## Training a new model

If the field agent wants to refresh the on-device model:

```bash
# On the PC (or backend) — retrain with the latest data
cd backend
python3 ml/train_esp32_model.py
cp ml/artifacts/model_tree.c ../../esp32-firmware/SoilEdge_FieldNode/
cp ml/artifacts/model_tree.h ../../esp32-firmware/SoilEdge_FieldNode/
# Then OTA-flash the new model to the device
```
