"use client";

import { useEffect, useState } from "react";
import { fetchStrategies, type StrategyInfo } from "@/lib/api";

export default function MaterialTable() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);

  useEffect(() => {
    fetchStrategies()
      .then((r) => setStrategies(r.strategies))
      .catch(() => setStrategies([]));
  }, []);

  if (!strategies.length) {
    return (
      <div className="rounded-lg border border-slate-800 p-4 text-sm text-slate-400">
        Loading material performance data...
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-800">
      <table className="w-full text-xs">
        <thead className="bg-slate-800 text-slate-400">
          <tr>
            <th className="px-3 py-2 text-left">Cooling strategy</th>
            <th className="px-3 py-2 text-right">LST ↓ (°C)</th>
            <th className="px-3 py-2 text-right">Cost / km²</th>
            <th className="px-3 py-2 text-right">NDVI Δ</th>
          </tr>
        </thead>
        <tbody>
          {strategies.map((s) => (
            <tr key={s.key} className="border-t border-slate-800 hover:bg-slate-800/50">
              <td className="px-3 py-2 font-medium text-slate-200">{s.label}</td>
              <td className="px-3 py-2 text-right text-orange-300">
                {s.lst_reduction_c.min}–{s.lst_reduction_c.max}
              </td>
              <td className="px-3 py-2 text-right text-slate-300">₹{s.cost_per_km2_crore} Cr</td>
              <td className="px-3 py-2 text-right text-emerald-400">
                {s.ndvi_delta > 0 ? `+${s.ndvi_delta}` : s.ndvi_delta || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-slate-800 bg-slate-900/50 px-3 py-2 text-[10px] text-slate-500">
        Literature-based LST reduction ranges per 500 m grid cell · used by scenario optimizer
      </p>
    </div>
  );
}
