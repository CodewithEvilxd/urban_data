#!/usr/bin/env python3
"""Train India-wide heat classifier on merged zones from all processed cities."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.metrics import brier_score_loss, classification_report
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, RandomizedSearchCV, cross_val_score

CLASS_ORDER = ["low", "moderate", "high", "critical"]
PROCESSED = ROOT / "data/processed"
MODEL_PATH = ROOT / "ml/models/heat_classifier.joblib"


def load_all_zones() -> tuple[pd.DataFrame, list[str]]:
    frames = []
    cities = []
    for path in sorted(PROCESSED.glob("zones_*.json")):
        if path.name == "zones_india.json":
            continue
        with open(path) as f:
            payload = json.load(f)
        city = payload.get("city") or path.stem.replace("zones_", "")
        zones = payload.get("zones", [])
        if not zones:
            continue
        df = pd.DataFrame(zones)
        df["city"] = city
        if "group" not in df.columns:
            df["group"] = df["zone_id"].str.extract(r"^(\w+)_")[0].fillna(city) + "_g"
        frames.append(df)
        cities.append(city)
        print(f"  loaded {len(df):>6} zones from {city}")
    if not frames:
        raise SystemExit("No zones_*.json files found. Run: python scripts/process_india.py")
    return pd.concat(frames, ignore_index=True), cities


def main():
    print("Merging India zone datasets...")
    df, cities = load_all_zones()
    print(f"Total: {len(df)} zones across {len(cities)} cities")

    features = [
        "ndvi",
        "ndbi",
        "builtup_density",
        "impervious_fraction",
        "water_dist_m",
        "latitude",
        "longitude",
    ]
    X = df[features].values
    y = df["heat_class"].values
    groups = df["group"].values

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    train_idx, test_idx = next(splitter.split(X, y, groups=groups))
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    rf_search = RandomizedSearchCV(
        RandomForestClassifier(class_weight="balanced", random_state=42),
        {"n_estimators": [200, 350, 500], "max_depth": [10, 14, 18, None], "min_samples_leaf": [1, 2, 4]},
        n_iter=12,
        cv=3,
        scoring="f1_weighted",
        random_state=42,
        n_jobs=-1,
    )
    rf_search.fit(X_train, y_train)
    rf_best = rf_search.best_estimator_

    hgb = HistGradientBoostingClassifier(
        max_depth=10, learning_rate=0.08, max_iter=300, random_state=42
    )
    hgb.fit(X_train, y_train)

    clf = VotingClassifier(
        estimators=[("rf", rf_best), ("hgb", hgb)],
        voting="soft",
        weights=[1.2, 1.0],
    )
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)
    y_proba = clf.predict_proba(X_test)
    report = classification_report(y_test, y_pred, labels=CLASS_ORDER, output_dict=True)

    cv = GroupKFold(n_splits=5)
    cv_scores = cross_val_score(clf, X, y, cv=cv, groups=groups, scoring="f1_weighted", n_jobs=-1)

    brier_per_class = {}
    for cls in CLASS_ORDER:
        if cls not in clf.classes_:
            continue
        idx = list(clf.classes_).index(cls)
        y_true_bin = (y_test == cls).astype(float)
        brier_per_class[cls] = float(brier_score_loss(y_true_bin, y_proba[:, idx]))

    metrics = {
        "scope": "india_multi_city",
        "cities": cities,
        "n_zones": len(df),
        "test_accuracy": float(report["accuracy"]),
        "cv_f1_macro": float(cv_scores.mean()),
        "cv_f1_std": float(cv_scores.std()),
        "classification_report": report,
        "brier_per_class": brier_per_class,
        "features": features,
    }

    joblib.dump({"model": clf, "features": features, "metrics": metrics}, MODEL_PATH)
    with open(MODEL_PATH.parent / "model_metrics.json", "w") as mf:
        json.dump(metrics, mf, indent=2)

    importances = rf_best.feature_importances_
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(features, importances, color="#e85d04")
    ax.set_xlabel("Importance")
    ax.set_title("India-wide heat classifier feature importance")
    fig.tight_layout()
    fig.savefig(MODEL_PATH.parent / "feature_importance.png", dpi=120)
    plt.close()

    summary = {
        "cities": cities,
        "total_zones": len(df),
        "metrics": {k: v for k, v in metrics.items() if k != "classification_report"},
    }
    with open(PROCESSED / "india_training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"India model saved to {MODEL_PATH}")
    print(f"Test accuracy: {metrics['test_accuracy']:.3f}")
    print(f"CV F1: {metrics['cv_f1_macro']:.3f}")


if __name__ == "__main__":
    main()
