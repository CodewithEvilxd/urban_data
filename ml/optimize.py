import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Strategy:
    key: str
    label: str
    cost_per_km2_crore: float
    lst_reduction_c: tuple[float, float]
    ndvi_delta: float
    impervious_delta: float
    builtup_delta: float
    ndbi_delta: float


STRATEGIES: list[Strategy] = [
    Strategy(
        key="cool_roofs",
        label="Rooftop solar reflective coating",
        cost_per_km2_crore=0.55,
        lst_reduction_c=(2.0, 4.0),
        ndvi_delta=0.00,
        impervious_delta=-0.03,
        builtup_delta=0.00,
        ndbi_delta=-0.02,
    ),
    Strategy(
        key="tree_canopy",
        label="Urban tree canopy expansion",
        cost_per_km2_crore=0.80,
        lst_reduction_c=(2.0, 5.0),
        ndvi_delta=0.12,
        impervious_delta=-0.08,
        builtup_delta=-0.05,
        ndbi_delta=-0.05,
    ),
    Strategy(
        key="green_corridors",
        label="Pocket park / green corridor",
        cost_per_km2_crore=1.10,
        lst_reduction_c=(1.0, 3.0),
        ndvi_delta=0.08,
        impervious_delta=-0.05,
        builtup_delta=-0.03,
        ndbi_delta=-0.03,
    ),
    Strategy(
        key="permeable_pavement",
        label="Permeable pavement retrofit",
        cost_per_km2_crore=0.90,
        lst_reduction_c=(1.0, 2.0),
        ndvi_delta=0.00,
        impervious_delta=-0.12,
        builtup_delta=0.00,
        ndbi_delta=-0.03,
    ),
    Strategy(
        key="water_features",
        label="Water body / fountain feature",
        cost_per_km2_crore=1.50,
        lst_reduction_c=(1.5, 3.5),
        ndvi_delta=0.02,
        impervious_delta=-0.03,
        builtup_delta=0.00,
        ndbi_delta=-0.02,
    ),
    Strategy(
        key="green_walls",
        label="Building setback green wall",
        cost_per_km2_crore=0.70,
        lst_reduction_c=(1.0, 2.5),
        ndvi_delta=0.05,
        impervious_delta=-0.04,
        builtup_delta=-0.02,
        ndbi_delta=-0.03,
    ),
]


def zone_area_km2(cell_size_m: float = 500.0) -> float:
    return (cell_size_m * cell_size_m) / 1_000_000.0


def feasibility_score(zone: dict, strategy: Strategy) -> float:
    ndvi = float(zone["ndvi"])
    builtup = float(zone["builtup_density"])
    imperv = float(zone["impervious_fraction"])
    water_dist = float(zone["water_dist_m"])

    if strategy.key == "tree_canopy":
        return 1.0 if ndvi < 0.35 else 0.4
    if strategy.key == "cool_roofs":
        return 1.0 if builtup > 0.55 and imperv > 0.55 else 0.5
    if strategy.key == "permeable_pavement":
        return 1.0 if imperv > 0.6 else 0.6
    if strategy.key == "water_features":
        return 1.0 if water_dist > 800 else 0.5
    if strategy.key == "green_walls":
        return 1.0 if builtup > 0.65 and ndvi < 0.25 else 0.6
    if strategy.key == "green_corridors":
        return 1.0 if builtup > 0.45 else 0.7
    return 0.7


def exposure_proxy(zone: dict) -> float:
    return float(zone["builtup_density"]) * 0.7 + float(zone["impervious_fraction"]) * 0.3


def expected_benefit(zone: dict, strategy: Strategy, objective: str) -> float:
    heat_class = zone["heat_class"]
    if heat_class not in ("high", "critical"):
        return 0.0

    feas = feasibility_score(zone, strategy)
    low, high = strategy.lst_reduction_c
    cooling = (low + high) / 2.0

    if objective == "max_people_protected":
        return cooling * exposure_proxy(zone) * feas
    if objective == "max_cooling_per_crore":
        return (cooling * feas) / max(strategy.cost_per_km2_crore, 1e-6)
    return cooling * feas


def apply_strategy(zone: dict, strategy: Strategy) -> dict:
    out = dict(zone)
    out["ndvi"] = float(min(max(out["ndvi"] + strategy.ndvi_delta, 0.0), 1.0))
    out["impervious_fraction"] = float(min(max(out["impervious_fraction"] + strategy.impervious_delta, 0.0), 1.0))
    out["builtup_density"] = float(min(max(out["builtup_density"] + strategy.builtup_delta, 0.0), 1.0))
    out["ndbi"] = float(min(max(out["ndbi"] + strategy.ndbi_delta, -1.0), 1.0))
    return out


def optimize_city(
    zones: list[dict],
    budget_crore: float,
    objective: str = "max_cooling",
    max_zones: int = 200,
    cell_size_m: float = 500.0,
) -> dict:
    if objective not in ("max_cooling", "max_people_protected", "max_cooling_per_crore"):
        objective = "max_cooling"

    area_km2 = zone_area_km2(cell_size_m)
    candidates = []
    for z in zones:
        if z.get("heat_class") not in ("high", "critical"):
            continue
        for s in STRATEGIES:
            benefit = expected_benefit(z, s, objective)
            if benefit <= 0:
                continue
            cost = s.cost_per_km2_crore * area_km2
            score = benefit / max(cost, 1e-6)
            candidates.append((score, cost, z["zone_id"], s))

    candidates.sort(key=lambda t: t[0], reverse=True)
    chosen = []
    spent = 0.0
    used_zone = set()
    for score, cost, zone_id, strat in candidates:
        if spent + cost > budget_crore:
            continue
        if zone_id in used_zone:
            continue
        chosen.append((zone_id, strat, cost, score))
        spent += cost
        used_zone.add(zone_id)
        if len(chosen) >= max_zones:
            break

    plan = []
    for zone_id, strat, cost, score in chosen:
        plan.append(
            {
                "zone_id": zone_id,
                "strategy": strat.key,
                "strategy_label": strat.label,
                "cost_crore": round(cost, 4),
                "estimated_lst_reduction_c": {
                    "min": strat.lst_reduction_c[0],
                    "max": strat.lst_reduction_c[1],
                    "source": "Published urban heat mitigation literature ranges",
                },
                "priority_score": round(score, 4),
            }
        )

    return {
        "objective": objective,
        "budget_crore": float(budget_crore),
        "spent_crore": round(spent, 4),
        "selected_zones": len(plan),
        "portfolio": plan,
    }

