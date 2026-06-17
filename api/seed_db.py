import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from api.models import Base, CitySnapshot, HeatZone, SessionLocal, engine
from ml.recommend import rank_interventions, recommendation_summary


def load_zones_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def seed(city: str = "delhi", zones_path: Path | None = None):
    zones_path = zones_path or ROOT / f"data/processed/zones_{city}.json"
    if not zones_path.exists():
        zones_path = ROOT / "data/processed/zones_delhi.json"
    payload = load_zones_json(zones_path)
    scene_id = payload["scene_id"]
    scene_date_str = payload.get("scene_date") or "2026-06-09"
    scene_date = datetime.fromisoformat(str(scene_date_str)[:10])

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)

    session = SessionLocal()
    session.query(HeatZone).filter(HeatZone.city == city).delete()
    session.query(CitySnapshot).filter(CitySnapshot.city == city).delete()

    classes = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
    lst_values = []

    for row in payload["zones"]:
        ranked = rank_interventions(
            row["heat_class"],
            row["ndvi"],
            row["builtup_density"],
            row["impervious_fraction"],
            row["water_dist_m"],
        )
        summary = recommendation_summary(ranked)
        poly = shape(row["geometry"])
        zone = HeatZone(
            zone_id=row["zone_id"],
            city=city,
            scene_id=scene_id,
            geom=from_shape(poly, srid=4326),
            mean_lst=row["mean_lst"],
            ndvi=row["ndvi"],
            ndbi=row["ndbi"],
            builtup_density=row["builtup_density"],
            impervious_fraction=row["impervious_fraction"],
            water_dist_m=row["water_dist_m"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            heat_class=row["heat_class"],
            recommendation_summary=summary,
            interventions_json=json.dumps(ranked),
            scene_date=scene_date,
        )
        session.add(zone)
        classes[row["heat_class"]] += 1
        lst_values.append(row["mean_lst"])

    total = len(lst_values)
    snapshot = CitySnapshot(
        city=city,
        scene_id=scene_id,
        scene_date=scene_date,
        mean_lst=sum(lst_values) / total,
        pct_low=classes["low"] / total * 100,
        pct_moderate=classes["moderate"] / total * 100,
        pct_high=classes["high"] / total * 100,
        pct_critical=classes["critical"] / total * 100,
        critical_count=classes["critical"],
    )
    session.add(snapshot)
    session.commit()
    session.close()
    print(f"Seeded {total} zones for {city}")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--city", default="delhi")
    p.add_argument("--zones", type=Path, default=None)
    a = p.parse_args()
    seed(a.city, a.zones)
