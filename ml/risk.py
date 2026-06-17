CLASS_WEIGHT = {"low": 1.0, "moderate": 2.0, "high": 3.5, "critical": 5.0}


def heat_risk_index(mean_lst: float, heat_class: str, builtup: float, impervious: float) -> float:
    class_score = CLASS_WEIGHT.get(heat_class, 2.0)
    exposure = builtup * 0.55 + impervious * 0.45
    lst_norm = min(max((mean_lst - 30.0) / 20.0, 0.0), 1.0)
    return round(class_score * 0.45 + exposure * 0.35 + lst_norm * 0.20, 2)


def population_exposure_proxy(builtup: float, impervious: float, mean_lst: float) -> int:
    base = 8000 + builtup * 42000 + impervious * 28000
    heat_boost = max(0.0, (mean_lst - 38.0) * 1200)
    return int(base + heat_boost)


def priority_score(risk_index: float, population_proxy: int) -> int:
    pop_norm = min(population_proxy / 50000.0, 1.0)
    return int(min(100, risk_index * 10 + pop_norm * 40))
