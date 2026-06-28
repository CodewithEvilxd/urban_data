"""Load all India city zone JSON files — no database required."""
from __future__ import annotations

import json
from pathlib import Path

from ml.recommend import rank_interventions, recommendation_summary

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"


class IndiaJsonStore:
    def __init__(self) -> None:
        self.cities: dict[str, dict] = {}
        self.zone_index: dict[str, dict] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        for path in sorted(PROCESSED.glob("zones_*.json")):
            if path.name == "zones_india.json":
                continue
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            slug = payload.get("city") or path.stem.replace("zones_", "")
            zones = payload.get("zones", [])
            self.cities[slug] = {
                "scene_id": payload.get("scene_id", ""),
                "scene_date": (payload.get("scene_date") or "")[:10],
                "zones": zones,
            }
            for z in zones:
                self.zone_index[z["zone_id"]] = {**z, "_city": slug}
        self._loaded = True

    def city_slugs(self) -> list[str]:
        self.load()
        return list(self.cities.keys())

    def zone_count(self, city: str) -> int:
        self.load()
        return len(self.cities.get(city, {}).get("zones", []))

    def enrich_zone(self, row: dict) -> dict:
        ranked = rank_interventions(
            row["heat_class"],
            row["ndvi"],
            row["builtup_density"],
            row["impervious_fraction"],
            row["water_dist_m"],
        )
        return {
            **row,
            "recommendation_summary": row.get("recommendation_summary")
            or recommendation_summary(ranked),
            "interventions": ranked,
        }

    def zones_for_city(self, city: str) -> list[dict]:
        self.load()
        payload = self.cities.get(city)
        if not payload:
            return []
        return [self.enrich_zone(z) for z in payload["zones"]]

    def zones_in_bbox(
        self,
        west: float,
        south: float,
        east: float,
        north: float,
        city: str | None = None,
        limit: int = 5000,
    ) -> list[dict]:
        self.load()
        out: list[dict] = []
        slugs = [city] if city and city in self.cities else list(self.cities.keys())
        for slug in slugs:
            for z in self.cities[slug]["zones"]:
                if west <= z["longitude"] <= east and south <= z["latitude"] <= north:
                    out.append(self.enrich_zone(z))
                    if len(out) >= limit:
                        return out
        return out

    def zone_by_id(self, zone_id: str) -> dict | None:
        self.load()
        row = self.zone_index.get(zone_id)
        if not row:
            return None
        clean = {k: v for k, v in row.items() if k != "_city"}
        return self.enrich_zone(clean)

    def nearest(self, lat: float, lon: float, city: str | None = None) -> dict | None:
        self.load()
        best = None
        best_d = float("inf")
        slugs = [city] if city and city in self.cities else list(self.cities.keys())
        for slug in slugs:
            for z in self.cities[slug]["zones"]:
                d = (z["latitude"] - lat) ** 2 + (z["longitude"] - lon) ** 2
                if d < best_d:
                    best_d = d
                    best = self.enrich_zone(z)
        return best

    def city_summaries(self, registry: list[dict]) -> list[dict]:
        self.load()
        reg_by_slug = {c["slug"]: c for c in registry}
        out: list[dict] = []
        for slug, payload in self.cities.items():
            zones = payload["zones"]
            if not zones:
                continue
            meta = reg_by_slug.get(slug, {})
            classes = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
            lst_values = []
            for z in zones:
                classes[z["heat_class"]] += 1
                lst_values.append(float(z["mean_lst"]))
            mean_lst = round(sum(lst_values) / len(lst_values), 2)
            heat_class = max(classes, key=classes.get)
            bbox = meta.get("bbox") or [
                min(z["longitude"] for z in zones),
                min(z["latitude"] for z in zones),
                max(z["longitude"] for z in zones),
                max(z["latitude"] for z in zones),
            ]
            out.append(
                {
                    "city": slug,
                    "name": meta.get("name", slug.title()),
                    "state": meta.get("state", ""),
                    "mean_lst": mean_lst,
                    "heat_class": heat_class,
                    "critical_count": classes["critical"],
                    "zone_count": len(zones),
                    "bbox": bbox,
                    "lat": meta.get("lat", (bbox[1] + bbox[3]) / 2),
                    "lon": meta.get("lon", (bbox[0] + bbox[2]) / 2),
                    "scene_date": payload.get("scene_date", ""),
                }
            )
        return out

    def interpolation_points(self, max_per_city: int = 150) -> list[dict]:
        self.load()
        points: list[dict] = []
        for slug, payload in self.cities.items():
            zones = payload["zones"]
            if not zones:
                continue
            step = max(1, len(zones) // max_per_city)
            for z in zones[::step][:max_per_city]:
                points.append(
                    {
                        "latitude": z["latitude"],
                        "longitude": z["longitude"],
                        "mean_lst": float(z["mean_lst"]),
                        "ndvi": float(z["ndvi"]),
                        "ndbi": float(z["ndbi"]),
                        "builtup_density": float(z["builtup_density"]),
                        "impervious_fraction": float(z["impervious_fraction"]),
                        "water_dist_m": float(z["water_dist_m"]),
                        "heat_class": z["heat_class"],
                        "city": slug,
                    }
                )
        return points

    def estimate_at(self, lat: float, lon: float) -> dict:
        from ml.national_grid import cell_polygon, idw_interpolate, point_cell

        west, south, east, north = point_cell(lat, lon, 0.008)
        est = idw_interpolate(lat, lon, self.interpolation_points())
        zone_id = f"est_{lat:.3f}_{lon:.3f}".replace(".", "p").replace("-", "m")
        return {
            "zone_id": zone_id,
            "mean_lst": est["mean_lst"],
            "ndvi": est.get("ndvi", 0),
            "ndbi": est.get("ndbi", 0),
            "builtup_density": est.get("builtup_density", 0),
            "impervious_fraction": est.get("impervious_fraction", 0),
            "water_dist_m": est.get("water_dist_m", 0),
            "latitude": lat,
            "longitude": lon,
            "heat_class": est["heat_class"],
            "geometry": cell_polygon(west, south, east, north),
            "data_source": est.get("data_source", "estimated"),
            "nearest_measured_km": est.get("nearest_measured_km"),
            "distance_m": est.get("distance_m", 0),
            "recommendation_summary": (
                "Landsat-measured zone"
                if est.get("data_source") == "measured"
                else f"AIML estimate · nearest Landsat data {est.get('nearest_measured_km', '?')} km"
            ),
        }

    def stats(self, city: str | None = None, bbox: tuple | None = None) -> dict:
        self.load()
        if bbox:
            rows = self.zones_in_bbox(*bbox, city=city, limit=10_000_000)
            label = city or "viewport"
        elif city and city in self.cities:
            rows = [z for z in self.cities[city]["zones"]]
            label = city
        elif city == "india":
            classes = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
            lst_values = []
            for payload in self.cities.values():
                for z in payload["zones"]:
                    classes[z["heat_class"]] += 1
                    lst_values.append(float(z["mean_lst"]))
            total = len(lst_values)
            if not total:
                raise KeyError("no data")
            return {
                "city": "india",
                "mean_lst": round(sum(lst_values) / total, 2),
                "pct_low": round(classes["low"] / total * 100, 1),
                "pct_moderate": round(classes["moderate"] / total * 100, 1),
                "pct_high": round(classes["high"] / total * 100, 1),
                "pct_critical": round(classes["critical"] / total * 100, 1),
                "critical_count": classes["critical"],
                "scene_id": "multi",
                "scene_date": "2026-06-09",
                "zone_count": total,
                "trend": [{"date": "2026-06-09", "mean_lst": round(sum(lst_values) / total, 2)}],
            }
        else:
            rows = []
            for slug in self.cities:
                rows.extend(self.cities[slug]["zones"])
            label = "india"

        if not rows:
            raise KeyError("no data")

        lst_values = [float(r["mean_lst"]) for r in rows]
        classes = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
        for r in rows:
            classes[r["heat_class"]] += 1
        total = len(rows)
        meta = self.cities.get(city or list(self.cities.keys())[0], {})
        scene_id = meta.get("scene_id", "multi")
        scene_date = meta.get("scene_date", "")

        return {
            "city": label,
            "mean_lst": round(sum(lst_values) / total, 2),
            "pct_low": round(classes["low"] / total * 100, 1),
            "pct_moderate": round(classes["moderate"] / total * 100, 1),
            "pct_high": round(classes["high"] / total * 100, 1),
            "pct_critical": round(classes["critical"] / total * 100, 1),
            "critical_count": classes["critical"],
            "scene_id": scene_id,
            "scene_date": scene_date or "2026-06-09",
            "zone_count": total,
            "trend": [{"date": scene_date or "2026-06-09", "mean_lst": round(sum(lst_values) / total, 2)}],
        }


_STORE: IndiaJsonStore | None = None


def get_store() -> IndiaJsonStore:
    global _STORE
    if _STORE is None:
        _STORE = IndiaJsonStore()
        _STORE.load()
    return _STORE
