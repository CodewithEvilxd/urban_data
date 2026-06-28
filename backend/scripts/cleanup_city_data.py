#!/usr/bin/env python3
"""Delete processed and seeded city data for specified Indian cities."""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "city_registry.json"
PROCESSED = ROOT / "data" / "processed"
RAW_CITIES = ROOT / "data" / "raw" / "cities"


def load_registry() -> dict[str, dict]:
    with open(REGISTRY) as f:
        return {c["slug"]: c for c in json.load(f)}


def remove_processed_json(slug: str) -> bool:
    path = PROCESSED / f"zones_{slug}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def remove_raw_city(slug: str) -> bool:
    path = RAW_CITIES / slug
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        return True
    return False


def query_db_rows(slug: str) -> tuple[int, int]:
    from api.models import CitySnapshot, HeatZone, SessionLocal

    session = SessionLocal()
    try:
        zone_count = session.query(HeatZone).filter(HeatZone.city.ilike(f"%{slug}%")).count()
        snapshot_count = session.query(CitySnapshot).filter(CitySnapshot.city.ilike(f"%{slug}%")).count()
        return zone_count, snapshot_count
    finally:
        session.close()


def delete_db_rows(slugs: list[str]) -> None:
    from api.models import CitySnapshot, HeatZone, SessionLocal

    session = SessionLocal()
    try:
        for slug in slugs:
            deleted_zones = session.query(HeatZone).filter(HeatZone.city.ilike(f"%{slug}%")).delete()
            deleted_snapshots = session.query(CitySnapshot).filter(CitySnapshot.city.ilike(f"%{slug}%")).delete()
            print(f"Deleted {deleted_zones} HeatZone rows and {deleted_snapshots} CitySnapshot rows for {slug}")
        session.commit()
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup processed and seeded city data")
    parser.add_argument("--cities", nargs="+", required=True, help="City slugs to clean")
    parser.add_argument("--remove-json", action="store_true", help="Remove processed data/ zones_<city>.json files")
    parser.add_argument("--remove-raw", action="store_true", help="Remove downloaded raw city data directories")
    parser.add_argument("--delete-db", action="store_true", help="Delete seeded city rows from the database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without changing anything")
    args = parser.parse_args()

    registry = load_registry()
    missing = [slug for slug in args.cities if slug not in registry]
    if missing:
        raise SystemExit(f"Unknown city slugs: {', '.join(missing)}")

    print(f"Cleaning cities: {', '.join(args.cities)}")
    if args.dry_run:
        print("Dry run mode: no changes will be made")

    for slug in args.cities:
        print(f"\nCity: {slug}")
        if args.remove_json:
            path = PROCESSED / f"zones_{slug}.json"
            print(f"  Processed JSON: {path} {'(exists)' if path.exists() else '(missing)'}")
            if not args.dry_run and path.exists():
                path.unlink()
                print("    removed")
        if args.remove_raw:
            raw_path = RAW_CITIES / slug
            print(f"  Raw data dir: {raw_path} {'(exists)' if raw_path.exists() else '(missing)'}")
            if not args.dry_run and raw_path.exists():
                shutil.rmtree(raw_path)
                print("    removed")
        if args.delete_db:
            zone_count, snapshot_count = query_db_rows(slug)
            print(f"  DB rows found for slug pattern '{slug}': {zone_count} HeatZone, {snapshot_count} CitySnapshot")

    if args.delete_db:
        if args.dry_run:
            print("\nDB delete: dry run, no DB changes will be made")
        else:
            print("\nDeleting DB rows...")
            delete_db_rows(args.cities)

    print("\nCleanup complete.")


if __name__ == "__main__":
    main()
