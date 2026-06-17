"use client";

import type { CityStats } from "@/lib/api";

type Props = {
  stats: CityStats | null;
};

export default function StatsBar({ stats }: Props) {
  if (!stats) {
    return (
      <div className="grid grid-cols-2 gap-3 p-4 md:grid-cols-5 md:gap-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-lg bg-slate-800" />
        ))}
      </div>
    );
  }

  const items = [
    { label: "Mean LST", value: `${stats.mean_lst}°C` },
    { label: "Critical zones", value: stats.critical_count.toLocaleString() },
    { label: "Low", value: `${stats.pct_low}%` },
    { label: "Moderate", value: `${stats.pct_moderate}%` },
    { label: "High / Critical", value: `${(stats.pct_high + stats.pct_critical).toFixed(1)}%` },
  ];

  return (
    <div className="border-b border-slate-800 bg-slate-900/80 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-white md:text-xl">UrbanCool</h1>
          <p className="text-xs text-slate-400">
            {stats.city === "delhi" ? "Delhi NCR" : stats.city} · Landsat {stats.scene_id} ·{" "}
            {stats.scene_date}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5 md:gap-3">
          {items.map((item) => (
            <div key={item.label} className="rounded-lg bg-slate-800/80 px-3 py-2 text-center">
              <div className="text-[10px] uppercase tracking-wider text-slate-400">{item.label}</div>
              <div className="text-sm font-medium text-white md:text-base">{item.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
