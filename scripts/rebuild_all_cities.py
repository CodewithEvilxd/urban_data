#!/usr/bin/env python3
"""Process and seed every city in city_registry.json."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "city_registry.json"
PROCESS_CITY = ROOT / "scripts" / "process_city.py"
SEED_ALL = ROOT / "api" / "seed_all_cities.py"


def load_registry() -> list[dict]:
    with open(REGISTRY) as f:
        return json.load(f)


def run(cmd: list[str]) -> None:
    print(">>", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, text=True)
    if result.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(cmd)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Process and seed every city in the registry")
    parser.add_argument("--force", action="store_true", help="Reprocess even when zones JSON already exists")
    parser.add_argument("--skip-seed", action="store_true", help="Do not seed the database after processing")
    parser.add_argument("--cities", nargs="*", help="Only process these city slugs")
    parser.add_argument("--start-from", help="Resume processing from this city slug")
    args = parser.parse_args()

    cities = load_registry()
    if args.cities:
        slugs = set(args.cities)
        cities = [c for c in cities if c["slug"] in slugs]
        missing = slugs - {c["slug"] for c in cities}
        if missing:
            raise SystemExit(f"Unknown city slugs: {', '.join(sorted(missing))}")

    started = args.start_from is None
    for city in cities:
        slug = city["slug"]
        if not started:
            if slug == args.start_from:
                started = True
            else:
                continue

        print(f"\n=== Processing {city['name']} ({slug}) ===")
        cmd = [sys.executable, str(PROCESS_CITY), slug]
        if args.force:
            cmd.append("--skip-seed")
        if args.skip_seed:
            cmd.append("--skip-seed")
        run(cmd)

    if not args.skip_seed:
        print("\n=== Seeding all cities ===")
        run([sys.executable, str(SEED_ALL)])

    print("\nRebuild complete.")


if __name__ == "__main__":
    main()
