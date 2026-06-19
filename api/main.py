import json
import os
import sys
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import joblib
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from geoalchemy2.shape import to_shape
from pydantic import BaseModel
import requests
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from api.models import CitySnapshot, HeatZone, SessionLocal
from api.json_store import get_store
from api.search import haversine_m, nearest_zone_json, reverse_geocode_local, search_places_local
from ml.recommend import rank_interventions
from ml.optimize import STRATEGIES, apply_strategy, optimize_city
from ml.risk import heat_risk_index, population_exposure_proxy, priority_score

app = FastAPI(title="UrbanCool API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CLASS_ORDER = ["low", "moderate", "high", "critical"]
_model_bundle = None
_national_features: list[dict] | None = None
INDIA_BOUNDS = (68.0, 6.5, 97.5, 37.5)
MEASURED_NEAR_M = 30_000

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "UrbanCoolHackathon/1.0 (contact: you@example.com)",
)
NOMINATIM_EMAIL = os.getenv("NOMINATIM_EMAIL")
_geo_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_geo_last_call_s = 0.0


def _geo_cache_get(key: str, ttl_s: int = 3600) -> dict | None:
    now = time.time()
    item = _geo_cache.get(key)
    if not item:
        return None
    ts, payload = item
    if now - ts > ttl_s:
        _geo_cache.pop(key, None)
        return None
    _geo_cache.move_to_end(key)
    return payload


def _geo_cache_put(key: str, payload: dict, max_items: int = 800) -> None:
    _geo_cache[key] = (time.time(), payload)
    _geo_cache.move_to_end(key)
    while len(_geo_cache) > max_items:
        _geo_cache.popitem(last=False)


def _nominatim_get(url: str, params: dict) -> dict:
    global _geo_last_call_s
    cache_key = f"{url}?{json.dumps(params, sort_keys=True)}"
    cached = _geo_cache_get(cache_key)
    if cached is not None:
        return cached

    # Public policy: max 1 req/sec + cache
    wait = 1.05 - (time.time() - _geo_last_call_s)
    if wait > 0:
        time.sleep(wait)
    _geo_last_call_s = time.time()

    params = dict(params)
    if NOMINATIM_EMAIL:
        params["email"] = NOMINATIM_EMAIL
    resp = requests.get(url, params=params, timeout=15, headers={"User-Agent": NOMINATIM_USER_AGENT})
    resp.raise_for_status()
    payload = resp.json()
    _geo_cache_put(cache_key, payload)
    return payload


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    west, south, east, north = [float(x) for x in bbox.split(",")]
    if west >= east or south >= north:
        raise ValueError("Invalid bbox order")
    return west, south, east, north


_CITY_REGISTRY: list[dict] | None = None
_CITY_REGISTRY_MTIME: float | None = None


def load_city_registry() -> list[dict]:
    global _CITY_REGISTRY, _CITY_REGISTRY_MTIME
    path = ROOT / "data/city_registry.json"
    mtime = path.stat().st_mtime
    if _CITY_REGISTRY is None or _CITY_REGISTRY_MTIME != mtime:
        with open(path) as f:
            _CITY_REGISTRY = json.load(f)
        _CITY_REGISTRY_MTIME = mtime
    return _CITY_REGISTRY


def in_india_bounds(lat: float, lon: float) -> bool:
    west, south, east, north = INDIA_BOUNDS
    return south <= lat <= north and west <= lon <= east


def parse_est_zone_id(zone_id: str) -> tuple[float, float] | None:
    if not zone_id.startswith("est_"):
        return None
    try:
        parts = zone_id[4:].split("_")
        lat = float(parts[0].replace("p", ".").replace("m", "-"))
        lon = float(parts[1].replace("p", ".").replace("m", "-"))
        return lat, lon
    except (IndexError, ValueError):
        return None


def national_grid_features() -> list[dict]:
    global _national_features
    if _national_features is not None:
        return _national_features
    cache_path = ROOT / "data/processed/india_national_grid.json"
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            _national_features = json.load(f)
        return _national_features
    from ml.national_grid import build_national_grid

    _national_features = build_national_grid(get_store().interpolation_points())
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(_national_features, f)
    return _national_features


