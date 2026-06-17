from dataclasses import dataclass


@dataclass
class Intervention:
    name: str
    lst_reduction_c: tuple[float, float]
    rationale: str


INTERVENTIONS = {
    "rooftop_solar_reflective_coating": Intervention(
        "Rooftop solar reflective coating",
        (2.0, 4.0),
        "High built-up density with low vegetation — cool roofs reduce absorbed solar flux on horizontal surfaces.",
    ),
    "urban_tree_canopy": Intervention(
        "Urban tree canopy expansion",
        (2.0, 5.0),
        "Low NDVI with room for canopy cover — shade and evapotranspiration lower surface temperatures.",
    ),
    "pocket_park_green_corridor": Intervention(
        "Pocket park / green corridor",
        (1.0, 3.0),
        "Moderate vegetation in dense areas — contiguous green patches reduce heat accumulation.",
    ),
    "permeable_pavement": Intervention(
        "Permeable pavement retrofit",
        (1.0, 2.0),
        "High impervious fraction — permeable surfaces retain moisture and reduce sensible heat.",
    ),
    "water_body_fountain": Intervention(
        "Water body / fountain feature",
        (1.5, 3.5),
        "Far from existing water features — evaporative cooling from open water lowers local LST.",
    ),
    "building_setback_green_wall": Intervention(
        "Building setback green wall",
        (1.0, 2.5),
        "Very high built-up density with minimal green cover — vertical greening shades facades.",
    ),
}


def rank_interventions(
    heat_class: str,
    ndvi: float,
    builtup_density: float,
    impervious_fraction: float,
    water_dist_m: float,
) -> list[dict]:
    if heat_class not in ("high", "critical"):
        return []

    scores: list[tuple[float, Intervention]] = []

    if builtup_density > 0.55 and impervious_fraction > 0.6:
        scores.append((0.9 + builtup_density, INTERVENTIONS["rooftop_solar_reflective_coating"]))

    if ndvi < 0.25:
        scores.append((0.85 + (0.25 - ndvi), INTERVENTIONS["urban_tree_canopy"]))
    elif ndvi < 0.4:
        scores.append((0.7 + (0.4 - ndvi), INTERVENTIONS["urban_tree_canopy"]))

    if builtup_density > 0.45 and ndvi < 0.35:
        scores.append((0.75 + builtup_density * 0.3, INTERVENTIONS["pocket_park_green_corridor"]))

    if impervious_fraction > 0.55:
        scores.append((0.65 + impervious_fraction * 0.4, INTERVENTIONS["permeable_pavement"]))

    if water_dist_m > 800:
        scores.append((0.6 + min(water_dist_m / 5000, 0.35), INTERVENTIONS["water_body_fountain"]))

    if builtup_density > 0.65 and ndvi < 0.2:
        scores.append((0.8 + builtup_density * 0.2, INTERVENTIONS["building_setback_green_wall"]))

    scores.sort(key=lambda x: x[0], reverse=True)
    seen = set()
    ranked = []
    for _, item in scores:
        if item.name in seen:
            continue
        seen.add(item.name)
        ranked.append(
            {
                "intervention": item.name,
                "estimated_lst_reduction_c": {
                    "min": item.lst_reduction_c[0],
                    "max": item.lst_reduction_c[1],
                    "source": "Published urban heat mitigation literature ranges",
                },
                "rationale": item.rationale,
            }
        )
    return ranked


def recommendation_summary(ranked: list[dict]) -> str:
    if not ranked:
        return "No cooling intervention required"
    top = ranked[0]["intervention"]
    lo = ranked[0]["estimated_lst_reduction_c"]["min"]
    hi = ranked[0]["estimated_lst_reduction_c"]["max"]
    return f"Primary: {top} (est. {lo}-{hi} C reduction per literature)"
