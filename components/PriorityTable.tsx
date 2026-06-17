"use client";

import { useEffect, useState } from "react";
import { fetchPriorities, type PriorityZone } from "@/lib/api";
import { CLASS_LABELS, heatClassColor } from "@/lib/colors";

type Props = {
  city?: string | null;
  bbox?: string | null;
  onSelectZone?: (zoneId: string, lat: number, lon: number) => void;
};

export default function PriorityTable({ city, bbox, onSelectZone }: Props) {
  const [zones, setZones] = useState<PriorityZone[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchPriorities(city ?? undefined, 30, bbox ?? undefined)
      .then((r) => setZones(r.zones))
      .catch(() => setZones([]))
      .finally(() => setLoading(false));
  }, [city, bbox]);

  if (loading) {
    return <div className="p-4 text-sm text-slate-400">Loading priority zones...</div>;
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Neighborhood prioritization</h2>
        <p className="text-xs text-slate-400">
          Heat Risk Index × population exposure proxy · high/critical zones only
        </p>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-800 text-slate-400">
            <tr>
              <th className="px-2 py-2 text-left">#</th>
              <th className="px-2 py-2 text-left">Zone</th>
              <th className="px-2 py-2 text-right">HRI</th>
              <th className="px-2 py-2 text-right">Priority</th>
              <th className="px-2 py-2 text-right">LST</th>
              <th className="px-2 py-2 text-left">Class</th>
            </tr>
          </thead>
          <tbody>
            {zones.map((z, i) => (
              <tr
                key={z.zone_id}
                className="cursor-pointer border-t border-slate-800 hover:bg-slate-800/60"
                onClick={() => onSelectZone?.(z.zone_id, z.latitude, z.longitude)}
              >
                <td className="px-2 py-2 text-slate-500">{i + 1}</td>
                <td className="px-2 py-2 font-mono text-slate-300">{z.zone_id}</td>
                <td className="px-2 py-2 text-right text-orange-300">{z.heat_risk_index}</td>
                <td className="px-2 py-2 text-right font-semibold text-white">{z.priority_score}</td>
                <td className="px-2 py-2 text-right">{z.mean_lst.toFixed(1)}°C</td>
                <td className="px-2 py-2">
                  <span
                    className="rounded px-1.5 py-0.5 text-[10px] font-medium text-slate-900"
                    style={{ background: heatClassColor(z.heat_class) }}
                  >
                    {CLASS_LABELS[z.heat_class] ?? z.heat_class}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
