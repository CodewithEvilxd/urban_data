#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import planetary_computer
import pystac_client
import requests

DEFAULT_BBOX = (76.84, 28.40, 77.35, 28.88)
CLOUD_MAX = 10
LOOKBACK_DAYS = 60

ASSET_KEYS = {
    "band10": ("lwir11", "B10"),
    "band4": ("red", "B4"),
    "band5": ("nir08", "B5"),
    "mtl": ("mtl.txt", "MTL"),
}


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [float(x.strip()) for x in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be west,south,east,north")
    return tuple(parts)


def scene_id_from_item(item) -> str:
    return item.properties.get("landsat:scene_id") or item.id.replace("/", "_")


def bbox_intersection_area(a: tuple, b: tuple) -> float:
    west = max(a[0], b[0])
    south = max(a[1], b[1])
    east = min(a[2], b[2])
    north = min(a[3], b[3])
    if west >= east or south >= north:
        return 0.0
    return (east - west) * (north - south)


def bbox_contains(outer: tuple, inner: tuple) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def bbox_margin(outer: tuple, inner: tuple) -> float:
    if not bbox_contains(outer, inner):
        return 0.0
    return min(
        inner[0] - outer[0],
        inner[1] - outer[1],
        outer[2] - inner[2],
        outer[3] - inner[3],
    )


def pick_best_scene(items: list, target_bbox: tuple):
    if not items:
        return None
    target_area = max((target_bbox[2] - target_bbox[0]) * (target_bbox[3] - target_bbox[1]), 1e-12)

    def score(item):
        item_bbox = tuple(item.bbox)
        coverage = bbox_intersection_area(item_bbox, target_bbox) / target_area
        full_cover = 1 if bbox_contains(item_bbox, target_bbox) else 0
        margin = bbox_margin(item_bbox, target_bbox)
        cloud = float(item.properties.get("eo:cloud_cover") or 100.0)
        dt = item.properties.get("datetime") or ""
        return (full_cover, coverage, margin, -cloud, dt)

    return max(items, key=score)


def search_scenes(bbox: tuple, start: datetime, end: datetime):
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    search = catalog.search(
        collections=["landsat-c2-l2"],
        bbox=list(bbox),
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        query={"eo:cloud_cover": {"lt": CLOUD_MAX}},
        sortby=[{"field": "datetime", "direction": "desc"}],
        max_items=50,
    )
    items = list(search.items())
    if items:
        return pick_best_scene(items, bbox)

    search = catalog.search(
        collections=["landsat-c2-l2"],
        bbox=list(bbox),
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        sortby=[{"field": "eo:cloud_cover", "direction": "asc"}, {"field": "datetime", "direction": "desc"}],
        max_items=1,
    )
    fallback = list(search.items())
    return pick_best_scene(fallback, bbox)


def download_asset(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    signed = planetary_computer.sign(url)
    with requests.get(signed, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)


def resolve_asset(item, keys: tuple[str, ...]):
    for key in keys:
        if key in item.assets:
            return item.assets[key]
    return None


def fetch_usgs_m2m(bbox: tuple, out_dir: Path) -> str | None:
    username = os.environ.get("USGS_USERNAME")
    password = os.environ.get("USGS_PASSWORD")
    if not username or not password:
        return None

    try:
        from landsatxplore.api import API
        from landsatxplore.earthexplorer import EarthExplorer
    except ImportError:
        print("Install landsatxplore for USGS downloads: pip install landsatxplore", file=sys.stderr)
        return None

    end = datetime.utcnow()
    start = end - timedelta(days=LOOKBACK_DAYS)
    api = API(username, password)
    scenes = api.search(
        dataset="landsat_ot_c2_l2",
        bbox=bbox,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        max_cloud_cover=CLOUD_MAX,
        max_results=5,
    )
    if not scenes:
        scenes = api.search(
            dataset="landsat_ot_c2_l2",
            bbox=bbox,
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            max_results=1,
        )
    if not scenes:
        api.logout()
        return None

    scene = sorted(scenes, key=lambda s: s.get("cloud_cover", 100))[0]
    scene_id = scene["display_id"]
    scene_dir = out_dir / scene_id.replace("/", "_")
    scene_dir.mkdir(parents=True, exist_ok=True)

    ee = EarthExplorer(username, password)
    ee.download(scene["entity_id"], output_dir=str(scene_dir))
    ee.logout()
    api.logout()
    return scene_id


def main():
    parser = argparse.ArgumentParser(description="Download Landsat 8/9 C2 L2 bands for UHI analysis")
    parser.add_argument("--bbox", type=parse_bbox, default=DEFAULT_BBOX, help="west,south,east,north")
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    parser.add_argument("--method", choices=["planetary", "usgs"], default="planetary")
    args = parser.parse_args()

    if args.method == "usgs":
        scene_id = fetch_usgs_m2m(args.bbox, args.output)
        if scene_id:
            print(f"Downloaded USGS scene {scene_id} -> {args.output / scene_id}")
            return
        print("USGS download failed or credentials missing; falling back to Planetary Computer", file=sys.stderr)

    end = datetime.utcnow()
    start = end - timedelta(days=LOOKBACK_DAYS)
    item = search_scenes(args.bbox, start, end)
    if item is None:
        print("No Landsat scenes found for bbox and date range", file=sys.stderr)
        sys.exit(1)

    scene_id = scene_id_from_item(item)
    scene_dir = args.output / scene_id
    scene_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "scene_id": scene_id,
        "datetime": item.properties.get("datetime"),
        "cloud_cover": item.properties.get("eo:cloud_cover"),
        "platform": item.properties.get("platform"),
        "bbox": args.bbox,
        "stac_id": item.id,
        "files": {},
    }

    band10 = resolve_asset(item, ("lwir11", "B10", "ST_B10"))
    st_trad = resolve_asset(item, ("trad", "st_trad", "ST_TRAD"))
    band4 = resolve_asset(item, ("red", "SR_B4", "B4"))
    band5 = resolve_asset(item, ("nir08", "SR_B5", "B5"))
    band6 = resolve_asset(item, ("swir16", "SR_B6", "B6"))
    mtl = resolve_asset(item, ("mtl.txt", "mtl.json", "MTL"))

    downloads = [
        ("band10", band10, scene_dir / f"{scene_id}_B10.TIF"),
        ("band4", band4, scene_dir / f"{scene_id}_B4.TIF"),
        ("band5", band5, scene_dir / f"{scene_id}_B5.TIF"),
        ("mtl", mtl, scene_dir / f"{scene_id}_MTL.txt"),
    ]
    if st_trad:
        downloads.append(("st_trad", st_trad, scene_dir / f"{scene_id}_ST_TRAD.TIF"))
    if band6:
        downloads.append(("band6", band6, scene_dir / f"{scene_id}_B6.TIF"))

    for label, asset, path in downloads:
        if asset is None:
            print(f"Missing asset for {label} on scene {scene_id}", file=sys.stderr)
            sys.exit(1)
        print(f"Downloading {label} -> {path.name}")
        download_asset(asset.href, path)
        manifest["files"][label] = str(path.name)

    mtl_json = resolve_asset(item, ("mtl.json",))
    if mtl_json and not (scene_dir / f"{scene_id}_MTL.json").exists():
        download_asset(mtl_json.href, scene_dir / f"{scene_id}_MTL.json")
        manifest["files"]["mtl_json"] = f"{scene_id}_MTL.json"

    with open(scene_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Scene {scene_id} saved to {scene_dir}")
    print(f"  date: {manifest['datetime']}, cloud: {manifest['cloud_cover']}%")


if __name__ == "__main__":
    main()
