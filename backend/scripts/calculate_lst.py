# Single-channel LST: Jimenez-Munoz et al. (2014) / Sobrino et al. (2004) NDVI-threshold emissivity method
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.mask import mask as rio_mask
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_geom
from shapely.geometry import box, mapping

WAVELENGTH_UM = 10.8
RHO = 14388.0
NDVI_SOIL = 0.2
NDVI_VEG = 0.5
EMISS_SOIL = 0.97
EMISS_VEG = 0.99


def parse_mtl(mtl_path: Path) -> dict[str, float]:
    text = mtl_path.read_text()
    out: dict[str, float] = {}

    def grab(pattern: str) -> float | None:
        m = re.search(pattern, text, re.IGNORECASE)
        return float(m.group(1)) if m else None

    out["processing_level"] = "L2SP" if "L2SP" in text else "L1TP"
    out["radiance_mult_b10"] = grab(r"RADIANCE_MULT_BAND_10\s*=\s*([\d.E+-]+)")
    out["radiance_add_b10"] = grab(r"RADIANCE_ADD_BAND_10\s*=\s*([\d.E+-]+)")
    out["k1_b10"] = grab(r"K1_CONSTANT_BAND_10\s*=\s*([\d.E+-]+)")
    out["k2_b10"] = grab(r"K2_CONSTANT_BAND_10\s*=\s*([\d.E+-]+)")
    out["refl_mult_b4"] = grab(r"REFLECTANCE_MULT_BAND_4\s*=\s*([\d.E+-]+)") or 2.75e-5
    out["refl_add_b4"] = grab(r"REFLECTANCE_ADD_BAND_4\s*=\s*([-\d.E+-]+)") or -0.2
    out["refl_mult_b5"] = grab(r"REFLECTANCE_MULT_BAND_5\s*=\s*([\d.E+-]+)") or 2.75e-5
    out["refl_add_b5"] = grab(r"REFLECTANCE_ADD_BAND_5\s*=\s*([-\d.E+-]+)") or -0.2
    out["st_trad_scale"] = 0.001
    return out


def find_scene_dir(raw_dir: Path) -> Path:
    dirs = [d for d in raw_dir.iterdir() if d.is_dir()]
    if not dirs:
        raise FileNotFoundError(f"No scenes in {raw_dir}")
    return max(dirs, key=lambda d: d.stat().st_mtime)


def scene_files(scene_dir: Path) -> dict[str, Path]:
    sid = scene_dir.name
    files = {
        "band10": scene_dir / f"{sid}_B10.TIF",
        "band4": scene_dir / f"{sid}_B4.TIF",
        "band5": scene_dir / f"{sid}_B5.TIF",
        "mtl": scene_dir / f"{sid}_MTL.txt",
        "st_trad": scene_dir / f"{sid}_ST_TRAD.TIF",
    }
    for key, path in list(files.items()):
        if not path.exists():
            if key == "st_trad":
                continue
            raise FileNotFoundError(path)
    return files


def clip_to_bbox(dataset, bbox_wgs84: tuple[float, float, float, float]):
    geom_wgs84 = mapping(box(*bbox_wgs84))
    if dataset.crs and str(dataset.crs) != "EPSG:4326":
        geom = transform_geom("EPSG:4326", dataset.crs, geom_wgs84)
    else:
        geom = geom_wgs84
    clipped, transform = rio_mask(dataset, [geom], crop=True, filled=False)
    meta = dataset.meta.copy()
    meta.update({"height": clipped.shape[1], "width": clipped.shape[2], "transform": transform})
    return clipped, meta


def radiance_from_band10(dn: np.ndarray, coeffs: dict) -> np.ndarray:
    if coeffs.get("st_trad_path"):
        trad = dn.astype(np.float64)
        trad = np.where(trad == -9999, np.nan, trad)
        return trad * coeffs["st_trad_scale"]
    return coeffs["radiance_mult_b10"] * dn.astype(np.float64) + coeffs["radiance_add_b10"]


def brightness_temp_kelvin(radiance: np.ndarray, k1: float, k2: float) -> np.ndarray:
    radiance = np.clip(radiance, 1e-6, None)
    return k2 / np.log((k1 / radiance) + 1.0)


def surface_reflectance(dn: np.ndarray, mult: float, add: float) -> np.ndarray:
    refl = dn.astype(np.float64) * mult + add
    return np.clip(refl, 0.0, 1.0)


def ndvi_from_bands(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denom = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir - red) / denom
    ndvi = np.where(denom == 0, np.nan, ndvi)
    return np.clip(ndvi, -1.0, 1.0)


