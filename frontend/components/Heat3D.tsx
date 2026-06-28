"use client";

import { useMemo } from "react";
import DeckGL from "@deck.gl/react";
import { PolygonLayer } from "@deck.gl/layers";
import { Map } from "react-map-gl/maplibre";
import type { ZoneCollection } from "@/lib/api";
import { heatClassColor } from "@/lib/colors";

type Props = {
  zones: ZoneCollection | null;
  selectedZoneId: string | null;
  simulatedClasses: Record<string, string>;
  viewMode: "current" | "simulated";
  onZoneClick: (zoneId: string) => void;
};

function parseRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return [r, g, b];
}

export default function Heat3D({ zones, selectedZoneId, simulatedClasses, viewMode, onZoneClick }: Props) {
  const data = zones?.features ?? [];

  const layer = useMemo(() => {
    return new PolygonLayer({
      id: "heat-extrusion",
      data,
      pickable: true,
      stroked: true,
      filled: true,
      wireframe: false,
      getPolygon: (f: any) => f.geometry.coordinates[0],
      getElevation: (f: any) => {
        const lst = Number(f.properties.mean_lst);
        return Math.max(0, (lst - 30) * 120);
      },
      getFillColor: (f: any) => {
        const zoneId = String(f.properties.zone_id);
        const heatClass =
          viewMode === "simulated" && simulatedClasses[zoneId]
            ? simulatedClasses[zoneId]
            : String(f.properties.heat_class);
        const [r, g, b] = parseRgb(heatClassColor(heatClass));
        const selected = zoneId === selectedZoneId;
        return selected ? [255, 255, 255, 220] : [r, g, b, 190];
      },
      getLineColor: (f: any) => {
        const zoneId = String(f.properties.zone_id);
        return zoneId === selectedZoneId ? [255, 255, 255, 255] : [30, 41, 59, 200];
      },
      lineWidthMinPixels: 1,
      extruded: true,
      onClick: (info: any) => {
        const zoneId = info?.object?.properties?.zone_id;
        if (zoneId) onZoneClick(String(zoneId));
      },
    });
  }, [data, onZoneClick, selectedZoneId, simulatedClasses, viewMode]);

  const initialViewState = {
    longitude: 77.1,
    latitude: 28.64,
    zoom: 10.8,
    pitch: 55,
    bearing: -15,
  };

  return (
    <div className="h-full w-full">
      <DeckGL
        initialViewState={initialViewState as any}
        controller
        layers={[layer]}
        style={{ position: "absolute", inset: "0px" }}
      >
        <Map
          mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
          reuseMaps
        />
      </DeckGL>
    </div>
  );
}

