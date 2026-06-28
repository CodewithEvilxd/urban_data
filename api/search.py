import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_AREAS: list[dict] | None = None
_CITIES: list[dict] | None = None
_PLACES: list[dict] | None = None


def load_delhi_areas() -> list[dict]:
    global _AREAS
    if _AREAS is None:
        with open(ROOT / "data/delhi_areas.json") as f:
            _AREAS = json.load(f)
    return _AREAS


def load_india_cities() -> list[dict]:
    global _CITIES
    if _CITIES is None:
        merged: dict[tuple[float, float], dict] = {}
        path = ROOT / "data/city_registry.json"
        if path.exists():
            with open(path) as f:
                rows = json.load(f)
            for row in rows:
                name = row.get("name") or row.get("slug", "").title()
                lat = float(row["lat"])
                lon = float(row["lon"])
                key = (round(lat, 3), round(lon, 3))
                if key in merged:
                    continue
                merged[key] = {
                    "name": name,
                    "aliases": row.get("aliases", []),
                    "lat": lat,
                    "lon": lon,
                    "state": row.get("state", "India"),
                }
        _CITIES = list(merged.values())
    return _CITIES


def load_india_places() -> list[dict]:
    global _PLACES
    if _PLACES is None:
        merged: dict[tuple[float, float, str], dict] = {}

        def add_place(row: dict, default_state: str | None = None) -> None:
            if "lat" not in row or "lon" not in row:
                return
            name = row.get("name")
            if not name:
                return
            lat = float(row["lat"])
            lon = float(row["lon"])
            state = row.get("state") or default_state or "India"
            key = (round(lat, 4), round(lon, 4), name.lower())
            merged[key] = {
                "name": name,
                "aliases": row.get("aliases", []),
                "lat": lat,
                "lon": lon,
                "state": state,
            }

        for area in load_delhi_areas():
            add_place(area, "Delhi")

        for path_name in ("india_places.json", "india_cities.json", "city_registry.json"):
            path = ROOT / "data" / path_name
            if not path.exists():
                continue
            with open(path) as f:
                for row in json.load(f):
                    add_place(row)

        _PLACES = list(merged.values())
    return _PLACES


def nearest_place_label(lat: float, lon: float, max_distance_m: float = 35_000) -> dict:
    best = None
    best_dist = float("inf")
    for place in load_india_places():
        d = haversine_m(lat, lon, place["lat"], place["lon"])
        if d < best_dist:
            best_dist = d
            best = place

    if not best or best_dist > max_distance_m:
        return {
            "place_name": f"{lat:.5f}, {lon:.5f}",
            "place_state": None,
            "place_distance_m": None,
        }

    return {
        "place_name": best["name"],
        "place_state": best.get("state"),
        "place_distance_m": round(best_dist),
    }


def _match_score(q: str, name: str, aliases: list[str]) -> int:
    name_l = name.lower()
    if name_l == q:
        return 100
    if name_l.startswith(q):
        return 80
    if q in name_l:
        return 60
    for alias in aliases:
        alias_l = alias.lower()
        if alias_l == q or alias_l.startswith(q) or q in alias_l:
            return 50
    return 0


def _place_entry(area: dict, *, state: str | None = None, kind: str = "locality") -> dict:
    return {
        "name": area["name"] if kind == "locality" else f"{area['name']}, {state}, India",
        "lat": area["lat"],
        "lon": area["lon"],
        "city": area["name"] if kind == "city" else None,
        "state": state,
        "kind": kind,
    }


def search_areas(query: str, limit: int = 8) -> list[dict]:
    return search_places_local(query, limit)


def search_places_local(query: str, limit: int = 8) -> list[dict]:
    q = query.strip().lower()
    if len(q) < 2:
        return []

    hits: list[tuple[int, dict]] = []
    for area in load_delhi_areas():
        score = _match_score(q, area["name"], area.get("aliases", []))
        if score:
            hits.append((score, _place_entry(area, state="Delhi", kind="locality")))

    for city in load_india_cities():
        score = _match_score(q, city["name"], city.get("aliases", []))
        if score:
            state = city.get("state", "India")
            hits.append((score, _place_entry(city, state=state, kind="city")))

    hits.sort(key=lambda item: (-item[0], item[1]["name"]))
    seen: set[tuple[float, float]] = set()
    results: list[dict] = []
    for _, place in hits:
        key = (place["lat"], place["lon"])
        if key in seen:
            continue
        seen.add(key)
        results.append({"name": place["name"], "lat": place["lat"], "lon": place["lon"]})
        if len(results) >= limit:
            break
    return results


def reverse_geocode_local(lat: float, lon: float) -> dict:
    best = None
    best_dist = float("inf")
    best_kind = "locality"
    best_state = "Delhi"

    for place in load_india_places():
        d = haversine_m(lat, lon, place["lat"], place["lon"])
        if d < best_dist:
            best_dist = d
            best = place["name"]
            best_state = place.get("state", "India")
            best_kind = "locality" if best_state == "Delhi" else "city"

    max_label_distance_m = 3_000 if best_kind == "locality" else 25_000
    if best and best_dist <= max_label_distance_m:
        location_label = f"Near {best}, {best_state}, India"
        city_name = best if best_kind == "city" else None
        suburb = best if best_kind == "locality" else None
        state = best_state
    else:
        location_label = f"Coordinates: {lat:.5f}, {lon:.5f}"
        city_name = None
        suburb = None
        state = None

    return {
        "display_name": location_label,
        "postcode": None,
        "suburb": suburb,
        "city": city_name,
        "town": None,
        "village": None,
        "county": None,
        "road": None,
        "place_name": suburb or city_name,
        "state": state,
        "country": "India" if state else None,
        "source": "local",
        "distance_m": round(best_dist) if best else None,
    }


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_zone_json(zones: list[dict], lat: float, lon: float) -> dict | None:
    best = None
    best_dist = float("inf")
    for z in zones:
        d = haversine_m(lat, lon, z["latitude"], z["longitude"])
        if d < best_dist:
            best_dist = d
            best = {**z, "distance_m": round(d)}
    return best