def zone_feature_props(row: dict) -> dict:
    return {
        "zone_id": row["zone_id"],
        "mean_lst": row["mean_lst"],
        "ndvi": row.get("ndvi", 0),
        "ndbi": row.get("ndbi", 0),
        "builtup_density": row.get("builtup_density", 0),
        "impervious_fraction": row.get("impervious_fraction", 0),
        "water_dist_m": row.get("water_dist_m", 0),
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "heat_class": row["heat_class"],
        "recommendation_summary": row.get("recommendation_summary", ""),
        "data_source": row.get("data_source", "measured"),
        "overview": row.get("overview", False),
        "national": row.get("national", False),
    }


def zones_json_path(city: str) -> Path:
    path = ROOT / f"data/processed/zones_{city}.json"
    if path.exists():
        return path
    return ROOT / "data/processed/zones_delhi.json"


def compute_stats_dict(
    rows: list[dict],
    city: str,
    scene_id: str,
    scene_date: str,
    zone_count: int | None = None,
) -> dict:
    if not rows:
        raise HTTPException(404, "No heat data for this area")
    lst_values = [float(r["mean_lst"]) for r in rows]
    classes = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
    for r in rows:
        classes[r["heat_class"]] += 1
    total = len(rows)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "city": city,
        "mean_lst": round(sum(lst_values) / total, 2),
        "pct_low": round(classes["low"] / total * 100, 1),
        "pct_moderate": round(classes["moderate"] / total * 100, 1),
        "pct_high": round(classes["high"] / total * 100, 1),
        "pct_critical": round(classes["critical"] / total * 100, 1),
        "critical_count": classes["critical"],
        "scene_id": scene_id,
        "scene_date": scene_date,
        "zone_count": zone_count if zone_count is not None else total,
        "trend": [{"date": scene_date, "mean_lst": round(sum(lst_values) / total, 2)}],
        "live": {
            "status": "live",
            "last_refresh": now,
            "data_source": "Landsat 8/9 Collection 2 (Planetary Computer)",
            "pipeline": "Physics LST → Spatial ML → Scenario Optimizer",
        },
    }


def query_zone_rows_bbox(
    west: float, south: float, east: float, north: float, city: str | None = None
) -> list[dict]:
    if use_db():
        session = SessionLocal()
        q = session.query(HeatZone).filter(
            HeatZone.geom.ST_Intersects(text("ST_MakeEnvelope(:west, :south, :east, :north, 4326)"))
        ).params(west=west, south=south, east=east, north=north)
        if city:
            q = q.filter(HeatZone.city == city)
        rows = [zone_row_dict(z) for z in q.all()]
        session.close()
        return rows

    return get_store().zones_in_bbox(west, south, east, north, city=city, limit=500_000)


def get_model():
    global _model_bundle
    if _model_bundle is None:
        path = ROOT / "ml/models/heat_classifier.joblib"
        _model_bundle = joblib.load(path)
    return _model_bundle


def load_zones_fallback(city: str = "delhi"):
    global _zones_cache
    path = zones_json_path(city)
    cache_key = str(path)
    if _zones_cache is None:
        _zones_cache = {}
    if cache_key not in _zones_cache:
        with open(path) as f:
            _zones_cache[cache_key] = json.load(f)
    return _zones_cache[cache_key]


def zone_row_dict(z) -> dict:
    return {
        "zone_id": z.zone_id,
        "mean_lst": z.mean_lst,
        "ndvi": z.ndvi,
        "ndbi": z.ndbi,
        "builtup_density": z.builtup_density,
        "impervious_fraction": z.impervious_fraction,
        "water_dist_m": z.water_dist_m,
        "latitude": z.latitude,
        "longitude": z.longitude,
        "heat_class": z.heat_class,
    }


def feature_vector(zone_data: dict, ndvi_increase: float) -> dict:
    return {
        "ndvi": zone_data["ndvi"] + ndvi_increase,
        "ndbi": max(zone_data["ndbi"] - ndvi_increase * 0.15, -1.0),
        "builtup_density": max(zone_data["builtup_density"] - ndvi_increase * 0.2, 0.0),
        "impervious_fraction": max(zone_data["impervious_fraction"] - ndvi_increase * 0.15, 0.0),
        "water_dist_m": zone_data["water_dist_m"],
        "latitude": zone_data["latitude"],
        "longitude": zone_data["longitude"],
    }


