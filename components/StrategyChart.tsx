"use client";

import { useCallback, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { optimizeScenario, type OptimizeResult } from "@/lib/api";

type Props = {
  city: string;
  bbox?: string | null;
  onPortfolioChangeAction?: (zoneIds: string[]) => void;
};

const OBJECTIVES = [
  { id: "max_cooling", label: "Max cooling" },
  { id: "max_people_protected", label: "Max people protected" },
  { id: "max_cooling_per_crore", label: "Best ROI (₹/°C)" },
];

export default function StrategyChart({ city, bbox, onPortfolioChangeAction }: Props) {
  const [budget, setBudget] = useState(25);
  const [objective, setObjective] = useState("max_cooling");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runOptimize = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await optimizeScenario(city, budget, objective, 40, bbox ?? undefined);
      setResult(res);
      onPortfolioChangeAction?.(res.portfolio.map((p) => p.zone_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Optimization failed");
    } finally {
      setLoading(false);
    }
  }, [city, budget, objective, bbox, onPortfolioChangeAction]);

  const chartData =
    result?.portfolio.slice(0, 12).map((p) => ({
      name: p.zone_id.replace("delhi_", ""),
      cooling: (p.estimated_lst_reduction_c.min + p.estimated_lst_reduction_c.max) / 2,
      cost: p.cost_crore,
      strategy: p.strategy_label.split(" ")[0],
    })) ?? [];

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Scenario Optimizer</h2>
        <p className="text-xs text-slate-400">
          Budget-aware cooling portfolio with model-backed validation
        </p>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4 space-y-4">
        <div>
          <label className="mb-1 block text-[10px] uppercase text-slate-500">
            Budget (₹ crore) — {budget}
          </label>
          <input
            type="range"
            min={5}
            max={100}
            step={5}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
            className="w-full accent-orange-500"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {OBJECTIVES.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => setObjective(o.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                objective === o.id
                  ? "bg-orange-600 text-white"
                  : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={runOptimize}
          disabled={loading}
          className="w-full rounded-md bg-emerald-700 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
        >
          {loading ? "Optimizing..." : "Generate cooling portfolio"}
        </button>
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>

      {result && (
        <>
          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded-lg bg-slate-800/80 p-2">
              <div className="text-slate-500">Selected</div>
              <div className="text-lg font-semibold text-white">{result.selected_zones}</div>
            </div>
            <div className="rounded-lg bg-slate-800/80 p-2">
              <div className="text-slate-500">Spent</div>
              <div className="text-lg font-semibold text-orange-300">₹{result.spent_crore} Cr</div>
            </div>
            <div className="rounded-lg bg-slate-800/80 p-2">
              <div className="text-slate-500">Budget</div>
              <div className="text-lg font-semibold text-white">₹{result.budget_crore} Cr</div>
            </div>
          </div>

          {chartData.length > 0 && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
              <h3 className="mb-2 text-xs font-medium uppercase text-slate-400">
                Cooling potential by zone (°C)
              </h3>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ bottom: 40 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: "#94a3b8", fontSize: 9 }}
                      angle={-35}
                      textAnchor="end"
                      height={50}
                    />
                    <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{ background: "#1e293b", border: "1px solid #334155" }}
                      formatter={(v: number, name: string) => [
                        name === "cooling" ? `${v.toFixed(1)}°C` : `₹${v.toFixed(3)} Cr`,
                        name === "cooling" ? "Est. cooling" : "Cost",
                      ]}
                    />
                    <Bar dataKey="cooling" fill="#f97316" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-800 text-xs">
            <table className="w-full">
              <thead className="sticky top-0 bg-slate-800 text-slate-400">
                <tr>
                  <th className="px-2 py-1.5 text-left">Zone</th>
                  <th className="px-2 py-1.5 text-left">Strategy</th>
                  <th className="px-2 py-1.5 text-right">°C</th>
                </tr>
              </thead>
              <tbody>
                {result.portfolio.map((p) => (
                  <tr key={`${p.zone_id}-${p.strategy}`} className="border-t border-slate-800">
                    <td className="px-2 py-1 font-mono text-slate-300">{p.zone_id}</td>
                    <td className="px-2 py-1 text-slate-400">{p.strategy_label}</td>
                    <td className="px-2 py-1 text-right text-orange-300">
                      {p.estimated_lst_reduction_c.min}–{p.estimated_lst_reduction_c.max}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
