"use client";

import { useEffect, useState } from "react";
import { fetchLiveStatus, fetchStats, type LiveStatus } from "@/lib/api";

type Props = {
  city?: string | null;
  bbox?: string | null;
  onRefresh?: () => void;
};

export default function LiveTracker({ city, bbox, onRefresh }: Props) {
  const [live, setLive] = useState<LiveStatus | null>(null);
  const [pulse, setPulse] = useState(true);
  const [noData, setNoData] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const params = new URLSearchParams();
        if (bbox) params.set("bbox", bbox);
        else if (city) params.set("city", city);
        else params.set("city", "delhi");

        const data = await fetchLiveStatus(params.get("city") ?? "delhi", bbox ?? undefined);
        if (data.status === "no_data") {
          setNoData(true);
          setLive(data);
          return;
        }
        setNoData(false);
        setLive(data);
      } catch {
        try {
          const stats = await fetchStats(city ?? "delhi", bbox ?? undefined);
          setNoData(false);
          setLive({
            status: "live",
            city: stats.city,
            scene_id: stats.scene_id,
            scene_date: stats.scene_date,
            mean_lst: stats.mean_lst,
            critical_count: stats.critical_count,
            zone_count: stats.zone_count ?? 0,
            data_source: stats.live?.data_source ?? "Landsat 8/9",
            pipeline: stats.live?.pipeline ?? "",
            last_refresh: stats.live?.last_refresh ?? new Date().toISOString(),
          });
        } catch {
          setLive(null);
        }
      }
    };

    load();
    const id = setInterval(() => {
      load();
      onRefresh?.();
    }, 60_000);
    const blink = setInterval(() => setPulse((p) => !p), 1200);
    return () => {
      clearInterval(id);
      clearInterval(blink);
    };
  }, [city, bbox, onRefresh]);

  if (!live) return null;

  if (noData) {
    return (
      <div className="rounded-lg border border-amber-900/50 bg-amber-950/40 px-3 py-1.5 text-[10px] text-amber-200">
        No heat data available yet. Select a processed city or run the data pipeline for this region.
      </div>
    );
  }

  const refreshed = new Date(live.last_refresh).toLocaleTimeString();

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-emerald-900/50 bg-emerald-950/40 px-3 py-1.5 text-[10px] text-emerald-200">
      <span className="inline-flex h-2.5 w-2.5 items-center justify-center rounded-full bg-emerald-400" />
      <span className="font-medium uppercase tracking-wider">Current data</span>
      <span className="text-emerald-400/80">|</span>
      <span>{live.city}</span>
      <span className="text-emerald-400/80">|</span>
      <span>{live.zone_count.toLocaleString()} zones</span>
      <span className="text-emerald-400/80">|</span>
      <span>LST {live.mean_lst}°C</span>
      <span className="hidden text-emerald-400/60 sm:inline">· {refreshed}</span>
    </div>
  );
}