def emissivity_from_ndvi(ndvi: np.ndarray) -> np.ndarray:
    eps = np.empty_like(ndvi, dtype=np.float64)
    bare = ndvi < NDVI_SOIL
    veg = ndvi > NDVI_VEG
    mixed = ~(bare | veg)
    eps[bare] = EMISS_SOIL
    eps[veg] = EMISS_VEG
    pv = ((ndvi[mixed] - NDVI_SOIL) / (NDVI_VEG - NDVI_SOIL)) ** 2
    eps[mixed] = 0.004 * pv + 0.986
    return eps


def lst_celsius(bt_k: np.ndarray, emissivity: np.ndarray) -> np.ndarray:
    corr = 1.0 + (WAVELENGTH_UM * bt_k / RHO) * np.log(emissivity)
    lst_k = bt_k / corr
    return lst_k - 273.15


def write_geotiff(path: Path, array: np.ndarray, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out_meta = meta.copy()
    out_meta.update(dtype="float32", count=1, nodata=np.nan)
    with rasterio.open(path, "w", **out_meta) as dst:
        dst.write(array.astype(np.float32), 1)


def reproject_to_4326(src_path: Path, dst_path: Path) -> None:
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, "EPSG:4326", src.width, src.height, *src.bounds
        )
        meta = src.meta.copy()
        meta.update(crs="EPSG:4326", transform=transform, width=width, height=height)
        with rasterio.open(dst_path, "w", **meta) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs="EPSG:4326",
                resampling=Resampling.bilinear,
                src_nodata=np.nan,
                dst_nodata=np.nan,
            )


def main():
    parser = argparse.ArgumentParser(description="Compute LST from Landsat thermal + optical bands")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--bbox", type=str, default="76.84,28.40,77.35,28.88")
    args = parser.parse_args()

    bbox = tuple(float(x) for x in args.bbox.split(","))
    scene_dir = find_scene_dir(args.raw_dir)
    scene_id = scene_dir.name
    files = scene_files(scene_dir)
    coeffs = parse_mtl(files["mtl"])

    if files["st_trad"].exists():
        coeffs["st_trad_path"] = True
        thermal_path = files["st_trad"]
    else:
        thermal_path = files["band10"]

    with rasterio.open(thermal_path) as b10_src:
        thermal_dn, t_meta = clip_to_bbox(b10_src, bbox)
        thermal_dn = thermal_dn[0].astype(np.float64)

    with rasterio.open(files["band4"]) as b4_src:
        red_dn, _ = clip_to_bbox(b4_src, bbox)
        red_dn = red_dn[0].astype(np.float64)

    with rasterio.open(files["band5"]) as b5_src:
        nir_dn, _ = clip_to_bbox(b5_src, bbox)
        nir_dn = nir_dn[0].astype(np.float64)

    if np.ma.isMaskedArray(thermal_dn):
        invalid = thermal_dn.mask
        thermal_dn = thermal_dn.data
    else:
        invalid = np.zeros_like(thermal_dn, dtype=bool)

    valid = (thermal_dn != -9999) & (thermal_dn > 0) & (red_dn > 0) & (nir_dn > 0) & ~invalid
    thermal = np.where(valid, thermal_dn, np.nan)
    red = np.where(valid, red_dn, np.nan)
    nir = np.where(valid, nir_dn, np.nan)

    radiance = radiance_from_band10(thermal, coeffs)
    bt_k = brightness_temp_kelvin(radiance, coeffs["k1_b10"], coeffs["k2_b10"])

    red_refl = surface_reflectance(red, coeffs["refl_mult_b4"], coeffs["refl_add_b4"])
    nir_refl = surface_reflectance(nir, coeffs["refl_mult_b5"], coeffs["refl_add_b5"])
    ndvi = ndvi_from_bands(red_refl, nir_refl)
    emissivity = emissivity_from_ndvi(ndvi)

    lst = lst_celsius(bt_k, emissivity)
    lst = np.where(valid, lst, np.nan)

    tmp_path = args.output_dir / f"lst_{scene_id}_utm.tif"
    final_path = args.output_dir / f"lst_{scene_id}.tif"
    write_geotiff(tmp_path, lst, t_meta)
    reproject_to_4326(tmp_path, final_path)
    tmp_path.unlink(missing_ok=True)

    finite = lst[np.isfinite(lst)]
    if finite.size == 0:
        print("No valid LST pixels", file=sys.stderr)
        sys.exit(1)

    print(f"LST written to {final_path}")
    print(f"  pixels: {finite.size}")
    print(f"  mean: {finite.mean():.2f} C")
    print(f"  min: {finite.min():.2f} C")
    print(f"  max: {finite.max():.2f} C")


if __name__ == "__main__":
    main()
