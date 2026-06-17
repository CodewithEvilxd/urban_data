"use client";

import { useEffect, useRef, useState } from "react";
import { searchAreas, type AreaResult } from "@/lib/api";

type Props = {
  onSelectAreaAction: (area: AreaResult) => void;
};

export default function AreaSearch({ onSelectAreaAction }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AreaResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    debounce.current = setTimeout(async () => {
      setLoading(true);
      try {
        const hits = await searchAreas(query);
        setResults(hits);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [query]);

  const pick = (area: AreaResult) => {
    setQuery(area.name);
    setOpen(false);
    onSelectAreaAction(area);
  };

  return (
    <div className="relative w-full max-w-xs sm:max-w-sm">
      <div className="flex gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Search any city, town or village in India"
          className="w-full rounded-md border border-slate-700 bg-slate-900/95 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-orange-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => results[0] && pick(results[0])}
          disabled={!results.length}
          className="shrink-0 rounded-md bg-orange-600 px-3 py-2 text-xs font-medium text-white hover:bg-orange-500 disabled:opacity-40"
        >
          Go
        </button>
      </div>
      {open && results.length > 0 && (
        <ul className="absolute left-0 right-0 top-full z-[600] mt-1 max-h-56 overflow-y-auto rounded-md border border-slate-700 bg-slate-900 shadow-xl">
          {results.map((area) => (
            <li key={area.name}>
              <button
                type="button"
                onClick={() => pick(area)}
                className="w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
              >
                {area.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {loading && <p className="mt-1 text-[10px] text-slate-500">Searching...</p>}
    </div>
  );
}
