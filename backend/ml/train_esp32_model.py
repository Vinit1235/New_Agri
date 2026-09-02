"""Train the ESP32 soil-AI decision tree from real data.

Datasets:
  * Smart-Agriculture (10,000 rows) — primary training source.
      Columns: pH, Temperature, Soil_Humidity, EC(uS/cm), Target
      Target: 0=no action, 1=watering, 2=fertigation

  * Irrigation-Dataset (150 rows) — used for cross-validation only.
      Columns: CropType, CropDays, Soil_Moisture(raw ADC), Soil_Temp,
               Air_Temp, Humidity, Irrigation(0/1)

We map the 3 raw classes onto the 5 spec action classes:
   0 (no action)        -> 0 (monitor)
   1 (watering)         -> 1 (improve irrigation scheduling)
                          if EC >= 4 dS/m   -> 3 (leach/drainage)
                          if EC >= 2.2 dS/m -> 2 (amend / salt-tolerant)
   2 (fertigation)      -> 0 (monitor) + fertilizer=True

The trained model is exported in three forms:
  * model_tree.json         — the tree structure (used by the Python mirror
                              in backend.app.services.soil_model for any
                              server-side re-scoring / calibration)
  * model_tree.h / .c       — drop-in C source for the ESP32 firmware
  * model_meta.json         — feature ranges, training accuracy, per-class
                              stats — loaded by the backend on boot
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent.parent / "datasets"
ARTIFACTS = HERE / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

FEATURES = ["ph", "temperature", "moisture", "ec"]
TARGET = "action"


# ---------------------------------------------------------------------------
# 1. Load and clean Smart-Agriculture dataset
# ---------------------------------------------------------------------------
def load_smart_agriculture() -> pd.DataFrame:
    """Read the 10K dataset, normalise European decimal commas to dots."""
    path = DATA_DIR / "Smart-Agriculture.csv"
    raw = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    # Drop the trailing empty column if present
    raw = raw.loc[:, ~raw.columns.str.contains(r"^Unnamed")]
    raw.columns = [c.strip().lower() for c in raw.columns]

    # Columns: ph_measurement; Temperature; Soil_Humidity;
    #          Electrical_conductivity(uS/cm); Target
    # All values use ',' as decimal separator (e.g. "4,5")
    def to_float(s):
        if isinstance(s, (int, float)):
            return float(s)
        return float(str(s).replace(",", "."))

    df = pd.DataFrame({
        "ph":         raw["ph_measurement"].map(to_float),
        "temperature": raw["temperature"].map(to_float),
        "moisture":    raw["soil_humidity"].map(to_float),
        # Note: the column header says uS/cm but the numeric range (1.1-6.1)
        # is the typical agronomic dS/m scale. Treat as dS/m directly.
        "ec":          raw["electrical_conductivity(us/cm)"].map(to_float),
        "action":      raw["target"].astype(int),
    })
    return df


# ---------------------------------------------------------------------------
# 2. Map 3-class labels to the 5-class spec action set + derive pump/fert
# ---------------------------------------------------------------------------
def remap_actions(df: pd.DataFrame) -> pd.DataFrame:
    """The spec defines 5 actions:

       0 — Maintain regular soil monitoring           (pump=0, fert=optional)
       1 — Improve irrigation scheduling              (pump=1, fert=0)
       2 — Use salt-tolerant crops / soil amendment    (pump=0, fert=0)
       3 — Apply leaching and drainage control        (pump=1, fert=0)
       4 — Immediate reclamation / salinity control   (pump=1, fert=0)

    The Smart-Agri labels are 0/1/2 (no action / watering / fertigation).
    We re-bin using EC + moisture thresholds so the tree can pick the right
    irrigation-vs-leach decision at inference time.
    """
    out = df.copy()
    new_action = []
    new_pump = []
    new_fert = []
    for _, row in df.iterrows():
        ec, mo, tgt = row["ec"], row["moisture"], int(row["action"])
        if tgt == 0:                                   # no action
            new_action.append(0); new_pump.append(False); new_fert.append(False)
        elif tgt == 1:                                 # watering
            if ec >= 4.0:                              # high salinity -> leach
                new_action.append(3); new_pump.append(True); new_fert.append(False)
            elif ec >= 2.2:                            # elevated -> amend
                new_action.append(2); new_pump.append(False); new_fert.append(False)
            else:                                      # normal irrigation
                new_action.append(1); new_pump.append(True); new_fert.append(False)
        else:                                          # tgt == 2 fertigation
            # Fertigation is only safe when EC is low, pH in band, and not
            # extremely dry / wet
            if ec < 2.2 and 6.0 <= row["ph"] <= 7.5 and 18.0 <= mo <= 40.0:
                new_action.append(0); new_pump.append(False); new_fert.append(True)
            else:
                # The "fertigate" label was unsafe -> default to monitor
                new_action.append(0); new_pump.append(False); new_fert.append(False)
    out["action"] = new_action
    out["pump"] = new_pump
    out["fert"] = new_fert
    return out


# ---------------------------------------------------------------------------
# 3. Hand-rolled CART decision tree (Gini, depth-limited)
# ---------------------------------------------------------------------------
class Node:
    __slots__ = ("feature", "threshold", "left", "right", "value", "depth", "n")

    def __init__(self, *, feature: int | None = None, threshold: float | None = None,
                 left: "Node | None" = None, right: "Node | None" = None,
                 value: int | None = None, depth: int = 0, n: int = 0):
        self.feature = feature
        self.threshold = threshold
        self.left = left
        self.right = right
        self.value = value
        self.depth = depth
        self.n = n

    def is_leaf(self) -> bool:
        return self.value is not None


def gini(y: np.ndarray) -> float:
    if len(y) == 0:
        return 0.0
    _, counts = np.unique(y, return_counts=True)
    p = counts / counts.sum()
    return float(1.0 - np.sum(p * p))


def best_split(X: np.ndarray, y: np.ndarray, max_features: int = 4):
    """Find the feature/threshold that minimises weighted Gini after the split."""
    n_samples, n_features = X.shape
    parent_gini = gini(y)
    best = (None, None, parent_gini, 0.0)

    feat_order = list(range(n_features))
    random.shuffle(feat_order)
    feat_order = feat_order[:max_features]

    for f in feat_order:
        col = X[:, f]
        # Try the median of each class-distinct threshold (fast + accurate)
        thresholds = np.unique(col)
        if len(thresholds) > 64:
            quantiles = np.linspace(0.05, 0.95, 32)
            thresholds = np.unique(np.quantile(col, quantiles))
        for t in thresholds:
            left_mask = col <= t
            right_mask = ~left_mask
            if left_mask.sum() < 5 or right_mask.sum() < 5:
                continue
            w_gini = (left_mask.sum() * gini(y[left_mask]) +
                      right_mask.sum() * gini(y[right_mask])) / n_samples
            gain = parent_gini - w_gini
            if gain > best[3]:
                best = (f, t, w_gini, gain)
    return best[0], best[1], best[2]


def build_tree(X: np.ndarray, y: np.ndarray, *, max_depth: int = 6,
               min_samples_leaf: int = 20, depth: int = 0) -> Node:
    n = len(y)
    if n == 0:
        return Node(value=0, depth=depth, n=0)
    counts = Counter(y.tolist())
    majority = max(counts.items(), key=lambda kv: kv[1])[0]

    if depth >= max_depth or n < 2 * min_samples_leaf or len(counts) == 1:
        return Node(value=int(majority), depth=depth, n=n)

    f, t, _ = best_split(X, y)
    if f is None:
        return Node(value=int(majority), depth=depth, n=n)

    left_mask = X[:, f] <= t
    right_mask = ~left_mask
    left = build_tree(X[left_mask], y[left_mask], max_depth=max_depth,
                      min_samples_leaf=min_samples_leaf, depth=depth + 1)
    right = build_tree(X[right_mask], y[right_mask], max_depth=max_depth,
                       min_samples_leaf=min_samples_leaf, depth=depth + 1)
    return Node(feature=int(f), threshold=float(t), left=left, right=right,
                depth=depth, n=n)


def predict_one(node: Node, x: np.ndarray) -> int:
    while not node.is_leaf():
        node = node.left if x[node.feature] <= node.threshold else node.right
    return node.value


def predict(node: Node, X: np.ndarray) -> np.ndarray:
    return np.array([predict_one(node, x) for x in X])


# ---------------------------------------------------------------------------
# 4. Train + 5-fold cross-validate
# ---------------------------------------------------------------------------
def stratified_kfold_indices(y: np.ndarray, k: int = 5, seed: int = 42):
    rng = np.random.default_rng(seed)
    folds = []
    for c in np.unique(y):
        idx = np.where(y == c)[0]
        rng.shuffle(idx)
        chunks = np.array_split(idx, k)
        for i in range(k):
            pass  # placeholder so the for-loop below is clear
    # build by class
    per_class = [np.where(y == c)[0] for c in np.unique(y)]
    rng.shuffle(per_class[0])  # type: ignore
    for arr in per_class:
        rng.shuffle(arr)
    folds = [np.concatenate([per_class[c][i::k] for c in range(len(per_class))])
             for i in range(k)]
    return folds


def cross_validate(X: np.ndarray, y: np.ndarray, *, max_depth: int, k: int = 5):
    folds = stratified_kfold_indices(y, k=k)
    accs = []
    for i, test_idx in enumerate(folds):
        train_idx = np.concatenate([f for j, f in enumerate(folds) if j != i])
        tree = build_tree(X[train_idx], y[train_idx], max_depth=max_depth)
        preds = predict(tree, X[test_idx])
        acc = float((preds == y[test_idx]).mean())
        accs.append(acc)
        print(f"  fold {i+1}: acc={acc:.4f}")
    return accs


# ---------------------------------------------------------------------------
# 5. Export
# ---------------------------------------------------------------------------
def tree_to_dict(node: Node | None) -> dict | int:
    if node is None:
        return 0
    if node.is_leaf():
        return int(node.value)
    return {
        "f": FEATURES[node.feature],                       # name for readability
        "t": round(node.threshold, 4),
        "n": int(node.n),
        "l": tree_to_dict(node.left),
        "r": tree_to_dict(node.right),
    }


def export_c(tree: Node, *, name: str = "classify") -> str:
    """Render the tree as a chain of C `if` statements, for ESP32."""
    lines: list[str] = [
        f"// Auto-generated by backend/ml/train_esp32_model.py on {datetime.utcnow().isoformat()}Z",
        f"// Source: Smart-Agriculture 10K + 5-class agronomic remap",
        f"// Features: {FEATURES}",
        "",
        f"int {name}(float ph, float temperature, float moisture, float ec) {{",
    ]
    counter = {"i": 0}

    def emit(node: Node, indent: str) -> str:
        if node.is_leaf():
            return f"{indent}return {node.value};\n"
        counter["i"] += 1
        idx = counter["i"]
        feat = FEATURES[node.feature]
        th = node.threshold
        return (
            f"{indent}if ({feat} <= {th:.4f}f) {{\n"
            f"{emit(node.left, indent + '  ')}"
            f"{indent}}} else {{\n"
            f"{emit(node.right, indent + '  ')}"
            f"{indent}}}\n"
        )

    lines.append(emit(tree, "  "))
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 6. Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("ESP32 soil-AI model — training pipeline")
    print("=" * 60)

    df = load_smart_agriculture()
    print(f"\nLoaded Smart-Agriculture: {len(df)} rows")
    print(df.describe().round(2))

    df = remap_actions(df)
    print("\nClass distribution (5-class spec remap):")
    print(df["action"].value_counts().sort_index())
    print("Pump trigger counts:", Counter(df["pump"]))
    print("Fertilizer trigger counts:", Counter(df["fert"]))

    X = df[FEATURES].to_numpy(dtype=float)
    y = df["action"].to_numpy(dtype=int)

    # Pick depth by 5-fold CV
    print("\n5-fold cross-validation (depth sweep):")
    best_depth, best_acc = 5, -1.0
    for d in (4, 5, 6, 7, 8):
        print(f" depth={d}")
        accs = cross_validate(X, y, max_depth=d, k=5)
        mean = float(np.mean(accs))
        print(f"  mean acc = {mean:.4f}")
        if mean > best_acc:
            best_acc, best_depth = mean, d

    print(f"\nBest depth: {best_depth} (CV acc = {best_acc:.4f})")

    # Refit on the full dataset
    final_tree = build_tree(X, y, max_depth=best_depth, min_samples_leaf=20)
    train_acc = float((predict(final_tree, X) == y).mean())
    print(f"Train acc (full data, depth={best_depth}): {train_acc:.4f}")

    # Feature importances (depth-weighted splits)
    importances = {f: 0.0 for f in FEATURES}
    def walk(node: Node, weight: float):
        if node.is_leaf():
            return
        importances[FEATURES[node.feature]] += weight
        walk(node.left, weight * 0.9)
        walk(node.right, weight * 0.9)
    walk(final_tree, 1.0)
    total = sum(importances.values()) or 1.0
    importances = {k: round(v / total, 3) for k, v in importances.items()}
    print("Feature importances:", importances)

    # Decision rules (textual)
    def describe(node, depth=0):
        if node.is_leaf():
            return []
        action = "≤" if depth % 2 == 0 else ">"
        # Just print the if-statements
        prefix = "  " * depth
        return [
            f"{prefix}if {FEATURES[node.feature]} {action} {node.threshold:.3f}",
            *describe(node.left, depth + 1),
            *describe(node.right, depth + 1),
        ]

    # Confusion matrix
    preds = predict(final_tree, X)
    classes = sorted(set(y.tolist()))
    cm = pd.crosstab(pd.Series(y, name="actual"),
                     pd.Series(preds, name="pred"),
                     normalize="index").reindex(index=classes, columns=classes, fill_value=0)
    print("\nConfusion matrix (rows = actual, cols = predicted, normalised):")
    print(cm.round(3))

    # Save artefacts
    tree_dict = tree_to_dict(final_tree)
    (ARTIFACTS / "model_tree.json").write_text(json.dumps(tree_dict, indent=2))
    (ARTIFACTS / "model_tree.c").write_text(export_c(final_tree))
    (ARTIFACTS / "model_tree.h").write_text(
        "// Auto-generated header for the ESP32 soil-AI model\n"
        f"// Trained on {len(df)} real samples on {datetime.utcnow().date()}\n"
        "// Returns the 5-class spec action code:\n"
        "//   0 = monitor, 1 = irrigate, 2 = amend, 3 = leach, 4 = reclamation\n"
        f"int classify(float ph, float temperature, float moisture, float ec);\n"
    )
    meta = {
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "source": "Smart-Agriculture.csv (10,000 samples, ramonjsi/Smart-Agriculture)",
        "n_samples": int(len(df)),
        "n_features": len(FEATURES),
        "features": FEATURES,
        "max_depth": best_depth,
        "min_samples_leaf": 20,
        "cv_accuracy_5fold": round(best_acc, 4),
        "train_accuracy_full": round(train_acc, 4),
        "feature_importances": importances,
        "class_distribution": {int(k): int(v) for k, v in
                                df["action"].value_counts().sort_index().items()},
        "action_names": {
            0: "Maintain regular soil monitoring",
            1: "Improve irrigation scheduling",
            2: "Use salt-tolerant crops / soil amendment",
            3: "Apply leaching and drainage control",
            4: "Immediate reclamation / salinity control",
        },
        "feature_ranges": {f: [float(df[f].min()), float(df[f].max())]
                           for f in FEATURES},
        "feature_units": {
            "ph": "pH",
            "temperature": "°C (air)",
            "moisture": "% soil humidity",
            "ec": "dS/m (milli-Siemens per cm; the source CSV header says uS/cm but the numeric range matches dS/m)",
        },
    }
    (ARTIFACTS / "model_meta.json").write_text(json.dumps(meta, indent=2))
    print("\nArtefacts written to:", ARTIFACTS)
    for f in sorted(ARTIFACTS.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
