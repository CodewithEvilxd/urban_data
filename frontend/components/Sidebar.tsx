"use client";

import { IconMap, IconInsights, IconPortfolio, IconPriority } from "./Icons";
import type { ReactNode } from "react";

export type NavSection = "map" | "insights" | "portfolio" | "priorities";

type Props = {
  active: NavSection;
  onChange: (section: NavSection) => void;
};

const ITEMS: { id: NavSection; label: string; icon: ReactNode }[] = [
  { id: "map", label: "Heat Map", icon: <IconMap /> },
  { id: "insights", label: "Insights", icon: <IconInsights /> },
  { id: "portfolio", label: "Portfolio", icon: <IconPortfolio /> },
  { id: "priorities", label: "Priority Zones", icon: <IconPriority /> },
];

export default function Sidebar({ active, onChange }: Props) {
  return (
    <nav className="flex w-14 shrink-0 flex-col items-center gap-1 border-r border-slate-800 bg-slate-900 py-4 md:w-52 md:items-stretch md:px-3">
      <div className="mb-4 hidden px-2 md:block">
        <div className="text-sm font-bold text-orange-400">UrbanCool</div>
        <div className="text-[10px] text-slate-500">BAH 2026 · PS-01</div>
      </div>
      {ITEMS.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onChange(item.id)}
          className={`group flex items-center gap-3 rounded-lg px-3 py-3 text-left transition md:px-4 ${
            active === item.id
              ? "bg-orange-600/20 text-orange-300 ring-1 ring-orange-500/40"
              : "text-slate-400 hover:bg-slate-800 hover:text-white"
          }`}
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-slate-900/80 text-slate-200 transition group-hover:bg-slate-800">
            {item.icon}
          </span>
          <span className="hidden text-sm font-medium md:inline">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
