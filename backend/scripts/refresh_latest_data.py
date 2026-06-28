#!/usr/bin/env python3
"""Refresh latest satellite data for every city in the registry.

This is a friendly wrapper around automation/daily_update.py. By default it
processes every city in data/city_registry.json, so future cities are included
automatically after they are added to the registry.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh latest data for all registered cities")
    parser.add_argument("--cities", nargs="*", help="Optional city slugs. Omit to process every registry city.")
    parser.add_argument("--no-retrain", action="store_true", help="Skip India-wide model retraining.")
    parser.add_argument("--push", action="store_true", help="Commit and push changed data to GitHub.")
    parser.add_argument("--include-rasters", action="store_true", help="Force-add raw/lst raster files to git.")
    args = parser.parse_args()

    cmd = [sys.executable, str(ROOT / "automation" / "daily_update.py")]
    if args.cities:
        cmd.extend(["--cities", *args.cities])
    if not args.no_retrain:
        cmd.append("--retrain-model")
    if args.push:
        cmd.append("--push")
    if args.include_rasters:
        cmd.append("--include-rasters")

    print(">>", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
