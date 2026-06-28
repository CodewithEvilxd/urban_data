"use client";

import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, GeoJSON, useMap, useMapEvents } from "react-leaflet";
import { reverseGeocode, type ReverseGeocode, type ZoneCollection } from "@/lib/api";
import { heatClassColor } from "@/lib/colors";
import "leaflet/dist/leaflet.css";

type Props = {
  zones: ZoneCollection | null;
  selectedZoneId: string | null;
  simulatedClasses: Record<string, string>;
  viewMode: "current" | "simulated";
  onZoneClickAction: (zoneId: string) => void;
  flyTarget: { lat: number; lon: number; zoom?: number } | null;
  portfolioZoneIds?: Set<string>;
  onBBoxChangeAction?: (bbox: string, zoom: number) => void;
  initialFit?: boolean;
  indiaView?: boolean;
  onCityOverviewClickAction?: (slug: string) => void;
  onMapClickAction?: (lat: number, lon: number) => void;
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

function MapClickHandler({ onMapClickAction }: { onMapClickAction?: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onMapClickAction?.(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

function BboxWatcher({ onBBoxChangeAction }: { onBBoxChangeAction: (bbox: string, zoom: number) => void }) {
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
        onBBoxChangeAction(`${west},${south},${east},${north}`, map.getZoom());
      }, 400);
    },
  });
  return null;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function placeFromReverse(geo: ReverseGeocode): string | null {
  return (
    geo.place_name ||
    geo.suburb ||
    geo.village ||
    geo.town ||
    geo.city ||
    geo.county ||
    geo.road ||
    geo.display_name ||
    null
  );
}

function formatDistance(distance: unknown): string {
  if (typeof distance !== "number" || distance <= 0) return "";
  if (distance < 1000) return `${Math.round(distance)} m away`;
  return `${(distance / 1000).toFixed(1)} km away`;
}

function zoneTooltip(props: Record<string, unknown>, resolvedPlace?: string | null, loading = false): string {
  const title = resolvedPlace || (props.place_name as string | undefined) || (props.zone_id as string);
  const locationLine =
    loading
      ? "Resolving exact place..."
      : [props.place_state as string | undefined, formatDistance(props.place_distance_m)]
          .filter(Boolean)
          .join(" - ") || "Mapped heat zone";
  const lst = Number(props.mean_lst);
  const lstLabel = Number.isFinite(lst) ? lst.toFixed(1) : "-";

  return `<strong>${escapeHtml(title)}</strong><br/>${escapeHtml(locationLine)}<br/>Zone: ${escapeHtml(
    props.zone_id
  )}<br/>LST: ${escapeHtml(lstLabel)} C - ${escapeHtml(props.heat_class)}`;
}

function overviewTooltip(props: Record<string, unknown>): string {
  const lst = Number(props.mean_lst);
  const lstLabel = Number.isFinite(lst) ? lst.toFixed(1) : "-";
  return `<strong>${escapeHtml(props.name)}</strong><br/>LST: ${escapeHtml(lstLabel)} C<br/>${escapeHtml(
    props.zone_count
  )} zones - ${escapeHtml(props.critical_count)} critical`;
}

function nationalTooltip(props: Record<string, unknown>): string {
  const lst = Number(props.mean_lst);
  const lstLabel = Number.isFinite(lst) ? lst.toFixed(1) : "-";
  return `<strong>India heat grid</strong><br/>LST: ${escapeHtml(lstLabel)} C - ${escapeHtml(
    props.heat_class
  )}<br/><em>Click for location detail</em>`;
}

export default function HeatMap({
  zones,
  selectedZoneId,
  simulatedClasses,
  viewMode,
  onZoneClickAction,
  flyTarget,
  portfolioZoneIds,
  onBBoxChangeAction,
  initialFit = true,
  indiaView = false,
  onCityOverviewClickAction,
  onMapClickAction,
  mapCenter = [20.5937, 78.9629],
  defaultZoom = 5,
}: Props) {
  const center = mapCenter;
  const reverseCache = useRef<Map<string, string | null>>(new Map());

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
        color: selected
          ? "#ffffff"
          : isNational
          ? "transparent"
          : isOverview
          ? "#f97316"
          : inPortfolio
          ? "#34d399"
          : "#1e293b",
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
      {onBBoxChangeAction && <BboxWatcher onBBoxChangeAction={onBBoxChangeAction} />}
      {onMapClickAction && <MapClickHandler onMapClickAction={onMapClickAction} />}
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
            layer.bindTooltip(isNational ? nationalTooltip(props) : isOverview ? overviewTooltip(props) : zoneTooltip(props), {
              sticky: true,
            });

            if (!isOverview && !isNational) {
              layer.on("mouseover", () => {
                const lat = Number(props.latitude);
                const lon = Number(props.longitude);
                if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

                const zoneId = String(props.zone_id ?? `${lat.toFixed(5)},${lon.toFixed(5)}`);
                const cacheKey = `${zoneId}:${lat.toFixed(5)},${lon.toFixed(5)}`;
                const leafletLayer = layer as typeof layer & {
                  setTooltipContent?: (content: string) => void;
                };

                if (reverseCache.current.has(cacheKey)) {
                  leafletLayer.setTooltipContent?.(zoneTooltip(props, reverseCache.current.get(cacheKey)));
                  return;
                }

                leafletLayer.setTooltipContent?.(zoneTooltip(props, null, true));
                reverseGeocode(lat, lon)
                  .then((geo) => {
                    const resolved = placeFromReverse(geo);
                    reverseCache.current.set(cacheKey, resolved);
                    leafletLayer.setTooltipContent?.(zoneTooltip(props, resolved));
                  })
                  .catch(() => {
                    reverseCache.current.set(cacheKey, null);
                    leafletLayer.setTooltipContent?.(zoneTooltip(props));
                  });
              });
              layer.on("click", () => onZoneClickAction(props.zone_id as string));
            } else if (isOverview && onCityOverviewClickAction && props.city) {
              layer.on("click", () => onCityOverviewClickAction(props.city as string));
            }
          }}
        />
      )}
    </MapContainer>
  );
}
