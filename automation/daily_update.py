#!/usr/bin/env python3
"""Daily satellite data refresh and optional GitHub push.

Designed for Render Cron Jobs or any scheduler. It reuses the existing
city pipeline, commits changed data artifacts, and can push them back to
the configured GitHub repository.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "city_registry.json"
STATE_PATH = ROOT / "data" / "processed" / "daily_update_state.json"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print(">>", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, text=True, check=check)


def capture(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_registry() -> list[dict]:
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def selected_cities(cli_cities: list[str] | None) -> list[str]:
    if cli_cities:
        requested = cli_cities
    else:
        requested = [
            c.strip()
            for c in os.getenv("DAILY_CITIES", "").replace(";", ",").split(",")
            if c.strip()
        ]

    registry = load_registry()
    known = {city["slug"] for city in registry}
    if not requested:
        return [city["slug"] for city in registry if city.get("has_data", True)]

    missing = sorted(set(requested) - known)
    if missing:
        raise SystemExit(f"Unknown city slugs: {', '.join(missing)}")
    return requested


def read_scene(city: str) -> dict:
    path = ROOT / "data" / "processed" / f"zones_{city}.json"
    if not path.exists():
        return {"scene_id": None, "scene_date": None, "zone_count": 0}
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return {
        "scene_id": payload.get("scene_id"),
        "scene_date": payload.get("scene_date"),
        "zone_count": len(payload.get("zones", [])),
    }


def git_has_changes(paths: list[str]) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *paths],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    return bool(result.stdout.strip())


def configure_git() -> None:
    run(["git", "config", "user.name", os.getenv("GIT_AUTHOR_NAME", "urbancool-data-bot")])
    run(["git", "config", "user.email", os.getenv("GIT_AUTHOR_EMAIL", "urbancool-data-bot@example.com")])

    token = os.getenv("GITHUB_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY")
    if token and repository:
        run(["git", "remote", "set-url", "origin", f"https://x-access-token:{token}@github.com/{repository}.git"])


def git_commit_and_push(message: str, include_rasters: bool, push: bool) -> None:
    data_paths = [
        "data/processed",
        "data/city_registry.json",
        "ml/models/model_metrics.json",
        "ml/models/heat_classifier.joblib",
        "ml/models/feature_importance.png",
    ]
    if include_rasters:
        data_paths.extend(["data/raw"])

    if not git_has_changes(data_paths):
        print("No data changes detected; skipping commit.")
        return

    configure_git()
    run(["git", "add", "data/processed", "data/city_registry.json", "ml/models/model_metrics.json"])
    if Path(ROOT / "ml/models/heat_classifier.joblib").exists():
        run(["git", "add", "-f", "ml/models/heat_classifier.joblib"])
    if Path(ROOT / "ml/models/feature_importance.png").exists():
        run(["git", "add", "-f", "ml/models/feature_importance.png"])
    if include_rasters:
        run(["git", "add", "-f", "data/raw", "data/processed/lst"])

    staged = capture(["git", "diff", "--cached", "--name-only"])
    if not staged:
        print("No staged data changes; skipping commit.")
        return

    print("Staged files:")
    print(staged)
    run(["git", "commit", "-m", message])
    if push:
        run(["git", "push", "origin", os.getenv("GIT_BRANCH", "main")])
    else:
        print("Commit created locally. Use --push or PUSH_CHANGES=true to push to GitHub.")


def write_state(results: list[dict]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def refresh_national_grid() -> None:
    sys.path.insert(0, str(ROOT))
    from api.json_store import get_store
    from ml.national_grid import build_national_grid

    out = ROOT / "data" / "processed" / "india_national_grid.json"
    features = build_national_grid(get_store().interpolation_points())
    with open(out, "w", encoding="utf-8") as f:
        json.dump(features, f)
    print(f"National grid saved to {out} ({len(features)} cells)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh city heat data and optionally push to GitHub")
    parser.add_argument("--cities", nargs="*", help="City slugs. Defaults to DAILY_CITIES or registry cities.")
    parser.add_argument("--retrain-model", action="store_true", help="Retrain India model after city refresh.")
    parser.add_argument("--skip-seed", action="store_true", help="Do not seed DB during city processing.")
    parser.add_argument("--include-rasters", action="store_true", help="Force-add raw/lst raster files to git.")
    parser.add_argument("--push", action="store_true", help="Push committed changes to GitHub.")
    args = parser.parse_args()

    cities = selected_cities(args.cities)
    retrain_model = args.retrain_model or env_bool("RETRAIN_MODEL", default=False)
    include_rasters = args.include_rasters or env_bool("INCLUDE_RASTERS", default=False)
    push = args.push or env_bool("PUSH_CHANGES", default=False)
    skip_seed = args.skip_seed or env_bool("SKIP_SEED", default=True)

    results = []
    for city in cities:
        before = read_scene(city)
        cmd = [sys.executable, str(ROOT / "scripts" / "process_city.py"), city]
        if skip_seed:
            cmd.append("--skip-seed")
        try:
            run(cmd)
            after = read_scene(city)
            results.append({"city": city, "status": "ok", "before": before, "after": after})
        except subprocess.CalledProcessError as exc:
            results.append({"city": city, "status": "failed", "returncode": exc.returncode, "before": before})
            print(f"City failed: {city}", file=sys.stderr)

    write_state(results)

    if retrain_model:
        run([sys.executable, str(ROOT / "ml" / "train_india_model.py")])
        refresh_national_grid()

    ok = [r for r in results if r["status"] == "ok"]
    changed = [
        r["city"]
        for r in ok
        if r["before"].get("scene_id") != r["after"].get("scene_id")
        or r["before"].get("zone_count") != r["after"].get("zone_count")
    ]
    label = ", ".join(changed) if changed else f"{len(ok)} city checks"
    message = f"data: daily satellite refresh ({label})"
    git_commit_and_push(message, include_rasters=include_rasters, push=push)

    failed = [r["city"] for r in results if r["status"] != "ok"]
    if failed:
        raise SystemExit(f"Daily update finished with failed cities: {', '.join(failed)}")


if __name__ == "__main__":
    main()
