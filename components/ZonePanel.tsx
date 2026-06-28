"use client";

import type { ReverseGeocode, ZoneDetail } from "@/lib/api";
import { CLASS_LABELS, heatClassColor } from "@/lib/colors";
import TrendChart from "./TrendChart";
import type { CityStats } from "@/lib/api";

const DRIVER_LABELS: Record<string, string> = {
  ndvi: "Vegetation (NDVI)",
  ndbi: "Built-up index",
  builtup_density: "Built-up density",
  impervious_fraction: "Impervious surface",
  water_dist_m: "Water distance",
  latitude: "Latitude",
  longitude: "Longitude",
};

type Props = {
  zone: ZoneDetail | null;
  loading: boolean;
  simulating: boolean;
  simulatedClass: string | null;
  onSimulateAction: (ndviIncrease: number) => void;
  onCloseAction: () => void;
  stats: CityStats | null;
  location?: ReverseGeocode | null;
};

export default function ZonePanel({
  zone,
  loading,
  simulating,
  simulatedClass,
  onSimulateAction,
  onCloseAction,
  stats,
  location,
}: Props) {
  const displayClass = simulatedClass ?? zone?.heat_class;
  const locationDisplayName = location?.display_name?.trim() || null;
  const locationTitle =
    location?.place_name ??
    location?.suburb ??
    location?.village ??
    location?.town ??
    location?.city ??
    location?.county ??
    zone?.place_name ??
    locationDisplayName ??
    (zone ? `${zone.latitude.toFixed(5)}, ${zone.longitude.toFixed(5)}` : null);
  const locationDetail =
    locationDisplayName && locationDisplayName !== locationTitle
      ? locationDisplayName
      : zone?.place_state
      ? [zone.place_state, "India"].filter(Boolean).join(", ")
      : location
      ? [location.state, location.country].filter(Boolean).join(", ") || null
      : zone
      ? `Coordinates: ${zone.latitude.toFixed(5)}, ${zone.longitude.toFixed(5)}`
      : null;
  const coordinateDetail = zone
    ? `${zone.latitude.toFixed(5)}, ${zone.longitude.toFixed(5)}`
    : null;

  return (
    <aside
      className={`fixed right-0 top-0 z-[1000] h-full w-full max-w-md transform border-l border-slate-800 bg-slate-900 shadow-2xl transition-transform duration-300 ${
        zone || loading ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <div className="flex h-full flex-col overflow-y-auto p-4 md:p-5">
        <div className="mb-4 flex items-start justify-between">
          <h2 className="text-lg font-semibold text-white">Zone intelligence</h2>
          <button
            onClick={onCloseAction}
            className="rounded-md border border-slate-700 bg-slate-900/80 p-2 text-slate-400 transition hover:bg-slate-800 hover:text-white"
            aria-label="Close panel"
          >
            <span className="inline-flex items-center justify-center">
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m6 6 12 12" />
                <path d="m18 6-12 12" />
              </svg>
            </span>
          </button>
        </div>

        {loading && <p className="text-sm text-slate-400">Loading zone...</p>}

        {zone && (
          <>
            {locationTitle && locationDetail && (
              <div className="mb-3 rounded-lg border border-slate-800 bg-slate-800/40 p-2 text-xs text-slate-300">
                <div className="font-medium text-white">{locationTitle}</div>
                <div className="text-slate-400">{locationDetail}</div>
                {coordinateDetail && locationDetail !== `Coordinates: ${coordinateDetail}` && (
                  <div className="mt-1 font-mono text-[10px] text-slate-500">
                    {coordinateDetail}
                  </div>
                )}
                {location?.source === "local" && (
                  <div className="mt-1 text-[10px] text-amber-300">
                    Approximate local place label
                  </div>
                )}
                {location?.postcode && (
                  <div className="mt-1 text-slate-500">PIN {location.postcode}</div>
                )}
              </div>
            )}

            <div className="mb-4 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-slate-800/60 p-2">
                <div className="text-[10px] text-slate-500">Heat Risk Index</div>
                <div className="text-lg font-semibold text-orange-400">
                  {zone.heat_risk_index?.toFixed(1) ?? "—"}
                </div>
              </div>
              <div className="rounded-lg bg-slate-800/60 p-2">
                <div className="text-[10px] text-slate-500">Priority score</div>
                <div className="text-lg font-semibold text-white">
                  {zone.priority_score ?? "—"}
                </div>
              </div>
            </div>

            <div className="mb-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">Zone</span>
                <span className="font-mono text-slate-200">{zone.zone_id}</span>
              </div>
              {zone.data_source && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Data</span>
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      zone.data_source === "measured"
                        ? "bg-emerald-900/60 text-emerald-300"
                        : "bg-amber-900/50 text-amber-200"
                    }`}
                  >
                    {zone.data_source === "measured"
                      ? "Landsat measured"
                      : `AIML estimate${zone.nearest_measured_km ? ` · ${zone.nearest_measured_km} km to nearest` : ""}`}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-slate-400">LST</span>
                <span className="font-medium text-orange-400">{zone.mean_lst.toFixed(1)}°C</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">NDVI</span>
                <span>{zone.ndvi.toFixed(3)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Built-up proxy</span>
                <span>{(zone.builtup_density * 100).toFixed(0)}%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Classification</span>
                <span
                  className="rounded-full px-2 py-0.5 text-xs font-medium text-slate-900"
                  style={{ background: heatClassColor(displayClass ?? zone.heat_class) }}
                >
                  {CLASS_LABELS[displayClass ?? zone.heat_class] ?? displayClass}
                  {simulatedClass && simulatedClass !== zone.heat_class ? " (simulated)" : ""}
                </span>
              </div>
            </div>

            {zone.drivers && zone.drivers.length > 0 && (
              <div className="mb-5 rounded-lg border border-slate-800 bg-slate-800/40 p-3">
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
                  Driver attribution
                </h3>
                <ul className="space-y-2">
                  {zone.drivers.map((d) => (
                    <li key={d.feature} className="flex justify-between text-xs">
                      <span className="text-slate-300">
                        {DRIVER_LABELS[d.feature] ?? d.feature}
                      </span>
                      <span
                        className={
                          d.delta_high_critical_proba > 0 ? "text-red-400" : "text-emerald-400"
                        }
                      >
                        {d.delta_high_critical_proba > 0 ? "+" : ""}
                        {(d.delta_high_critical_proba * 100).toFixed(1)}%
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mb-5 rounded-lg border border-slate-800 bg-slate-800/50 p-3">
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
                What-if: increase green cover
              </h3>
              <div className="flex flex-wrap gap-2">
                {[0.05, 0.1, 0.15, 0.2].map((inc) => (
                  <button
                    key={inc}
                    disabled={simulating}
                    onClick={() => onSimulateAction(inc)}
                    className="rounded-md bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
                  >
                    +{inc} NDVI
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-5">
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
                Cooling recommendations
              </h3>
              {zone.interventions.length === 0 ? (
                <p className="text-sm text-slate-400">No intervention required for this zone.</p>
              ) : (
                <ol className="space-y-3">
                  {zone.interventions.map((item, idx) => (
                    <li key={item.intervention} className="rounded-lg border border-slate-800 p-3 text-sm">
                      <div className="mb-1 font-medium text-white">
                        {idx + 1}. {item.intervention}
                      </div>
                      <div className="mb-1 text-orange-300">
                        Est. {item.estimated_lst_reduction_c.min}–{item.estimated_lst_reduction_c.max}°C
                      </div>
                      <p className="text-xs text-slate-400">{item.rationale}</p>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <TrendChart stats={stats} />
          </>
        )}
      </div>
    </aside>
  );
}
