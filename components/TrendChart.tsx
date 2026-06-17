"use client";

import type { CityStats } from "@/lib/api";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

type Props = {
  stats: CityStats | null;
};

export default function TrendChart({ stats }: Props) {
  if (!stats || stats.trend.length < 2) return null;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/90 p-3">
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
        City mean LST trend
      </h3>
      <div className="h-36 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={stats.trend}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 10 }} />
            <YAxis domain={["auto", "auto"]} tick={{ fill: "#94a3b8", fontSize: 10 }} unit="°C" />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 12 }}
            />
            <Line type="monotone" dataKey="mean_lst" stroke="#f97316" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