def driver_attribution(model, features: list[str], zone_data: dict) -> list[dict]:
    proba = model.predict_proba([[zone_data[f] for f in features]])[0]
    classes = list(model.classes_)
    target_idx = [classes.index(c) for c in classes if c in ("high", "critical")]
    base = float(sum(proba[i] for i in target_idx)) if target_idx else float(max(proba))

    steps = {
        "ndvi": 0.05,
        "ndbi": 0.05,
        "builtup_density": 0.05,
        "impervious_fraction": 0.05,
        "water_dist_m": 100.0,
        "latitude": 0.01,
        "longitude": 0.01,
    }
    deltas = []
    for f in features:
        step = steps.get(f, 0.05)
        pert = dict(zone_data)
        if f == "water_dist_m":
            pert[f] = max(pert[f] - step, 0.0)
        elif f in {"ndvi", "builtup_density", "impervious_fraction"}:
            pert[f] = float(min(max(pert[f] + step, 0.0), 1.0))
        elif f == "ndbi":
            pert[f] = float(min(max(pert[f] + step, -1.0), 1.0))
        else:
            pert[f] = pert[f] + step

        p2 = model.predict_proba([[pert[k] for k in features]])[0]
        score2 = float(sum(p2[i] for i in target_idx)) if target_idx else float(max(p2))
        deltas.append({"feature": f, "delta_high_critical_proba": score2 - base})

    deltas.sort(key=lambda d: abs(d["delta_high_critical_proba"]), reverse=True)
    return deltas[:3]


def zone_to_feature(zone) -> dict:
    d = dict(zone_row_dict(zone)) if hasattr(zone, "zone_id") else dict(zone)
    if hasattr(zone, "recommendation_summary"):
        d["recommendation_summary"] = zone.recommendation_summary
    return d


def geometry_geojson(geom):
    return json.loads(json.dumps(to_shape(geom).__geo_interface__))


def db_available() -> bool:
    try:
        session = SessionLocal()
        session.execute(text("SELECT 1"))
        session.close()
        return True
    except Exception:
        return False


def use_db() -> bool:
    mode = os.getenv("DATA_BACKEND", "auto").lower()
    if mode == "json":
        return False
    if mode == "db":
        return db_available()
    return db_available()


def zones_from_json(city: str) -> list[dict]:
    return get_store().zones_for_city(city)


@app.get("/api/cities")
def list_cities():
    registry = load_city_registry()
    counts: dict[str, int] = {}
    if use_db():
        session = SessionLocal()
        for c in registry:
            counts[c["slug"]] = (
                session.query(HeatZone).filter(HeatZone.city == c["slug"]).count()
            )
        session.close()
    else:
        for c in registry:
            counts[c["slug"]] = get_store().zone_count(c["slug"])

    return {
        "cities": [
            {
                "slug": c["slug"],
                "name": c["name"],
                "state": c["state"],
                "lat": c["lat"],
                "lon": c["lon"],
                "bbox": c["bbox"],
                "has_data": counts.get(c["slug"], 0) > 0,
                "zone_count": counts.get(c["slug"], 0),
            }
            for c in registry
        ]
    }


