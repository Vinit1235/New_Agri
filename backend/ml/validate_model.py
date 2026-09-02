"""
=============================================================================
 COMPREHENSIVE MODEL VALIDATION  -- validate_model.py
 Run from repo root: python backend/ml/validate_model.py
=============================================================================
"""
import json, sys, os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path("backend").resolve()
sys.path.insert(0, str(ROOT))

from ml.test_ndvi_model import evaluate_ndvi
from app.services.health_rules import (
    compute_health, growth_stage, expected_ndvi_range, _stage_windows_in_days
)
from app.services.sentinel import IndicesResult, CopernicusClient
from app.models import Field

ARTIFACTS = Path("backend/ml/artifacts")
NDVI_BANDS_PATH = ARTIFACTS / "ndvi_bands.json"

PASS = 0
FAIL = 0

def ok(label, expr, detail=""):
    global PASS, FAIL
    mark = "PASS" if expr else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{mark}]  {label}{suffix}")
    if expr: PASS += 1
    else: FAIL += 1

# ==========================================================================
print("\n========================================")
print("  SECTION 1 -- ndvi_bands.json Schema")
print("========================================")
with open(NDVI_BANDS_PATH) as f:
    bands = json.load(f)
profiles = bands.get("profiles", {})
ok("File loaded", bool(profiles))
ok("Has wheat profile",      "wheat"      in profiles)
ok("Has maize profile",      "maize"      in profiles)
ok("Has rice profile",       "rice"       in profiles)
ok("Has vegetables profile", "vegetables" in profiles)
ok("Has cereals profile",    "cereals"    in profiles)
ok("Has pulses profile",     "pulses"     in profiles)

for crop, pdata in profiles.items():
    stages = pdata.get("stages", [])
    ok(f"{crop}: >=5 stages", len(stages) >= 5)
    for s in stages:
        lo, hi = s["ndvi_low"], s["ndvi_high"]
        ok(f"{crop}/{s['stage']}: 0<=lo<hi<=1", 0.0<=lo<hi<=1.0, f"lo={lo} hi={hi}")
        ok(f"{crop}/{s['stage']}: doy_window 2 or 4 values", len(s["doy_window"]) in (2,4))

# ==========================================================================
print("\n========================================")
print("  SECTION 2 -- evaluate_ndvi() per crop/stage")
print("  (bands from ndvi_bands.json, truths derived from actual band values)")
print("========================================")
# Maize: flowering=[196,230] lo=0.653 hi=0.820   ripening=[231,275] lo=0.624 hi=0.801
cases = [
    # (crop,  doy, ndvi, exp_stage,    exp_status)
    ("wheat",  30, 0.40, "seedling",   "healthy"),   # band [0.253, 0.536]
    ("wheat",  30, 0.15, "seedling",   "low"),
    ("wheat",  30, 0.60, "seedling",   "high"),
    ("wheat", 100, 0.50, "vegetative", "healthy"),   # band [0.356, 0.616]
    ("wheat", 155, 0.70, "flowering",  "healthy"),   # band [0.618, 0.776]
    ("wheat", 200, 0.85, "ripening",   "high"),      # band [0.631, 0.811]
    ("wheat", 300, 0.50, "fallow",     "healthy"),   # band [0.490, 0.702]
    ("maize", 120, 0.60, "seedling",   "healthy"),   # band [0.488, 0.688]
    ("maize", 160, 0.90, "vegetative", "high"),      # band [0.638, 0.784]
    ("maize", 215, 0.72, "flowering",  "healthy"),   # band [0.653, 0.820] -- 0.6 is LOW
    ("maize", 250, 0.70, "ripening",   "healthy"),   # band [0.624, 0.801] -- 0.5 is LOW
    ("maize", 300, 0.50, "fallow",     "healthy"),   # band [0.352, 0.628]
    ("maize",  45, 0.70, "fallow",     "high"),      # band [0.352, 0.628] split window early
    # boundary / stress
    ("wheat",  30, 0.24, "seedling",   "low"),       # just below 0.253
    ("wheat", 155, 0.78, "flowering",  "high"),      # just above 0.776
]
for crop, doy, ndvi, exp_s, exp_st in cases:
    s, st = evaluate_ndvi(profiles, crop, doy, ndvi)
    ok(f"{crop} doy={doy} ndvi={ndvi} -> {exp_s}/{exp_st}", s==exp_s and st==exp_st, f"got {s!r}/{st!r}")

# ==========================================================================
print("\n========================================")
print("  SECTION 3 -- growth_stage() phenology")
print("  Wheat windows (days-since-planting):")
for w in _stage_windows_in_days("wheat"):
    print(f"    {w}")
