import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import transform_geom
from shapely.geometry import box, mapping, shape
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.metrics import brier_score_loss, classification_report
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, RandomizedSearchCV, cross_val_score

CELL_SIZE_M = 500
CLASS_ORDER = ["low", "moderate", "high", "critical"]
PERCENTILES = (25, 60, 85)


def find_scene_id(raw_dir: Path) -> str:
    return max((d for d in raw_dir.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime).name


def parse_mtl_refl(mtl_path: Path) -> dict[str, float]:
    text = mtl_path.read_text()

    def grab(pattern: str, default: float) -> float:
        m = re.search(pattern, text, re.IGNORECASE)
        return float(m.group(1)) if m else default

    return {
        "b4_mult": grab(r"REFLECTANCE_MULT_BAND_4\s*=\s*([\d.E+-]+)", 2.75e-5),
        "b4_add": grab(r"REFLECTANCE_ADD_BAND_4\s*=\s*([-\d.E+-]+)", -0.2),
        "b5_mult": grab(r"REFLECTANCE_MULT_BAND_5\s*=\s*([\d.E+-]+)", 2.75e-5),
        "b5_add": grab(r"REFLECTANCE_ADD_BAND_5\s*=\s*([-\d.E+-]+)", -0.2),
        "b6_mult": grab(r"REFLECTANCE_MULT_BAND_6\s*=\s*([\d.E+-]+)", 2.75e-5),
        "b6_add": grab(r"REFLECTANCE_ADD_BAND_6\s*=\s*([-\d.E+-]+)", -0.2),
    }


def load_band(scene_dir: Path, scene_id: str, suffix: str):
    path = scene_dir / f"{scene_id}_{suffix}.TIF"
    if not path.exists():
        return None, None
    with rasterio.open(path) as src:
        return src.read(1).astype(np.float64), src


def align_to_lst(lst_src, band_data, band_src):
    if band_src.crs == lst_src.crs and band_src.transform == lst_src.transform and band_data.shape == lst_src.read(1).shape:
        return band_data
    from rasterio.warp import reproject, Resampling

    dest = np.zeros((lst_src.height, lst_src.width), dtype=np.float64)
    reproject(
        source=band_data,
        destination=dest,
        src_transform=band_src.transform,
        src_crs=band_src.crs,
        dst_transform=lst_src.transform,
        dst_crs=lst_src.crs,
        resampling=Resampling.bilinear,
    )
    return dest


def build_reflectance(dn: np.ndarray, mult: float, add: float) -> np.ndarray:
    return np.clip(dn * mult + add, 0.0, 1.0)


def ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denom = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        v = (nir - red) / denom
    return np.where(denom > 0, v, np.nan)


def ndbi(swir: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denom = swir + nir
    with np.errstate(divide="ignore", invalid="ignore"):
        v = (swir - nir) / denom
    return np.where(denom > 0, v, np.nan)


def builtup_proxy(ndvi_arr: np.ndarray, red: np.ndarray) -> np.ndarray:
    red_norm = red / (np.nanmax(red) + 1e-9)
    return np.clip((1.0 - ndvi_arr) * 0.6 + red_norm * 0.4, 0.0, 1.0)


def water_distance_proxy(ndvi_arr: np.ndarray, lst_arr: np.ndarray) -> np.ndarray:
    water_like = (ndvi_arr > 0.2) & (ndvi_arr < 0.45) & (lst_arr < np.nanpercentile(lst_arr, 20))
    if not np.any(water_like):
        return np.full(lst_arr.shape, 5000.0, dtype=np.float32)
    ys, xs = np.where(water_like)
    coords = np.column_stack([ys, xs])
    yy, xx = np.mgrid[0 : lst_arr.shape[0], 0 : lst_arr.shape[1]]
    grid = np.column_stack([yy.ravel(), xx.ravel()])
    from scipy.spatial import cKDTree

    tree = cKDTree(coords)
    dist_px, _ = tree.query(grid, k=1)
    return (dist_px.reshape(lst_arr.shape) * 30.0).astype(np.float32)


def classify_lst_percentiles(mean_lst: float, p25: float, p60: float, p85: float) -> str:
    if mean_lst < p25:
        return "low"
    if mean_lst < p60:
        return "moderate"
    if mean_lst < p85:
        return "high"
    return "critical"


def grid_cells(bounds, cell_deg=0.0045, city: str = "delhi"):
    west, south, east, north = bounds
    lon_steps = np.arange(west, east, cell_deg)
    lat_steps = np.arange(south, north, cell_deg)
    for i, lon in enumerate(lon_steps):
        for j, lat in enumerate(lat_steps):
            cell = box(lon, lat, min(lon + cell_deg, east), min(lat + cell_deg, north))
            yield f"{city}_{i}_{j}", i, j, cell


def spatial_group_id(i: int, j: int, city: str = "delhi", block: int = 6) -> str:
    return f"{city}_g_{i // block}_{j // block}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lst", type=Path, default=None)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--bbox", default="76.84,28.40,77.35,28.88")
    parser.add_argument("--city", default="delhi")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--model", type=Path, default=Path("ml/models/heat_classifier.joblib"))
    parser.add_argument("--zones-only", action="store_true", help="Only export zone grid JSON, skip model training")
    args = parser.parse_args()
    if args.output is None:
        args.output = Path(f"data/processed/zones_{args.city}.json")

    scene_id = find_scene_id(args.raw_dir)
    scene_dir = args.raw_dir / scene_id
    lst_path = args.lst or Path(f"data/processed/lst_{scene_id}.tif")
    coeffs = parse_mtl_refl(scene_dir / f"{scene_id}_MTL.txt")

    with rasterio.open(lst_path) as lst_src:
        lst = lst_src.read(1).astype(np.float64)
        lst = np.where(lst == lst_src.nodata, np.nan, lst)
        bounds = lst_src.bounds

    b4_data, b4_src = load_band(scene_dir, scene_id, "B4")
    b5_data, b5_src = load_band(scene_dir, scene_id, "B5")
    b6_data, b6_src = load_band(scene_dir, scene_id, "B6")

    with rasterio.open(lst_path) as lst_src:
        red_dn = align_to_lst(lst_src, b4_data, b4_src)
        nir_dn = align_to_lst(lst_src, b5_data, b5_src)
        red = build_reflectance(red_dn, coeffs["b4_mult"], coeffs["b4_add"])
        nir = build_reflectance(nir_dn, coeffs["b5_mult"], coeffs["b5_add"])
        ndvi_arr = ndvi(red, nir)

        if b6_data is not None:
            swir_dn = align_to_lst(lst_src, b6_data, b6_src)
            swir = build_reflectance(swir_dn, coeffs["b6_mult"], coeffs["b6_add"])
            ndbi_arr = ndbi(swir, nir)
        else:
            ndbi_arr = None

        builtup = builtup_proxy(ndvi_arr, red)
        water_dist = water_distance_proxy(ndvi_arr, lst)

    cell_deg = CELL_SIZE_M / 111_320.0
    rows = []

    with rasterio.open(lst_path) as lst_src:
        for zone_id, i, j, cell_geom in grid_cells(bounds, cell_deg, city=args.city):
            geom_4326 = mapping(cell_geom)
            if lst_src.crs != "EPSG:4326":
                geom_proj = transform_geom("EPSG:4326", lst_src.crs, geom_4326)
            else:
                geom_proj = geom_4326

            mask = geometry_mask([geom_proj], out_shape=(lst_src.height, lst_src.width), transform=lst_src.transform, invert=True)
            cell_lst = lst[mask]
            cell_ndvi = ndvi_arr[mask]
            if np.sum(np.isfinite(cell_lst)) < 5:
                continue
            mean_lst = float(np.nanmean(cell_lst))
            mean_ndvi = float(np.nanmean(cell_ndvi))
            if ndbi_arr is not None:
                mean_ndbi = float(np.nanmean(ndbi_arr[mask]))
            else:
                mean_ndbi = float(np.nanmean(builtup[mask]))
            mean_builtup = float(np.nanmean(builtup[mask]))
            impervious = float(np.clip(mean_builtup * 0.85 + (1 - mean_ndvi) * 0.15, 0, 1))
            centroid = cell_geom.centroid
            mean_water_dist = float(np.nanmean(water_dist[mask]))
            rows.append(
                {
                    "zone_id": zone_id,
                    "group": spatial_group_id(i, j, city=args.city),
                    "geometry": mapping(cell_geom),
                    "mean_lst": mean_lst,
                    "ndvi": mean_ndvi,
                    "ndbi": mean_ndbi,
                    "builtup_density": mean_builtup,
                    "impervious_fraction": impervious,
                    "water_dist_m": mean_water_dist,
                    "latitude": centroid.y,
                    "longitude": centroid.x,
                }
            )

    df = pd.DataFrame(rows)
    p25, p60, p85 = np.percentile(df["mean_lst"], PERCENTILES)
    df["heat_class"] = df["mean_lst"].apply(lambda v: classify_lst_percentiles(v, p25, p60, p85))

    from ml.recommend import rank_interventions, recommendation_summary

    df["recommendation_summary"] = df.apply(
        lambda r: recommendation_summary(
            rank_interventions(
                r["heat_class"], r["ndvi"], r["builtup_density"], r["impervious_fraction"], r["water_dist_m"]
            )
        ),
        axis=1,
    )

    output = {
        "city": args.city,
        "scene_id": scene_id,
        "scene_date": (scene_dir / "manifest.json").exists()
        and json.loads((scene_dir / "manifest.json").read_text()).get("datetime", "")[:10]
        or "",
        "percentiles": {"p25": p25, "p60": p60, "p85": p85},
        "zones": df.to_dict(orient="records"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f)

    print(f"Zones saved to {args.output} ({len(df)} cells)")

    if args.zones_only:
        return

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
        max_depth=10,
        learning_rate=0.08,
        max_iter=300,
        random_state=42,
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
    print(json.dumps(report, indent=2))

    cv = GroupKFold(n_splits=5)
    cv_scores = cross_val_score(clf, X, y, cv=cv, groups=groups, scoring="f1_weighted", n_jobs=-1)
    print(f"5-fold CV F1 weighted: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")

    # Simple multiclass Brier score by averaging one-vs-rest losses
    brier_per_class = {}
    for cls in CLASS_ORDER:
        idx = list(clf.classes_).index(cls)
        y_true_bin = (y_test == cls).astype(float)
        brier_per_class[cls] = float(brier_score_loss(y_true_bin, y_proba[:, idx]))
    brier_macro = float(np.mean(list(brier_per_class.values())))

    # Driver-level local attribution: how much each feature shifts high/critical probability
    proba_all = clf.predict_proba(X)
    target_classes = [c for c in clf.classes_ if c in ("high", "critical")]
    if target_classes:
        target_idx = [list(clf.classes_).index(c) for c in target_classes]
        base_score = proba_all[:, target_idx].sum(axis=1)
        driver_effects = {}
        feature_steps = {
            "ndvi": 0.05,
            "ndbi": 0.05,
            "builtup_density": 0.05,
            "impervious_fraction": 0.05,
            "water_dist_m": 100.0,
            "latitude": 0.01,
            "longitude": 0.01,
        }
        for j, fname in enumerate(features):
            X_perturbed = X.copy()
            step = feature_steps.get(fname, 0.05)
            if fname in {"water_dist_m"}:
                X_perturbed[:, j] = np.clip(X_perturbed[:, j] - step, 0.0, None)
            elif fname in {"ndvi", "ndbi", "builtup_density", "impervious_fraction"}:
                X_perturbed[:, j] = np.clip(X_perturbed[:, j] + step, 0.0, 1.0)
            else:
                X_perturbed[:, j] = X_perturbed[:, j] + step
            proba_perturbed = clf.predict_proba(X_perturbed)
            score_perturbed = proba_perturbed[:, target_idx].sum(axis=1)
            driver_effects[fname] = score_perturbed - base_score

        top_drivers = []
        for i in range(X.shape[0]):
            contribs = []
            for fname in features:
                delta = float(driver_effects[fname][i])
                contribs.append((fname, delta))
            contribs.sort(key=lambda t: abs(t[1]), reverse=True)
            top_drivers.append(
                [
                    {"feature": name, "delta_high_critical_proba": delta}
                    for name, delta in contribs[:3]
                ]
            )
        df["drivers"] = top_drivers
    else:
        df["drivers"] = [[] for _ in range(len(df))]

    args.model.parent.mkdir(parents=True, exist_ok=True)
    metrics = {
        "cv_f1_weighted_mean": float(cv_scores.mean()),
        "cv_f1_weighted_std": float(cv_scores.std()),
        "test_accuracy": float((y_pred == y_test).mean()),
        "rf_best_params": rf_search.best_params_,
        "model_type": "VotingClassifier(RF + HistGradientBoosting)",
        "classification_report": report,
        "brier_per_class": brier_per_class,
        "brier_macro": brier_macro,
        "validation": {
            "holdout": "GroupShuffleSplit(blocked spatial groups)",
            "cv": "GroupKFold(blocked spatial groups)",
            "group_block_cells": 6,
        },
    }
    joblib.dump(
        {
            "model": clf,
            "features": features,
            "percentiles": {"p25": p25, "p60": p60, "p85": p85},
            "metrics": metrics,
        },
        args.model,
    )
    with open(args.model.parent / "model_metrics.json", "w") as mf:
        json.dump(metrics, mf, indent=2)

    importances = rf_best.feature_importances_
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(features, importances, color="#e85d04")
    ax.set_xlabel("Importance")
    ax.set_title("Heat zone classifier feature importance")
    fig.tight_layout()
    plot_path = args.model.parent / "feature_importance.png"
    fig.savefig(plot_path, dpi=120)
    plt.close()

    print(f"Model saved to {args.model}")
    print(f"Feature plot saved to {plot_path}")


if __name__ == "__main__":
    main()