@app.get("/api/zones")
def list_zones(city: str | None = None, bbox: str | None = None, limit: int = 5000):
    if use_db():
        session = SessionLocal()
        if bbox:
            west, south, east, north = parse_bbox(bbox)
            rows = (
                session.query(HeatZone)
                .filter(
                    HeatZone.geom.ST_Intersects(
                        text("ST_MakeEnvelope(:west, :south, :east, :north, 4326)")
                    )
                )
                .params(west=west, south=south, east=east, north=north)
                .limit(limit)
                .all()
            )
        elif city:
            rows = session.query(HeatZone).filter(HeatZone.city == city).limit(limit).all()
        else:
            rows = session.query(HeatZone).limit(limit).all()
        features = []
        for z in rows:
            props = zone_to_feature(z)
            props["recommendation_summary"] = z.recommendation_summary
            features.append(
                {
                    "type": "Feature",
                    "id": z.zone_id,
                    "geometry": geometry_geojson(z.geom),
                    "properties": props,
                }
            )
        session.close()
    else:
        if bbox:
            west, south, east, north = parse_bbox(bbox)
            rows = get_store().zones_in_bbox(west, south, east, north, city=city, limit=limit)
        else:
            rows = get_store().zones_for_city(city)[:limit] if city else []
        features = [
            {
                "type": "Feature",
                "id": r["zone_id"],
                "geometry": r["geometry"],
                "properties": {
                    "zone_id": r["zone_id"],
                    "mean_lst": r["mean_lst"],
                    "ndvi": r["ndvi"],
                    "ndbi": r["ndbi"],
                    "builtup_density": r["builtup_density"],
                    "impervious_fraction": r["impervious_fraction"],
                    "water_dist_m": r["water_dist_m"],
                    "latitude": r["latitude"],
                    "longitude": r["longitude"],
                    "heat_class": r["heat_class"],
                    "recommendation_summary": r.get("recommendation_summary", ""),
                },
            }
            for r in rows
        ]
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/zones/india-national")
def india_national():
    features = [
        {
            "type": "Feature",
            "id": row["zone_id"],
            "geometry": row["geometry"],
            "properties": zone_feature_props(row),
        }
        for row in national_grid_features()
    ]
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/zones/estimate")
def zone_estimate(lat: float, lon: float):
    if not in_india_bounds(lat, lon):
        raise HTTPException(404, "Location outside India. Pan map supports all of India only.")
    row = get_store().estimate_at(lat, lon)
    hit = get_store().nearest(lat, lon, city=None)
    if hit:
        dist = haversine_m(lat, lon, hit["latitude"], hit["longitude"])
        if dist <= MEASURED_NEAR_M:
            detail = enrich_zone_risk(hit)
            bundle = get_model()
            model = bundle["model"]
            features = bundle["features"]
            zone_vec = {k: detail[k] for k in features}
            detail["geometry"] = hit["geometry"]
            detail["drivers"] = driver_attribution(model, features, zone_vec)
            detail["distance_m"] = round(dist, 1)
            detail["data_source"] = "measured"
            return detail
    detail = enrich_zone_risk(row)
    bundle = get_model()
    model = bundle["model"]
    features = bundle["features"]
    zone_vec = {k: detail[k] for k in features}
    detail["drivers"] = driver_attribution(model, features, zone_vec)
    detail["interventions"] = rank_interventions(
        detail["heat_class"],
        detail["ndvi"],
        detail["builtup_density"],
        detail["impervious_fraction"],
        detail["water_dist_m"],
    )
    return detail


