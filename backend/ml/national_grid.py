"""Nationwide India heat grid — IDW interpolation from Landsat-measured zones."""
from __future__ import annotations

import math

INDIA_BOUNDS = (68.0, 6.5, 97.5, 37.5)  # west, south, east, north
DEFAULT_CELL_DEG = 0.42


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def lst_to_heat_class(lst: float) -> str:
    if lst < 33.0:
        return "low"
    if lst < 38.0:
        return "moderate"
    if lst < 43.0:
        return "high"
    return "critical"


def idw_interpolate(
    lat: float,
    lon: float,
    points: list[dict],
    *,
    k: int = 16,
    power: float = 2.0,
) -> dict:
    if not points:
        raise ValueError("no interpolation points")

    ranked = sorted(points, key=lambda p: haversine_m(lat, lon, p["latitude"], p["longitude"]))
    nearest = ranked[0]
    nearest_dist = haversine_m(lat, lon, nearest["latitude"], nearest["longitude"])
    if nearest_dist < 600:
        return {**nearest, "distance_m": round(nearest_dist), "data_source": "measured"}

    pool = ranked[:k]
    weights: list[float] = []
    for p in pool:
        d = haversine_m(lat, lon, p["latitude"], p["longitude"])
        weights.append(1.0 / (d**power + 1.0))

    wsum = sum(weights)
    keys = ("mean_lst", "ndvi", "ndbi", "builtup_density", "impervious_fraction", "water_dist_m")
    out: dict = {"latitude": lat, "longitude": lon}
    for key in keys:
        out[key] = round(sum(p[key] * w / wsum for p, w in zip(pool, weights)), 4)
    out["mean_lst"] = round(out["mean_lst"], 2)
    out["heat_class"] = lst_to_heat_class(out["mean_lst"])
    out["distance_m"] = round(nearest_dist)
    out["data_source"] = "estimated"
    out["nearest_measured_km"] = round(nearest_dist / 1000, 1)
    return out


def cell_polygon(west: float, south: float, east: float, north: float) -> dict:
    return {
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
    }


def point_cell(lat: float, lon: float, cell_deg: float) -> tuple[float, float, float, float]:
    west = math.floor(lon / cell_deg) * cell_deg
    south = math.floor(lat / cell_deg) * cell_deg
    return west, south, west + cell_deg, south + cell_deg


def build_national_grid(points: list[dict], cell_deg: float = DEFAULT_CELL_DEG) -> list[dict]:
    west0, south0, east0, north0 = INDIA_BOUNDS
    features: list[dict] = []
    lat = south0
    idx = 0
    while lat < north0:
        lon = west0
        north = min(lat + cell_deg, north0)
        while lon < east0:
            east = min(lon + cell_deg, east0)
            clat = (lat + north) / 2
            clon = (lon + east) / 2
            est = idw_interpolate(clat, clon, points)
            features.append(
                {
                    "zone_id": f"grid_{idx}",
                    "geometry": cell_polygon(lon, lat, east, north),
                    "latitude": clat,
                    "longitude": clon,
                    "mean_lst": est["mean_lst"],
                    "heat_class": est["heat_class"],
                    "ndvi": est.get("ndvi", 0),
                    "ndbi": est.get("ndbi", 0),
                    "builtup_density": est.get("builtup_density", 0),
                    "impervious_fraction": est.get("impervious_fraction", 0),
                    "water_dist_m": est.get("water_dist_m", 0),
                    "data_source": est.get("data_source", "estimated"),
                    "overview": True,
                    "national": True,
                }
            )
            idx += 1
            lon += cell_deg
        lat += cell_deg
    return features
