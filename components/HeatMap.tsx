"use client";

import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, GeoJSON, useMap, useMapEvents } from "react-leaflet";
import type { ZoneCollection } from "@/lib/api";
import { heatClassColor } from "@/lib/colors";
import "leaflet/dist/leaflet.css";

type Props = {
  zones: ZoneCollection | null;
  selectedZoneId: string | null;
  simulatedClasses: Record<string, string>;
  viewMode: "current" | "simulated";
  onZoneClick: (zoneId: string) => void;
  flyTarget: { lat: number; lon: number; zoom?: number } | null;
  portfolioZoneIds?: Set<string>;
  onBBoxChange?: (bbox: string, zoom: number) => void;
  initialFit?: boolean;
  indiaView?: boolean;
  onCityOverviewClick?: (slug: string) => void;
  onMapClick?: (lat: number, lon: number) => void;
  mapCenter?: [number, number];
  defaultZoom?: number;
};

function FlyTo({ target }: { target: { lat: number; lon: number; zoom?: number } }) {
  const map = useMap();
  useEffect(() => {
    map.flyTo([target.lat, target.lon], target.zoom ?? 14, { duration: 1.2 });
  }, [target, map]);
  return null;
}

function FitBounds({ zones }: { zones: ZoneCollection }) {
  const map = useMap();
  const done = useRef(false);
  useEffect(() => {
    if (done.current || !zones.features.length) return;
    const lats: number[] = [];
    const lons: number[] = [];
    zones.features.forEach((f) => {
      f.geometry.coordinates[0].forEach(([lon, lat]) => {
        lons.push(lon);
        lats.push(lat);
      });
    });
    map.fitBounds(
      [
        [Math.min(...lats), Math.min(...lons)],
        [Math.max(...lats), Math.max(...lons)],
      ],
      { padding: [20, 20] }
    );
    done.current = true;
  }, [zones, map]);
  return null;
}

function FitIndiaBounds({ active }: { active: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!active) return;
    map.fitBounds(
      [
        [6.5, 68.0],
        [37.5, 97.5],
      ],
      { padding: [24, 24] }
    );
  }, [active, map]);
  return null;
}

function MapClickHandler({ onMapClick }: { onMapClick?: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onMapClick?.(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

function BboxWatcher({ onBBoxChange }: { onBBoxChange: (bbox: string, zoom: number) => void }) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const map = useMapEvents({
    moveend() {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        const b = map.getBounds();
        const west = b.getWest().toFixed(5);
        const south = b.getSouth().toFixed(5);
        const east = b.getEast().toFixed(5);
        const north = b.getNorth().toFixed(5);
        onBBoxChange(`${west},${south},${east},${north}`, map.getZoom());
      }, 400);
    },
  });
  return null;
}

export default function HeatMap({
  zones,
  selectedZoneId,
  simulatedClasses,
  viewMode,
  onZoneClick,
  flyTarget,
  portfolioZoneIds,
  onBBoxChange,
  initialFit = true,
  indiaView = false,
  onCityOverviewClick,
  onMapClick,
  mapCenter = [20.5937, 78.9629],
  defaultZoom = 5,
}: Props) {
  const center = mapCenter;

  const style = useMemo(
    () => (feature: GeoJSON.Feature | undefined) => {
      if (!feature?.properties) return {};
      const props = feature.properties as Record<string, unknown>;
      const zoneId = props.zone_id as string;
      const heatClass =
        viewMode === "simulated" && simulatedClasses[zoneId]
          ? simulatedClasses[zoneId]
          : (feature.properties.heat_class as string);
      const selected = zoneId === selectedZoneId;
      const inPortfolio = portfolioZoneIds?.has(zoneId);
      const isOverview = Boolean(props.overview);
      const isNational = Boolean(props.national);
      return {
        fillColor: heatClassColor(heatClass),
        weight: selected ? 3 : isNational ? 0.25 : isOverview ? 1.5 : inPortfolio ? 2 : 0.5,
        opacity: isNational ? 0.85 : 1,
        color: selected ? "#ffffff" : isNational ? "transparent" : isOverview ? "#f97316" : inPortfolio ? "#34d399" : "#1e293b",
        fillOpacity: selected ? 0.9 : isNational ? 0.62 : isOverview ? 0.72 : inPortfolio ? 0.8 : 0.65,
        dashArray: inPortfolio && !selected ? "4 2" : undefined,
      };
    },
    [selectedZoneId, simulatedClasses, viewMode, portfolioZoneIds]
  );

  return (
    <MapContainer center={center} zoom={defaultZoom} className="h-full w-full" scrollWheelZoom preferCanvas>
      <TileLayer
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      {flyTarget && <FlyTo target={flyTarget} />}
      {onBBoxChange && <BboxWatcher onBBoxChange={onBBoxChange} />}
      {onMapClick && <MapClickHandler onMapClick={onMapClick} />}
      {indiaView && <FitIndiaBounds active={indiaView} />}
      {zones && initialFit && !indiaView && <FitBounds zones={zones} />}
      {zones && (
        <GeoJSON
          key={`${viewMode}-${indiaView ? "india" : "detail"}-${zones.features.length}-${portfolioZoneIds?.size ?? 0}`}
          data={zones}
          style={style}
          onEachFeature={(feature, layer) => {
            const props = feature.properties as Record<string, unknown>;
            const isOverview = Boolean(props.overview);
            const isNational = Boolean(props.national);
            layer.bindTooltip(
              isNational
                ? `<strong>India heat grid</strong><br/>LST: ${(props.mean_lst as number).toFixed(1)}°C · ${props.heat_class}<br/><em>Click for location detail</em>`
                : isOverview
                ? `<strong>${props.name}</strong><br/>LST: ${(props.mean_lst as number).toFixed(1)}°C<br/>${props.zone_count} zones · ${props.critical_count} critical`
                : `<strong>${props.zone_id}</strong><br/>LST: ${(props.mean_lst as number).toFixed(1)}°C<br/>${props.heat_class}`,
              { sticky: true }
            );
            if (!isOverview && !isNational) {
              layer.on("click", () => onZoneClick(props.zone_id as string));
            } else if (isOverview && onCityOverviewClick && props.city) {
              layer.on("click", () => onCityOverviewClick(props.city as string));
            }
          }}
        />
      )}
    </MapContainer>
  );
}
