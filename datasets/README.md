# Datasets

Training data for the SoilEdge Field System ML pipeline.

| File | Rows | Used for |
|---|---|---|
| `Smart-Agriculture.csv` | 10,000 | Train the ESP32 soil-AI decision tree |
| `Irrigation-Dataset.xlsx` | 150 | Cross-validation / sanity check |
| `ndvi_wheat_ES.csv` | 60,154 | Derive empirical NDVI bands (wheat, Spain) |
| `ndvi_wheat_NL.csv` | 11,728 | Derive empirical NDVI bands (wheat, Netherlands) |
| `ndvi_maize_ES.csv` | 53,942 | Derive empirical NDVI bands (maize, Spain) |
| `ndvi_maize_NL.csv` | 11,757 | Derive empirical NDVI bands (maize, Netherlands) |

---

## Data lineage

### 1. Smart-Agriculture (soil AI)

* **Source:** https://github.com/ramonjsi/Smart-Agriculture
* **File:** `Dataset_smart_agriculture.csv`
* **Schema:** `ph_measurement, Temperature, Soil_Humidity, Electrical_conductivity(uS/cm), Target`
* **Target:** 0 = no action, 1 = watering, 2 = fertigation
* **Note on units:** the `Electrical_conductivity` column header says µS/cm but
  the numeric range (1.1 - 6.1) matches the typical agronomic dS/m scale.
  The training script treats the values as **dS/m** directly.
* **Note on decimal separator:** the CSV uses `,` (European) — handled in
  `backend/ml/train_esp32_model.py::load_smart_agriculture`.
* **Class remap to the 5 spec action codes** is in
  `backend/ml/train_esp32_model.py::remap_actions`.

### 2. GCEK Irrigation-Dataset (cross-validation)

* **Source:** https://github.com/GCEKIoTCommunity/Irrigation-Dataset
* **File:** `Project_datasheet_2019-2020.xlsx`
* **Schema:** `CropType, CropDays, Soil Moisture (raw ADC), Soil Temperature, Temperature, Humidity, Irrigation(Y/N)`
* **Use:** cross-validation only. The raw ADC needs calibration before
  being used as input to the soil-AI model; we use it to confirm the
  decision tree's *qualitative* behaviour on a real ESP32 deployment.

### 3. CY-Bench (NDVI bands)

* **Source:** https://github.com/WUR-AI/sample_data
  (a 38 MB `workshop-data.zip` was cloned from the parent
  https://github.com/WUR-AI/AgML-CY-Bench repo).
* **Files used:** the four `ndvi_<crop>_<country>.csv` files.
* **Source sensor:** MODIS Terra Daily L3 Global 0.05° CMG (MOD09CMG),
  processed by CY-Bench into weekly NDVI at the admin-region level.
* **Time range:** 2001-01-01 → 2023-12-27.
* **Rescaling:** raw NDVI is on a 0-250-ish integer scale. We map
  per-crop p05 → 0.20 (fallow) and p95 → 0.85 (peak) so the bands land
  in the agronomically-expected 0.0-1.0 range. This is the dominant
  source of "ground truth" for the spec's 5 crop profiles
  (`wheat`, `maize`, `rice`, `vegetables`, `cereals`, `pulses`).

---

## Re-fetching the data

If you only have the NDVI CSVs (5.4 MB total) but need the full CY-Bench
sample for the other crops (rice, soybean, etc.), clone the upstream:

```bash
git clone https://github.com/WUR-AI/sample_data.git /tmp/cybench
cp /tmp/cybench/wheat/*/*.csv datasets/
cp /tmp/cybench/maize/*/*.csv datasets/
```

For Smart-Agriculture and Irrigation-Dataset, see the URLs in the
*Source* column above.

---

## License / citation

* **Smart-Agriculture** — synthetic, no formal citation required.
* **GCEK Irrigation-Dataset** — by GCEK IoT Community, on GitHub.
* **CY-Bench** — by Biradar et al. (Wageningen University & Research);
  cite the paper at https://github.com/BigDataWUR/AgML-CY-Bench if
  you use these NDVI files in academic work.
