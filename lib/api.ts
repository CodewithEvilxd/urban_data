const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type ZoneProperties = {
  zone_id: string;
  mean_lst: number;
  ndvi: number;
  ndbi: number;
  builtup_density: number;
  impervious_fraction: number;
  water_dist_m: number;
  latitude: number;
  longitude: number;
  heat_class: string;
  recommendation_summary: string;
};

export type ZoneFeature = {
  type: "Feature";
  id: string;
  geometry: GeoJSON.Polygon;
  properties: ZoneProperties;
};

export type ZoneCollection = {
  type: "FeatureCollection";
  features: ZoneFeature[];
};

export type DriverAttribution = {
  feature: string;
  delta_high_critical_proba: number;
};

export type ZoneDetail = ZoneProperties & {
  geometry: GeoJSON.Polygon;
  interventions: {
    intervention: string;
    estimated_lst_reduction_c: { min: number; max: number; source: string };
    rationale: string;
  }[];
  drivers?: DriverAttribution[];
  heat_risk_index?: number;
  population_exposure?: number;
  priority_score?: number;
  data_source?: "measured" | "estimated";
  nearest_measured_km?: number;
  distance_m?: number;
};

export type CityStats = {
  city: string;
  mean_lst: number;
  pct_low: number;
  pct_moderate: number;
  pct_high: number;
  pct_critical: number;
  critical_count: number;
  scene_id: string;
  scene_date: string;
  zone_count?: number;
  trend: { date: string; mean_lst: number }[];
  live?: {
    status: string;
    last_refresh: string;
    data_source: string;
    pipeline: string;
  };
};

export type IndiaCity = {
  slug: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
  bbox: number[];
  has_data: boolean;
  zone_count: number;
};

export type SimulateResult = {
  zone_id: string;
  current_class: string;
  predicted_class: string;
  class_changed: boolean;
  ndvi_after: number;
  estimated_lst_c: number;
  estimated_lst_reduction_c: number;
  confidence: number;
};

export type AreaResult = { name: string; lat: number; lon: number };

export type NearZone = ZoneDetail & { distance_m: number };

export type ReverseGeocode = {
  display_name?: string;
  postcode?: string | null;
  suburb?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  source?: string;
};

export type PriorityZone = {
  zone_id: string;
  mean_lst: number;
  heat_class: string;
  latitude: number;
  longitude: number;
  heat_risk_index: number;
  population_exposure: number;
  priority_score: number;
  recommendation_summary: string;
};

export type StrategyInfo = {
  key: string;
  label: string;
  cost_per_km2_crore: number;
  cost_per_cell_crore: number;
  lst_reduction_c: { min: number; max: number };
  ndvi_delta: number;
  impervious_delta: number;
};

export type PortfolioItem = {
  zone_id: string;
  strategy: string;
  strategy_label: string;
  cost_crore: number;
  estimated_lst_reduction_c: { min: number; max: number; source: string };
  priority_score: number;
  current_class?: string;
  predicted_class_after?: string;
  confidence?: number;
};

export type OptimizeResult = {
  objective: string;
  budget_crore: number;
  spent_crore: number;
  selected_zones: number;
  portfolio: PortfolioItem[];
};

export type LiveStatus = {
  status: string;
  city: string;
  scene_id?: string;
  scene_date?: string;
  mean_lst?: number;
  critical_count?: number;
  zone_count: number;
  data_source: string;
  pipeline?: string;
  last_refresh: string;
  message?: string;
};

export type ModelMetrics = {
  test_accuracy?: number;
  cv_f1_macro?: number;
  n_zones?: number;
  features?: string[];
  [key: string]: unknown;
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { ...init, cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export function fetchZones(city = "delhi") {
  return fetchJson<ZoneCollection>(`/api/zones?city=${city}`);
}

export function fetchZonesByBbox(bbox: string, city?: string, limit = 12000) {
  const q = new URLSearchParams();
  q.set("bbox", bbox);
  q.set("limit", String(limit));
  if (city) q.set("city", city);
  return fetchJson<ZoneCollection>(`/api/zones?${q.toString()}`);
}

export function fetchIndiaOverview() {
  return fetchJson<ZoneCollection>("/api/zones/india-national");
}

export function fetchIndiaNational() {
  return fetchJson<ZoneCollection>("/api/zones/india-national");
}

export function fetchZoneEstimate(lat: number, lon: number) {
  return fetchJson<ZoneDetail>(`/api/zones/estimate?lat=${lat}&lon=${lon}`);
}

export function fetchCities() {
  return fetchJson<{ cities: IndiaCity[] }>("/api/cities");
}

export function fetchZoneDetail(zoneId: string) {
  return fetchJson<ZoneDetail>(`/api/zones/${zoneId}`);
}

export function fetchStats(city = "delhi", bbox?: string) {
  const q = new URLSearchParams();
  q.set("city", city);
  if (bbox) q.set("bbox", bbox);
  return fetchJson<CityStats>(`/api/stats?${q.toString()}`);
}

export function simulateZone(zoneId: string, ndviIncrease: number) {
  return fetchJson<SimulateResult>("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zone_id: zoneId, ndvi_increase: ndviIncrease }),
  });
}

export function searchAreas(q: string) {
  return fetchJson<{ results: AreaResult[] }>(`/api/search/areas?q=${encodeURIComponent(q)}`).then(
    (r) => r.results
  );
}

export function reverseGeocode(lat: number, lon: number) {
  return fetchJson<ReverseGeocode>(`/api/geocode/reverse?lat=${lat}&lon=${lon}`);
}

export function fetchZoneNear(lat: number, lon: number, city = "delhi") {
  return fetchJson<NearZone>(`/api/zones/near?lat=${lat}&lon=${lon}&city=${city}`);
}

export function fetchZoneNearAny(lat: number, lon: number) {
  return fetchJson<NearZone>(`/api/zones/near?lat=${lat}&lon=${lon}`);
}

export function fetchModelMetrics() {
  return fetchJson<ModelMetrics>("/api/model/metrics");
}

export function fetchPriorities(city?: string, limit = 25, bbox?: string) {
  const q = new URLSearchParams();
  if (city) q.set("city", city);
  q.set("limit", String(limit));
  if (bbox) q.set("bbox", bbox);
  return fetchJson<{ city: string; count: number; zones: PriorityZone[] }>(
    `/api/zones/priorities?${q.toString()}`
  );
}

export function fetchStrategies() {
  return fetchJson<{ strategies: StrategyInfo[] }>("/api/strategies");
}

export function fetchLiveStatus(city = "delhi", bbox?: string) {
  const q = new URLSearchParams();
  q.set("city", city);
  if (bbox) q.set("bbox", bbox);
  return fetchJson<LiveStatus>(`/api/live?${q.toString()}`);
}

export function optimizeScenario(
  city: string,
  budgetCrore: number,
  objective: string,
  maxZones = 50,
  bbox?: string
) {
  return fetchJson<OptimizeResult>("/api/scenarios/optimize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      city,
      budget_crore: budgetCrore,
      objective,
      max_zones: maxZones,
      bbox: bbox ?? null,
    }),
  });
}