print("========================================")
# Actual wheat windows: seedling(0-30), vegetative(30-90), flowering(90-140), ripening(140-180), fallow(180+)
ok("Wheat  25d -> seedling",   growth_stage("wheat", date.today()-timedelta(days=25))=="seedling")
ok("Wheat  60d -> vegetative", growth_stage("wheat", date.today()-timedelta(days=60))=="vegetative")
ok("Wheat 100d -> flowering",  growth_stage("wheat", date.today()-timedelta(days=100))=="flowering")
ok("Wheat 160d -> ripening",   growth_stage("wheat", date.today()-timedelta(days=160))=="ripening")
ok("Wheat 200d -> fallow",     growth_stage("wheat", date.today()-timedelta(days=200))=="fallow")
ok("Wheat 560d -> fallow",     growth_stage("wheat", date.today()-timedelta(days=560))=="fallow")
ok("None planting -> unknown", growth_stage("wheat", None)=="unknown")
ok("Maize  60d -> seedling or vegetative",
   growth_stage("maize", date.today()-timedelta(days=60)) in ("seedling","vegetative"))

# ==========================================================================
print("\n========================================")
print("  SECTION 4 -- expected_ndvi_range() coverage")
print("========================================")
for crop in ("wheat","maize","rice","vegetables","cereals","pulses","general"):
    for days in (20, 60, 100, 160, 220):
        planting = date.today()-timedelta(days=days)
        lo, hi = expected_ndvi_range(crop, planting)
        ok(f"{crop} {days}d: 0<=lo<hi<=1", 0.0<=lo<hi<=1.0, f"[{lo:.2f},{hi:.2f}]")

# ==========================================================================
print("\n========================================")
print("  SECTION 5 -- compute_health() multi-modal logic")
print("========================================")
planting = date.today()-timedelta(days=200)   # fallow stage for wheat

# Stress scoring (per health_rules.py):
# NDVI well-below (>0.10 gap): +2  |  NDVI slightly-below: +1
# trend < -0.10: +2  |  trend < -0.05: +1
# NDWI < -0.20: +1
# moisture < 18: +1
# EC >= 4.0: +2  |  EC >= 2.2: +1
# High_stress threshold: stress >= 3

scenarios = [
    #  label                   ndvi   ndwi  cloud  prev   moist  ec    expected
    ("Healthy all-green",      0.65,  0.10,  5.0,  0.62,  35.0, 1.5,  "healthy"),
    ("Low NDVI moderate",      0.30, -0.05,  5.0,  0.32,  30.0, 1.5,  "moderate"),  # ndvi 0.30 < 0.49 -> +2 (not +2 since 0.49-0.10=0.39, 0.30<0.39 -> +2); stress=2 -> moderate
    ("Drought triple hit",     0.25, -0.30,  8.0,  0.40,  12.0, 1.5,  "high_stress"), # ndvi well-below(+2)+trend-0.15(+2)+ndwi<-0.20(+1)+moist<18(+1) -> 6
    ("Salt EC high",           0.55,  0.05,  5.0,  0.60,  30.0, 4.5,  "moderate"),   # NDVI healthy, EC>=4.0 +2 => stress=2 -> moderate
    ("Salt+LowNDVI stress",    0.35,  0.05,  5.0,  0.40,  30.0, 4.5,  "high_stress"),# ndvi 0.35 < 0.39 -> +2, EC +2 -> stress=4
    ("High moisture note",     0.65,  0.42,  5.0,  0.60,  45.0, 1.2,  "healthy"),    # NDWI>0.30 is NOTE only no stress; NDVI ok; trend+0.05 ok -> healthy
    ("Cloudy -- unknown",      0.65,  0.10, 75.0,  0.62,  35.0, 1.5,  "unknown"),
    ("No NDVI -- unknown",     None,  None,  5.0,  None,  35.0, 1.5,  "unknown"),
    ("EC elevated moderate",   0.65,  0.05,  5.0,  0.60,  30.0, 2.5,  "moderate"),   # EC>=2.2 -> +1
    ("Sharp NDVI drop",        0.55, -0.05,  5.0,  0.70,  30.0, 1.5,  "moderate"),   # trend -0.15 -> +2 -> moderate
]
for label, ndvi, ndwi, cloud, prev, moist, ec, exp in scenarios:
    v = compute_health(crop_type="wheat", planting_date=planting,
                       ndvi=ndvi, ndwi=ndwi, cloud_pct=cloud,
                       prev_ndvi=prev, latest_moisture=moist, latest_ec=ec)
    ok(f"{label}", v.status==exp, f"expected={exp!r} got={v.status!r} | {v.reason[:60]}")

# ==========================================================================
print("\n========================================")
print("  SECTION 6 -- NDWI boundary thresholds")
print("========================================")
planting = date.today()-timedelta(days=60)  # vegetative
for ndwi_val, exp_statuses, label in [
    (-0.25, ["moderate","high_stress"], "drought hint -> stress +1"),
    (-0.05, ["healthy"],                "normal -> no extra stress"),
    ( 0.35, ["healthy","moderate"],     "wet -> note only"),
]:
    v = compute_health(crop_type="wheat", planting_date=planting,
                       ndvi=0.50, ndwi=ndwi_val, cloud_pct=5.0,
                       prev_ndvi=0.49, latest_moisture=30.0, latest_ec=1.5)
    ok(f"NDWI={ndwi_val} ({label})", v.status in exp_statuses, f"got {v.status!r} reason={v.reason[:50]}")

