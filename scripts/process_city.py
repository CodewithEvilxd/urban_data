#!/usr/bin/env python3
"""Run full Landsat pipeline for any Indian city in city_registry.json."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/city_registry.json"


def main():
    parser = argparse.ArgumentParser(description="Process UHI pipeline for an Indian city")
    parser.add_argument("city", help="City slug, e.g. delhi, mumbai, bengaluru")
    parser.add_argument("--skip-seed", action="store_true")
    args = parser.parse_args()

    with open(REGISTRY) as f:
        cities = {c["slug"]: c for c in json.load(f)}

    if args.city not in cities:
        print(f"Unknown city '{args.city}'. Available: {', '.join(sorted(cities))}", file=sys.stderr)
        sys.exit(1)

    city = cities[args.city]
    bbox = ",".join(str(x) for x in city["bbox"])
    py = sys.executable
    raw_dir = ROOT / f"data/raw/cities/{args.city}"
    zones_out = ROOT / f"data/processed/zones_{args.city}.json"

    steps = [
        [py, str(ROOT / "scripts/fetch_landsat.py"), "--bbox", bbox, "--output", str(raw_dir)],
        [py, str(ROOT / "scripts/calculate_lst.py"), "--raw-dir", str(raw_dir), "--bbox", bbox],
        [
            py,
            str(ROOT / "ml/train_classifier.py"),
            "--raw-dir",
            str(raw_dir),
            "--bbox",
            bbox,
            "--city",
            args.city,
            "--output",
            str(zones_out),
            "--zones-only",
        ],
    ]
    if not args.skip_seed:
        steps.append([py, str(ROOT / "api/seed_db.py"), "--city", args.city, "--zones", str(zones_out)])

    for cmd in steps:
        print(">>", " ".join(cmd))
        subprocess.run(cmd, cwd=ROOT, check=True)

    print(f"Done: {city['name']} ({args.city})")


if __name__ == "__main__":
    main()
