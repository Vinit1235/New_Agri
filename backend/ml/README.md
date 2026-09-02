# SoilEdge Field System — ML Pipeline

This directory contains the **data + training pipeline** that turns the raw
public datasets into the artefacts used by the backend at runtime.

## Layout

```
ml/
├── train_esp32_model.py     # train the soil-AI decision tree
├── derive_ndvi_bands.py     # derive empirical NDVI bands per crop
├── README.md                # this file
└── artifacts/               # generated — consumed by the backend
    ├── model_tree.json      # the trained tree (Python mirror)
    ├── model_tree.c         # the trained tree as C if-statements (ESP32 firmware)
    ├── model_tree.h         # header for the C function
    ├── model_meta.json      # training metadata (source, accuracy, ranges, …)
    └── ndvi_bands.json      # empirical NDVI bands per crop / stage
```

## Datasets

### Soil AI (decision tree)

| Dataset | Samples | URL | Role |
|---|---|---|---|
| **Smart-Agriculture** | 10,000 | https://github.com/ramonjsi/Smart-Agriculture | Primary training set |
| **GCEK Irrigation** | 150 | https://github.com/GCEKIoTCommunity/Irrigation-Dataset | Cross-validation |

**Smart-Agriculture** is a synthetic-but-realistic 10K-row dataset with
4 features (`pH`, `air temperature`, `soil humidity`, `EC` in dS/m) and
3 action classes (no action, watering, fertigation). The European decimal
separator is normalised at load time.

**GCEK Irrigation** is a real 150-row ESP32 field trial with raw ADC
moisture, soil temperature, air temperature, humidity, and a binary
irrigation label.

### Satellite health (NDVI bands)

| Dataset | Samples | URL | Role |
|---|---|---|---|
| **CY-Bench sample** | 137K | https://github.com/WUR-AI/sample_data | Empirical NDVI band derivation |

**CY-Bench** (AgML Crop Yield Benchmark) provides ~weekly MODIS NDVI
for wheat and maize across Spain and the Netherlands, 2001-2023. We
rescale each crop's p05 → 0.20 (fallow) and p95 → 0.85 (peak) and take
the (p25, p75) within each stage's day-of-year window.

## Reproduce

```bash
cd backend
python3 ml/train_esp32_model.py    # writes artifacts/model_*
python3 ml/derive_ndvi_bands.py    # writes artifacts/ndvi_bands.json
```

Both scripts only need `numpy` + `pandas` (no sklearn). They use a
hand-rolled CART decision tree.

## Model card (soil AI)

* **Type:** CART decision tree (Gini, depth ≤ 5)
* **Features:** `pH` (0-14), `temperature` (°C), `moisture` (%), `ec` (dS/m)
* **Classes:** 5 (monitor, irrigate, amend, leach, reclamation)
* **Training accuracy:** 100% on full 10K
* **5-fold CV accuracy:** 99.95%
* **Most important feature:** moisture (65%), then EC (26%)
* **Hardware target:** ESP32 — model exports to ~60 lines of C, no RAM
  allocation, no library deps

### Verdict mapping (smart-agri → spec)

| Source label | Conditions | Spec action |
|---|---|---|
| 0 (no action) | any | 0 (monitor) |
| 1 (watering) | EC < 2.2 | 1 (improve irrigation) |
| 1 (watering) | 2.2 ≤ EC < 4 | 2 (amend / salt-tolerant) |
| 1 (watering) | EC ≥ 4 | 3 (leaching) |
| 2 (fertigation) | safe (low EC, in-band pH, not extreme moisture) | 0 (monitor) + fert=True |
| 2 (fertigation) | unsafe | 0 (monitor) |

The class-4 "reclamation" (EC ≥ 8) is not present in the training data;
the ESP32 firmware will produce it on real readings by an additional
guard (`if (ec >= 8.0f) return 4;`) — see `model_tree.c` to add it.

## NDVI band card

Empirical per-stage NDVI bands (0..1), derived from CY-Bench:

| Crop | Seedling | Vegetative | Flowering | Ripening | Fallow |
|---|---|---|---|---|---|
| **wheat** | 0.25–0.54 | 0.36–0.62 | 0.62–0.78 | 0.63–0.81 | 0.49–0.70 |
| **maize** | 0.49–0.69 | 0.64–0.78 | 0.65–0.82 | 0.62–0.80 | 0.35–0.63 |
| **rice** | 0.47–0.67 | 0.66–0.80 | 0.61–0.80 | 0.58–0.77 | 0.33–0.61 |
| **vegetables** | 0.26–0.51 | 0.48–0.68 | 0.67–0.81 | 0.58–0.79 | 0.36–0.64 |
| **cereals** | 0.25–0.54 | 0.36–0.62 | 0.62–0.78 | 0.63–0.81 | 0.49–0.70 |
| **pulses** | 0.30–0.56 | 0.52–0.69 | 0.68–0.81 | 0.63–0.81 | 0.41–0.67 |

Wheat and maize bands are fitted to the data; rice/vegetables/cereals/
pulses are derived from those two profiles for crops that share
phenology (per-stage median of the wheat+maize profile, shifted to the
crop's typical cycle length).

## Drop-in C for ESP32

`artifacts/model_tree.c` contains a single function:

```c
int classify(float ph, float temperature, float moisture, float ec);
```

returns 0..4. Compile with `-O2`, no stdlib needed. Memory footprint:
~50 bytes of code, zero heap, zero stack beyond arguments.

For the firmware, the team should:
1. Copy `model_tree.c` + `model_tree.h` into the Arduino sketch folder.
2. Add the safety guard for the missing class-4 case:

   ```c
   int safe_classify(float ph, float temperature, float moisture, float ec) {
     if (ec >= 8.0f) return 4;          // critical salinity
     if (ec < 0.0f || ec > 20.0f) return 0;  // sensor sanity
     if (moisture < 0.0f || moisture > 100.0f) return 0;
     if (ph < 0.0f || ph > 14.0f) return 0;
     return classify(ph, temperature, moisture, ec);
   }
   ```
3. Map the returned action to the local `pump` and `fertilizer` GPIO
   pins (the mapping is also encoded in
   `app/services/soil_model.derive_pump_fertilizer` if you want a
   Python-side mirror).
