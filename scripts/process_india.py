#!/usr/bin/env python3
"""Process all Indian cities: Landsat fetch → LST → zones per city."""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/city_registry.json"
LOG = ROOT / "data/processed/india_pipeline_log.json"


def load_registry():
    with open(REGISTRY) as f:
        return json.load(f)


def zones_path(slug: str) -> Path:
    return ROOT / f"data/processed/zones_{slug}.json"


def run_city(slug: str, skip_seed: bool) -> dict:
    py = sys.executable
    cmd = [py, str(ROOT / "scripts/process_city.py"), slug]
    if skip_seed:
        cmd.append("--skip-seed")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return {
        "slug": slug,
        "ok": proc.returncode == 0,
        "seconds": round(time.time() - t0, 1),
        "stdout_tail": proc.stdout[-800:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-800:] if proc.stderr else "",
    }


def main():
    parser = argparse.ArgumentParser(description="Batch process all India cities from registry")
    parser.add_argument("--force", action="store_true", help="Reprocess even if zones file exists")
    parser.add_argument("--skip-seed", action="store_true", help="Skip DB seed per city (seed at end)")
    parser.add_argument("--cities", nargs="*", help="Only these slugs (default: all)")
    parser.add_argument("--start-from", default=None, help="Resume from this city slug")
    args = parser.parse_args()

    cities = load_registry()
    if args.cities:
        slugs = set(args.cities)
        cities = [c for c in cities if c["slug"] in slugs]

    results = []
    started = args.start_from is None
    for city in cities:
        slug = city["slug"]
        if not started:
            if slug == args.start_from:
                started = True
            else:
                continue
        if zones_path(slug).exists() and not args.force:
            print(f"[skip] {slug} — zones already exist")
            results.append({"slug": slug, "ok": True, "skipped": True})
            continue
        print(f"\n=== Processing {city['name']} ({slug}) ===")
        result = run_city(slug, skip_seed=args.skip_seed)
        results.append(result)
        status = "OK" if result["ok"] else "FAIL"
        print(f"[{status}] {slug} in {result['seconds']}s")
        if not result["ok"]:
            print(result.get("stderr_tail", ""))

    log = {
        "finished_at": datetime.utcnow().isoformat(),
        "results": results,
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "w") as f:
        json.dump(log, f, indent=2)

    ok = sum(1 for r in results if r.get("ok"))
    print(f"\nDone: {ok}/{len(results)} cities")
    if ok:
        print("Next: python ml/train_india_model.py && python api/seed_all_cities.py")


if __name__ == "__main__":
    main()
