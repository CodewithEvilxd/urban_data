#!/usr/bin/env python3
"""Seed all processed city zone files into PostGIS."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.seed_db import seed


def main():
    processed = ROOT / "data/processed"
    paths = sorted(processed.glob("zones_*.json"))
    if not paths:
        raise SystemExit("No zones_*.json found")

    for path in paths:
        if path.name == "zones_india.json":
            continue
        with open(path) as f:
            city = json.load(f).get("city") or path.stem.replace("zones_", "")
        print(f"Seeding {city} from {path.name}...")
        seed(city=city, zones_path=path)

    print("All cities seeded.")


if __name__ == "__main__":
    main()
