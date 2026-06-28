"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchModelMetrics, type CityStats, type ModelMetrics } from "@/lib/api";
import { heatClassColor } from "@/lib/colors";

type Props = {
  stats: CityStats | null;
};

const FEATURE_LABELS: Record<string, string> = {
  ndvi: "Vegetation (NDVI)",
  ndbi: "Built-up index",
  builtup_density: "Built-up density",
  impervious_fraction: "Impervious surface",
  water_dist_m: "Water proximity",
};

export default function InsightsPanel({ stats }: Props) {
  const [metrics, setMetrics] = useState<ModelMetrics | null>(null);

  useEffect(() => {
    fetchModelMetrics().then(setMetrics).catch(() => setMetrics(null));
  }, []);

  if (!stats) {
    return <div className="p-4 text-sm text-slate-400">Loading insights...</div>;
  }

  const classData = [
    { name: "Low", value: stats.pct_low, color: heatClassColor("low") },
    { name: "Moderate", value: stats.pct_moderate, color: heatClassColor("moderate") },
    { name: "High", value: stats.pct_high, color: heatClassColor("high") },
    { name: "Critical", value: stats.pct_critical, color: heatClassColor("critical") },
  ];

  const accuracy =
    metrics?.test_accuracy != null
      ? `${(Number(metrics.test_accuracy) * 100).toFixed(1)}%`
      : "—";
  const cvF1 =
    metrics?.cv_f1_macro != null ? Number(metrics.cv_f1_macro).toFixed(3) : "—";

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Model insights</h2>
        <p className="text-xs text-slate-400">
          Physics-informed LST analysis · {stats.scene_id} · {stats.scene_date}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Mean LST", value: `${stats.mean_lst}°C` },
          { label: "Test accuracy", value: accuracy },
          { label: "Spatial CV F1", value: cvF1 },
          { label: "Critical zones", value: stats.critical_count.toLocaleString() },
        ].map((c) => (
          <div key={c.label} className="rounded-lg border border-slate-800 bg-slate-900/80 p-3">
            <div className="text-[10px] uppercase text-slate-500">{c.label}</div>
            <div className="text-lg font-semibold text-orange-300">{c.value}</div>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
        <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-400">
          Heat class distribution
        </h3>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={classData} layout="vertical" margin={{ left: 8, right: 16 }}>
              <XAxis type="number" domain={[0, 100]} tick={{ fill: "#94a3b8", fontSize: 10 }} />
              <YAxis type="category" dataKey="name" width={72} tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: "#1e293b", border: "1px solid #334155" }}
                formatter={(v: number) => [`${v}%`, "Share"]}
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {classData.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
          Key UHI drivers (model features)
        </h3>
        <ul className="space-y-2 text-sm text-slate-300">
          {(metrics?.features as string[] | undefined)?.map((f) => (
            <li key={f} className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-orange-500" />
              {FEATURE_LABELS[f] ?? f}
            </li>
          )) ?? (
            <>
              <li>Vegetation cover (NDVI)</li>
              <li>Built-up & impervious surfaces</li>
              <li>Distance to water bodies</li>
            </>
          )}
        </ul>
        <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
          Per-zone driver attribution shows which spectral and spatial factors are most
          strongly associated with higher heat risk.
        </p>
      </div>
    </div>
  );
}
