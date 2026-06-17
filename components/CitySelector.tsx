"use client";

import { useEffect, useState } from "react";
import { fetchCities, type IndiaCity } from "@/lib/api";

type Props = {
  value: string | null;
  onSelectAction: (city: IndiaCity) => void;
  onIndiaSelectAction: () => void;
};

export default function CitySelector({ value, onSelectAction, onIndiaSelectAction }: Props) {
  const [cities, setCities] = useState<IndiaCity[]>([]);

  useEffect(() => {
    fetchCities().then((r) => setCities(r.cities)).catch(() => {});
  }, []);

  return (
    <select
      value={value ?? ""}
      onChange={(e) => {
        const slug = e.target.value;
        if (!slug) {
          onIndiaSelectAction();
          return;
        }
        const city = cities.find((c) => c.slug === slug);
        if (city) onSelectAction(city);
      }}
      className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-xs text-white focus:border-orange-500 focus:outline-none"
    >
      <option value="">All India (pan map)</option>
      {cities.map((c) => (
        <option key={c.slug} value={c.slug}>
          {c.name} {c.has_data ? "(data available)" : "(no data)"}
        </option>
      ))}
    </select>
  );
}