@app.get("/api/zones/india-overview")
def india_overview():
    registry = load_city_registry()
    summaries = get_store().city_summaries(registry)
    features = []
    for s in summaries:
        west, south, east, north = s["bbox"]
        features.append(
            {
                "type": "Feature",
                "id": s["city"],
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [west, south],
                            [east, south],
                            [east, north],
                            [west, north],
                            [west, south],
                        ]
                    ],
                },
                "properties": {
                    "zone_id": f"city_{s['city']}",
                    "city": s["city"],
                    "name": s["name"],
                    "state": s["state"],
                    "mean_lst": s["mean_lst"],
                    "heat_class": s["heat_class"],
                    "critical_count": s["critical_count"],
                    "zone_count": s["zone_count"],
                    "ndvi": 0,
                    "ndbi": 0,
                    "builtup_density": 0,
                    "impervious_fraction": 0,
                    "water_dist_m": 0,
                    "latitude": s["lat"],
                    "longitude": s["lon"],
                    "overview": True,
                    "recommendation_summary": f"{s['zone_count']:,} zones · {s['critical_count']:,} critical",
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/search/areas")
def search_places(q: str, country: str = "in", limit: int = 8):
    q = q.strip()
    if len(q) < 2:
        return {"results": [], "source": "local"}

    try:
        data = _nominatim_get(
            f"{NOMINATIM_BASE}/search",
            {
                "q": q,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": limit,
                "countrycodes": country,
            },
        )
        if isinstance(data, list) and data:
            results = []
            for item in data:
                name = item.get("display_name", "")
                lat = float(item["lat"])
                lon = float(item["lon"])
                results.append({"name": name, "lat": lat, "lon": lon})
            return {"results": results, "source": "nominatim"}
    except requests.RequestException:
        pass

    return {"results": search_places_local(q, limit), "source": "local"}


@app.get("/api/geocode/reverse")
def reverse_geocode(lat: float, lon: float):
    try:
        data = _nominatim_get(
            f"{NOMINATIM_BASE}/reverse",
            {"lat": lat, "lon": lon, "format": "jsonv2", "addressdetails": 1},
        )
        if isinstance(data, dict) and data.get("display_name"):
            addr = data.get("address", {}) or {}
            return {
                "display_name": data.get("display_name"),
                "postcode": addr.get("postcode"),
                "suburb": addr.get("suburb") or addr.get("neighbourhood"),
                "city": addr.get("city") or addr.get("town") or addr.get("village"),
                "state": addr.get("state"),
                "country": addr.get("country"),
                "source": "nominatim",
            }
    except requests.RequestException:
        pass

    return reverse_geocode_local(lat, lon)


@app.get("/api/zones/near")
def zone_near(lat: float, lon: float, city: str | None = None):
    if use_db():
        session = SessionLocal()
        row = session.execute(
            text(
                """
                SELECT zone_id, mean_lst, ndvi, ndbi, builtup_density, impervious_fraction,
                       water_dist_m, latitude, longitude, heat_class, recommendation_summary,
                       ST_AsGeoJSON(geom) AS geom_json,
                       ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS dist_m
                FROM heat_zones
                WHERE (:city IS NULL OR city = :city)
                ORDER BY geom::geography <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                LIMIT 1
                """
            ),
            {"lat": lat, "lon": lon, "city": city},
        ).mappings().first()
        session.close()
        if not row:
            raise HTTPException(404, "No zone near this point")
        geom = json.loads(row["geom_json"])
        return {
            "zone_id": row["zone_id"],
            "mean_lst": row["mean_lst"],
            "ndvi": row["ndvi"],
            "ndbi": row["ndbi"],
            "builtup_density": row["builtup_density"],
            "impervious_fraction": row["impervious_fraction"],
            "water_dist_m": row["water_dist_m"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "heat_class": row["heat_class"],
            "recommendation_summary": row["recommendation_summary"],
            "geometry": geom,
            "distance_m": round(float(row["dist_m"]), 1),
        }

    hit = get_store().nearest(lat, lon, city=city)
    if hit:
        dist = haversine_m(lat, lon, hit["latitude"], hit["longitude"])
        if dist <= MEASURED_NEAR_M:
            return {
                "zone_id": hit["zone_id"],
                "mean_lst": hit["mean_lst"],
                "ndvi": hit["ndvi"],
                "ndbi": hit["ndbi"],
                "builtup_density": hit["builtup_density"],
                "impervious_fraction": hit["impervious_fraction"],
                "water_dist_m": hit["water_dist_m"],
                "latitude": hit["latitude"],
                "longitude": hit["longitude"],
                "heat_class": hit["heat_class"],
                "recommendation_summary": hit.get("recommendation_summary", ""),
                "geometry": hit["geometry"],
                "distance_m": round(dist, 1),
                "data_source": "measured",
            }

    if not in_india_bounds(lat, lon):
        raise HTTPException(404, "No zone near this point")
    est = get_store().estimate_at(lat, lon)
    return {
        **est,
        "recommendation_summary": est.get("recommendation_summary", ""),
    }


def enrich_zone_risk(row: dict) -> dict:
    risk = heat_risk_index(
        float(row["mean_lst"]),
        row["heat_class"],
        float(row["builtup_density"]),
        float(row["impervious_fraction"]),
    )
    pop = population_exposure_proxy(
        float(row["builtup_density"]),
        float(row["impervious_fraction"]),
        float(row["mean_lst"]),
    )
    return {
        **row,
        "heat_risk_index": risk,
        "population_exposure": pop,
        "priority_score": priority_score(risk, pop),
    }


@app.get("/api/zones/priorities")
def zone_priorities(city: str | None = None, bbox: str | None = None, limit: int = 25):
    if bbox:
        west, south, east, north = parse_bbox(bbox)
        zone_rows = [
            enrich_zone_risk(r)
            for r in query_zone_rows_bbox(west, south, east, north, city)
            if r["heat_class"] in ("high", "critical")
        ]
        label = city or "viewport"
    elif use_db():
        session = SessionLocal()
        q = session.query(HeatZone).filter(HeatZone.heat_class.in_(["high", "critical"]))
        if city:
            q = q.filter(HeatZone.city == city)
        rows = q.all()
        session.close()
        zone_rows = [enrich_zone_risk(zone_row_dict(z)) for z in rows]
        label = city or "india"
    else:
        store = get_store()
        if city:
            candidates = store.zones_for_city(city)
            label = city
        else:
            candidates = []
            for slug in store.city_slugs():
                candidates.extend(store.zones_for_city(slug))
            label = "india"
        zone_rows = [
            enrich_zone_risk(r)
            for r in candidates
            if r["heat_class"] in ("high", "critical")
        ]

    zone_rows.sort(key=lambda z: z["priority_score"], reverse=True)
    top = zone_rows[:limit]
    return {
        "city": label,
        "count": len(top),
        "zones": [
            {
                "zone_id": z["zone_id"],
                "mean_lst": z["mean_lst"],
                "heat_class": z["heat_class"],
                "latitude": z["latitude"],
                "longitude": z["longitude"],
                "heat_risk_index": z["heat_risk_index"],
                "population_exposure": z["population_exposure"],
                "priority_score": z["priority_score"],
                "recommendation_summary": z.get("recommendation_summary", ""),
            }
            for z in top
        ],
    }


@app.get("/api/strategies")
def list_strategies():
    area_km2 = 0.25  # 500m grid cell
    return {
        "strategies": [
            {
                "key": s.key,
                "label": s.label,
                "cost_per_km2_crore": s.cost_per_km2_crore,
                "cost_per_cell_crore": round(s.cost_per_km2_crore * area_km2, 4),
                "lst_reduction_c": {"min": s.lst_reduction_c[0], "max": s.lst_reduction_c[1]},
                "ndvi_delta": s.ndvi_delta,
                "impervious_delta": s.impervious_delta,
            }
            for s in STRATEGIES
        ]
    }


@app.get("/api/live")
def live_status(city: str | None = None, bbox: str | None = None):
    try:
        if bbox:
            stats = city_stats(city=city or "viewport", bbox=bbox)
        else:
            stats = city_stats(city=city or "delhi")
    except HTTPException:
        return {
            "status": "no_data",
            "city": city or "india",
            "message": "No Landsat heat data for this area yet. Select a city with live data or run: python scripts/process_city.py <city>",
            "last_refresh": datetime.now(timezone.utc).isoformat(),
            "zone_count": 0,
            "data_source": "Landsat 8/9 Collection 2 (Planetary Computer)",
        }

    live = stats.get("live", {})
    return {
        "status": "live",
        "city": stats["city"],
        "scene_id": stats.get("scene_id", ""),
        "scene_date": stats.get("scene_date", ""),
        "mean_lst": stats.get("mean_lst", 0),
        "critical_count": stats.get("critical_count", 0),
        "zone_count": stats.get("zone_count", 0),
        "data_source": live.get("data_source", "Landsat 8/9 Collection 2"),
        "pipeline": live.get("pipeline", ""),
        "last_refresh": live.get("last_refresh", datetime.now(timezone.utc).isoformat()),
    }


@app.get("/api/zones/{zone_id}")
def zone_detail(zone_id: str):
    if use_db():
        session = SessionLocal()
        z = session.query(HeatZone).filter(HeatZone.zone_id == zone_id).first()
        if not z:
            session.close()
            raise HTTPException(404, "Zone not found")
        detail = zone_to_feature(z)
        detail["geometry"] = geometry_geojson(z.geom)
        detail["interventions"] = json.loads(z.interventions_json)
        detail.update(
            enrich_zone_risk(detail)
        )
        bundle = get_model()
        model = bundle["model"]
        features = bundle["features"]
        zone_vec = {k: detail[k] for k in features}
        detail["drivers"] = driver_attribution(model, features, zone_vec)
        session.close()
        return detail

    coords = parse_est_zone_id(zone_id)
    if coords:
        return zone_estimate(lat=coords[0], lon=coords[1])

    row = get_store().zone_by_id(zone_id)
    if not row:
        raise HTTPException(404, "Zone not found")
    bundle = get_model()
    model = bundle["model"]
    features = bundle["features"]
    zone_vec = {k: row[k] for k in features}
    detail = enrich_zone_risk(
        {
            **row,
            "drivers": row.get("drivers") or driver_attribution(model, features, zone_vec),
        }
    )
    return detail


class SimulateRequest(BaseModel):
    zone_id: str
    ndvi_increase: float


@app.post("/api/simulate")
def simulate(body: SimulateRequest):
    bundle = get_model()
    model = bundle["model"]
    features = bundle["features"]

    if use_db():
        session = SessionLocal()
        z = session.query(HeatZone).filter(HeatZone.zone_id == body.zone_id).first()
        session.close()
        if not z:
            raise HTTPException(404, "Zone not found")
        zone_data = zone_row_dict(z)
        current_class = z.heat_class
        mean_lst = z.mean_lst
        ndvi = z.ndvi + body.ndvi_increase
    else:
        row = get_store().zone_by_id(body.zone_id)
        if not row:
            coords = parse_est_zone_id(body.zone_id)
            if coords:
                row = get_store().estimate_at(coords[0], coords[1])
            else:
                raise HTTPException(404, "Zone not found")
        zone_data = {
            k: row[k]
            for k in (
                "zone_id",
                "mean_lst",
                "ndvi",
                "ndbi",
                "builtup_density",
                "impervious_fraction",
                "water_dist_m",
                "latitude",
                "longitude",
                "heat_class",
            )
        }
        current_class = row["heat_class"]
        mean_lst = row["mean_lst"]
        ndvi = row["ndvi"] + body.ndvi_increase

    sample = feature_vector(zone_data, body.ndvi_increase)
    X = [[sample[f] for f in features]]
    predicted = model.predict(X)[0]
    proba = model.predict_proba(X)[0]
    class_idx = list(model.classes_).index(predicted)

    lst_reduction = body.ndvi_increase * 8.0
    estimated_lst = mean_lst - lst_reduction

    return {
        "zone_id": body.zone_id,
        "current_class": current_class,
        "predicted_class": predicted,
        "class_changed": predicted != current_class,
        "ndvi_after": ndvi,
        "estimated_lst_c": round(estimated_lst, 2),
        "estimated_lst_reduction_c": round(lst_reduction, 2),
        "confidence": round(float(proba[class_idx]), 3),
    }


class OptimizeRequest(BaseModel):
    city: str = "delhi"
    budget_crore: float = 25.0
    objective: str = "max_cooling"
    max_zones: int = 200
    bbox: str | None = None


@app.post("/api/scenarios/optimize")
def optimize_scenario(body: OptimizeRequest):
    if body.bbox:
        west, south, east, north = parse_bbox(body.bbox)
        zone_rows = query_zone_rows_bbox(west, south, east, north, body.city or None)
    elif use_db():
        session = SessionLocal()
        zones = session.query(HeatZone).filter(HeatZone.city == body.city).all()
        session.close()
        zone_rows = [zone_row_dict(z) | {
            "impervious_fraction": z.impervious_fraction,
            "water_dist_m": z.water_dist_m,
            "ndbi": z.ndbi,
            "ndvi": z.ndvi,
            "builtup_density": z.builtup_density,
        } for z in zones]
    else:
        zone_rows = zones_from_json(body.city)

    portfolio = optimize_city(
        zones=zone_rows,
        budget_crore=body.budget_crore,
        objective=body.objective,
        max_zones=body.max_zones,
    )

    bundle = get_model()
    model = bundle["model"]
    features = bundle["features"]

    zone_index = {z["zone_id"]: z for z in zone_rows}
    enriched = []
    for item in portfolio["portfolio"]:
        z = zone_index.get(item["zone_id"])
        if not z:
            continue
        strat = next((s for s in STRATEGIES if s.key == item["strategy"]), None)
        if not strat:
            continue
        after = apply_strategy(z, strat)
        X = [[after[f] for f in features]]
        predicted = model.predict(X)[0]
        proba = model.predict_proba(X)[0]
        conf = float(max(proba))
        enriched.append(
            item
            | {
                "current_class": z["heat_class"],
                "predicted_class_after": predicted,
                "confidence": round(conf, 3),
            }
        )

    portfolio["portfolio"] = enriched
    return portfolio


@app.get("/api/stats")
def city_stats(city: str = "delhi", bbox: str | None = None):
    if bbox:
        west, south, east, north = parse_bbox(bbox)
        rows = query_zone_rows_bbox(west, south, east, north, city if city != "viewport" else None)
        scene_id = "multi"
        scene_date = datetime.now(timezone.utc).date().isoformat()
        if use_db() and rows:
            session = SessionLocal()
            first = (
                session.query(HeatZone)
                .filter(HeatZone.zone_id == rows[0]["zone_id"])
                .first()
            )
            session.close()
            if first:
                scene_id = first.scene_id
                scene_date = first.scene_date.date().isoformat()
        elif rows:
            try:
                meta = get_store().stats(
                    city=city if city not in ("viewport", "india") else None,
                    bbox=(west, south, east, north),
                )
                scene_id = meta.get("scene_id", scene_id)
                scene_date = meta.get("scene_date", scene_date)
            except KeyError:
                pass
        return compute_stats_dict(rows, city, scene_id, scene_date)

    if use_db():
        session = SessionLocal()
        snap = (
            session.query(CitySnapshot)
            .filter(CitySnapshot.city == city)
            .order_by(CitySnapshot.scene_date.desc())
            .all()
        )
        zone_count = session.query(HeatZone).filter(HeatZone.city == city).count()
        session.close()
        if not snap:
            raise HTTPException(404, f"No stats for city '{city}'")
        trend = [
            {"date": s.scene_date.date().isoformat(), "mean_lst": round(s.mean_lst, 2)}
            for s in reversed(snap)
        ]
        latest = snap[0]
        base = {
            "city": city,
            "mean_lst": round(latest.mean_lst, 2),
            "pct_low": round(latest.pct_low, 1),
            "pct_moderate": round(latest.pct_moderate, 1),
            "pct_high": round(latest.pct_high, 1),
            "pct_critical": round(latest.pct_critical, 1),
            "critical_count": latest.critical_count,
            "scene_id": latest.scene_id,
            "scene_date": latest.scene_date.date().isoformat(),
            "zone_count": zone_count,
            "trend": trend,
        }
        now = datetime.now(timezone.utc).isoformat()
        base["live"] = {
            "status": "live",
            "last_refresh": now,
            "data_source": "Landsat 8/9 Collection 2 (Planetary Computer)",
            "pipeline": "Physics LST → Spatial ML → Scenario Optimizer",
        }
        return base

    try:
        stats = get_store().stats(city=city)
    except KeyError:
        raise HTTPException(404, f"No stats for city '{city}'")
    now = datetime.now(timezone.utc).isoformat()
    stats["live"] = {
        "status": "live",
        "last_refresh": now,
        "data_source": "Landsat 8/9 Collection 2 (Planetary Computer)",
        "pipeline": "Physics LST → Spatial ML → Scenario Optimizer",
    }
    return stats


@app.get("/api/model/metrics")
def model_metrics():
    metrics_path = ROOT / "ml/models/model_metrics.json"
    if metrics_path.exists():
        with open(metrics_path) as f:
            return json.load(f)
    bundle = get_model()
    return bundle.get("metrics", {"note": "Retrain with ml/train_classifier.py for full metrics"})


@app.get("/api/zones/{zone_id}/drivers")
def zone_drivers(zone_id: str):
    bundle = get_model()
    model = bundle["model"]
    features = bundle["features"]

    if use_db():
        session = SessionLocal()
        z = session.query(HeatZone).filter(HeatZone.zone_id == zone_id).first()
        session.close()
        if not z:
            raise HTTPException(404, "Zone not found")
        zone_data = zone_row_dict(z)
        zone_vec = {k: zone_data[k] for k in features}
        return {"zone_id": zone_id, "drivers": driver_attribution(model, features, zone_vec)}

    row = get_store().zone_by_id(zone_id)
    if not row:
        coords = parse_est_zone_id(zone_id)
        if coords:
            row = get_store().estimate_at(coords[0], coords[1])
        else:
            raise HTTPException(404, "Zone not found")
    zone_vec = {k: row[k] for k in features}
    return {"zone_id": zone_id, "drivers": row.get("drivers") or driver_attribution(model, features, zone_vec)}


@app.get("/health")
def health():
    return {"status": "ok"}