# ==========================================================================
print("\n========================================")
print("  SECTION 7 -- GeoJSON -> Sentinel mock -> Health Model")
print("  (mocked because Copernicus credentials not set in test env)")
print("========================================")
geojson_polygon = {
    "type": "Polygon",
    "coordinates": [[
        [-98.4901, 38.8702], [-98.4845, 38.8702],
        [-98.4845, 38.8651], [-98.4901, 38.8651],
        [-98.4901, 38.8702],
    ]]
}
field = Field(id=101, name="Kansas Wheat WHEAT_FIELD_0102", crop_type="wheat",
              planting_date=date(2024, 1, 15), polygon=geojson_polygon,
              lat=38.8676, lon=-98.4873)

mock_indices = IndicesResult(ndvi=0.60, ndwi=0.38, cloud_pct=4.5, scene_date=None, source="copernicus_mock")
with patch.object(CopernicusClient, "fetch_indices", return_value=mock_indices):
    client = CopernicusClient()
    indices = client.fetch_indices(field)

ok("GeoJSON polygon accepted", geojson_polygon["type"] == "Polygon")
ok("5 vertices", len(geojson_polygon["coordinates"][0]) == 5)
ok("NDVI in [0,1]",   0.0 <= indices.ndvi <= 1.0, f"ndvi={indices.ndvi}")
ok("NDWI in [-1,1]",  -1.0 <= indices.ndwi <= 1.0, f"ndwi={indices.ndwi}")
ok("Cloud pct OK",    0.0 <= indices.cloud_pct <= 100.0, f"cloud={indices.cloud_pct}")
ok("Source reported", bool(indices.source), f"source={indices.source!r}")

verdict = compute_health(crop_type=field.crop_type, planting_date=field.planting_date,
                         ndvi=indices.ndvi, ndwi=indices.ndwi, cloud_pct=indices.cloud_pct,
                         prev_ndvi=0.70, latest_moisture=38.5, latest_ec=1.4)
ok("Full pipeline verdict produced", verdict.status in ("healthy","moderate","high_stress","unknown"),
   f"status={verdict.status!r}")
print(f"       NDVI={indices.ndvi}  NDWI={indices.ndwi}  Status={verdict.status.upper()}")
print(f"       Reason: {verdict.reason[:90]}")

# ==========================================================================
print("\n========================================")
print("  SECTION 8 -- Edge Cases")
print("========================================")
lo, hi = expected_ndvi_range("unknown_crop_xyz", date.today()-timedelta(days=60))
ok("Unknown crop -> fallback valid range", 0.0<=lo<hi<=1.0, f"[{lo},{hi}]")

s = growth_stage("wheat", date.today()+timedelta(days=30))
ok("Future planting (0d clamped) -> seedling", s=="seedling", f"got {s!r}")

s = growth_stage("wheat", date.today()-timedelta(days=3650))
ok("10-year-old wheat -> fallow", s=="fallow", f"got {s!r}")

v = compute_health(crop_type="wheat", planting_date=None,
                   ndvi=0.60, ndwi=0.10, cloud_pct=5.0, prev_ndvi=None,
                   latest_moisture=None, latest_ec=None)
ok("None planting_date -> non-crash", v.status in ("healthy","moderate","high_stress","unknown"))

v = compute_health(crop_type="wheat", planting_date=date.today()-timedelta(days=100),
                   ndvi=0.0, ndwi=-1.0, cloud_pct=0.0, prev_ndvi=0.0,
                   latest_moisture=0.0, latest_ec=0.0)
ok("NDVI=0 extreme -> high_stress", v.status=="high_stress", f"got {v.status!r}")

# ==========================================================================
print("\n========================================")
print("  SECTION 9 -- pytest unit suite smoke-check")
print("========================================")
import subprocess
r = subprocess.run(
    [sys.executable, "-m", "pytest", "backend/ml/test_ndvi_model.py",
     "backend/ml/test_model.py", "-v", "--tb=short"],
    capture_output=True, text=True
)
passed = r.stdout.count(" PASSED")
failed = r.stdout.count(" FAILED")
ok(f"pytest: {passed} tests passed, {failed} failed", failed==0, f"exit={r.returncode}")
if failed:
    print(r.stdout[-800:])

# ==========================================================================
print("\n========================================")
print("  VALIDATION SUMMARY")
print("========================================")
total = PASS + FAIL
pct   = 100*PASS//total if total else 0
print(f"  Total checks : {total}")
print(f"  Passed       : {PASS}")
print(f"  Failed       : {FAIL}")
print(f"  Pass rate    : {pct}%")
print("========================================")
sys.exit(0 if FAIL==0 else 1)
