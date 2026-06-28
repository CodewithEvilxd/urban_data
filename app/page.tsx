"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import Sidebar, { type NavSection } from "@/components/Sidebar";
import StatsBar from "@/components/StatsBar";
import ZonePanel from "@/components/ZonePanel";
import AreaSearch from "@/components/AreaSearch";
import CitySelector from "@/components/CitySelector";
import LiveTracker from "@/components/LiveTracker";
import InsightsPanel from "@/components/InsightsPanel";
import StrategyChart from "@/components/StrategyChart";
import MaterialTable from "@/components/MaterialTable";
import PriorityTable from "@/components/PriorityTable";
import {
  fetchStats,
  fetchZoneDetail,
  fetchZoneEstimate,
  fetchZoneNearAny,
  fetchZones,
  fetchZonesByBbox,
  fetchCities,
  reverseGeocode,
  simulateZone,
  type AreaResult,
  type CityStats,
  type IndiaCity,
  type ReverseGeocode,
  type ZoneCollection,
  type ZoneDetail,
} from "@/lib/api";

const HeatMap = dynamic(() => import("@/components/HeatMap"), { ssr: false });
const Heat3D = dynamic(() => import("@/components/Heat3D"), { ssr: false });

const INDIA_CENTER: [number, number] = [20.5937, 78.9629];
const DETAIL_ZOOM = 9;

export default function Dashboard() {
  const [section, setSection] = useState<NavSection>("map");
  const [activeCity, setActiveCity] = useState<IndiaCity | null>(null);
  const [zones, setZones] = useState<ZoneCollection | null>(null);
  const [stats, setStats] = useState<CityStats | null>(null);
  const [currentBbox, setCurrentBbox] = useState<string | null>(null);
  const [selectedZone, setSelectedZone] = useState<ZoneDetail | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoneLocation, setZoneLocation] = useState<ReverseGeocode | null>(null);
  const [loadingZone, setLoadingZone] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [simulatedClasses, setSimulatedClasses] = useState<Record<string, string>>({});
  const [viewMode, setViewMode] = useState<"current" | "simulated">("current");
  const [view3d, setView3d] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flyTarget, setFlyTarget] = useState<{ lat: number; lon: number; zoom?: number } | null>(
    null
  );
  const [portfolioIds, setPortfolioIds] = useState<string[]>([]);
  const [locating, setLocating] = useState(false);
  const [mapZoom, setMapZoom] = useState(5);
  const [initialFit, setInitialFit] = useState(false);
  const [cityRegistry, setCityRegistry] = useState<IndiaCity[]>([]);

  const portfolioSet = useMemo(() => new Set(portfolioIds), [portfolioIds]);
  const statsCity = activeCity?.slug ?? "india";

  const loadViewport = useCallback(
    async (bbox: string, city?: IndiaCity | null, fullCity = false) => {
      setCurrentBbox(bbox);
      const citySlug = city?.has_data ? city.slug : undefined;
      try {
        const z =
          fullCity && citySlug
            ? await fetchZones(citySlug)
            : await fetchZonesByBbox(bbox, citySlug);
        if (z.features.length > 0) setZones(z);
        const s = await fetchStats(city?.slug ?? "viewport", bbox);
        setStats(s);
        setError(null);
      } catch {
        if (!city?.has_data) {
          setError(
            "No heat data in this view. Zoom into a city with data or select one from the dropdown."
          );
        }
      }
    },
    []
  );

  const refreshStats = useCallback(() => {
    if (currentBbox) {
      fetchStats(statsCity, currentBbox).then(setStats).catch(() => {});
    } else if (activeCity?.has_data) {
      const bbox = activeCity.bbox.join(",");
      fetchStats(activeCity.slug, bbox).then(setStats).catch(() => {});
    }
  }, [activeCity, currentBbox, statsCity]);

  const handleCitySelect = useCallback(
    (city: IndiaCity) => {
      setActiveCity(city);
      setInitialFit(true);
      setMapZoom(11);
      setFlyTarget({ lat: city.lat, lon: city.lon, zoom: 11 });
      const bbox = city.bbox.join(",");
      loadViewport(bbox, city, true);
    },
    [loadViewport]
  );

  const handleCityOverviewClick = useCallback(
    (slug: string) => {
      const city = cityRegistry.find((c) => c.slug === slug);
      if (city) handleCitySelect(city);
    },
    [cityRegistry, handleCitySelect]
  );

  useEffect(() => {
    fetchCities()
      .then((r) => {
        setCityRegistry(r.cities);
        if (!activeCity && r.cities.length > 0) {
          handleCitySelect(r.cities[0]);
        }
      })
      .catch(() => {});
  }, [activeCity, handleCitySelect]);

  const handleBBoxChange = useCallback(
    (bbox: string, zoom: number) => {
      setMapZoom(zoom);
      if (!activeCity && zoom < DETAIL_ZOOM) {
        return;
      }
      loadViewport(bbox, activeCity);
    },
    [activeCity, loadViewport]
  );


  const openZone = useCallback(async (zoneId: string, lat?: number, lon?: number) => {
    setSelectedId(zoneId);
    setLoadingZone(true);
    setSection("map");
    try {
      const detail = await fetchZoneDetail(zoneId);
      setSelectedZone(detail);
      const la = lat ?? detail.latitude;
      const lo = lon ?? detail.longitude;
      const geo = await reverseGeocode(la, lo).catch(() => null);
      setZoneLocation(geo);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load zone");
    } finally {
      setLoadingZone(false);
    }
  }, []);

  const handleSimulate = async (ndviIncrease: number) => {
    if (!selectedId) return;
    setSimulating(true);
    try {
      const result = await simulateZone(selectedId, ndviIncrease);
      setSimulatedClasses((prev) => ({ ...prev, [selectedId]: result.predicted_class }));
      setViewMode("simulated");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setSimulating(false);
    }
  };

  const handleMapClick = useCallback(
    async (lat: number, lon: number) => {
      setSection("map");
      setSelectedId(null);
      setLoadingZone(true);
      setError(null);
      try {
        const detail = await fetchZoneEstimate(lat, lon);
        setSelectedZone(detail);
        setSelectedId(detail.zone_id);
        const geo = await reverseGeocode(lat, lon).catch(() => null);
        setZoneLocation(geo);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not estimate heat for this location");
      } finally {
        setLoadingZone(false);
      }
    },
    []
  );

  const flyToPoint = useCallback(
    async (lat: number, lon: number, zoom = 14) => {
      setFlyTarget({ lat, lon, zoom });
      setMapZoom(zoom);
      setError(null);
      setSelectedZone(null);
      setSelectedId(null);
      setZoneLocation(null);
      setLoadingZone(true);
      try {
        const near = await fetchZoneNearAny(lat, lon);
        await openZone(near.zone_id, lat, lon);
      } catch {
        try {
          const detail = await fetchZoneEstimate(lat, lon);
          setSelectedZone(detail);
          setSelectedId(detail.zone_id);
          const geo = await reverseGeocode(lat, lon).catch(() => null);
          setZoneLocation(geo);
        } catch {
          setError("Could not load heat data for this location.");
        } finally {
          setLoadingZone(false);
        }
      }
    },
    [openZone]
  );

  const handleAreaSelect = useCallback(
    async (area: AreaResult) => {
      await flyToPoint(area.lat, area.lon);
    },
    [flyToPoint]
  );

  const handleMyLocation = () => {
    if (!navigator.geolocation) {
      setError("Geolocation not supported");
      return;
    }
    setLocating(true);

    let best: GeolocationPosition | null = null;
    let watchId: number | null = null;
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      if (watchId !== null) navigator.geolocation.clearWatch(watchId);
      setLocating(false);

      if (!best) {
        setError("Could not get your location. Allow precise GPS permission and try again.");
        return;
      }

      const { latitude, longitude, accuracy } = best.coords;
      if (!accuracy || accuracy > 1500) {
        setError(
          `Location accuracy is too low (${accuracy ? Math.round(accuracy) : "unknown"} m). Turn on precise GPS/location services and try again.`
        );
        return;
      }
      flyToPoint(latitude, longitude, 15);
    };

    watchId = navigator.geolocation.watchPosition(
      (pos) => {
        if (!best || pos.coords.accuracy < best.coords.accuracy) {
          best = pos;
        }
        if (pos.coords.accuracy <= 150) {
          finish();
        }
      },
      () => finish(),
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
    );
    window.setTimeout(finish, 8000);
  };

  return (
    <div className="flex h-screen flex-col bg-slate-950">
      <StatsBar stats={stats} />
      <div className="flex min-h-0 flex-1">
        <Sidebar active={section} onChange={setSection} />

        <main className="flex min-w-0 flex-1 flex-col">
          {section === "map" && (
            <>
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 px-3 py-2">
                <LiveTracker
                  city={activeCity?.has_data ? activeCity.slug : statsCity}
                  bbox={currentBbox}
                  onRefresh={refreshStats}
                />
                <CitySelector value={activeCity?.slug ?? null} onSelectAction={handleCitySelect} />
                <AreaSearch onSelectAreaAction={handleAreaSelect} />
                <button
                  type="button"
                  onClick={handleMyLocation}
                  disabled={locating}
                  className="rounded-md bg-indigo-700 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-600 disabled:opacity-50"
                >
                  {locating ? "Locating..." : "Find my location"}
                </button>
                <div className="flex gap-2">
                  <button
                    onClick={() => setView3d((v) => !v)}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                      view3d ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    {view3d ? "3D" : "2D"}
                  </button>
                  <button
                    onClick={() => setViewMode("current")}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                      viewMode === "current" ? "bg-orange-600 text-white" : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    Current
                  </button>
                  <button
                    onClick={() => setViewMode("simulated")}
                    disabled={Object.keys(simulatedClasses).length === 0}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium disabled:opacity-40 ${
                      viewMode === "simulated" ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    Simulated
                  </button>
                </div>
              </div>
              <div className="relative min-h-0 flex-1">
                {error && (
                  <div className="absolute bottom-3 left-3 z-[500] max-w-md rounded-md bg-red-900/90 px-3 py-2 text-xs text-red-100">
                    {error}
                  </div>
                )}
                {portfolioIds.length > 0 && (
                  <div className="absolute right-3 top-3 z-[500] rounded-md bg-emerald-900/80 px-3 py-1.5 text-[10px] text-emerald-100">
                    {portfolioIds.length} zones in cooling portfolio
                  </div>
                )}
                {view3d ? (
                  <Heat3D
                    zones={zones}
                    selectedZoneId={selectedId}
                    simulatedClasses={simulatedClasses}
                    viewMode={viewMode}
                    onZoneClick={openZone}
                  />
                ) : (
                  <HeatMap
                    zones={zones}
                    selectedZoneId={selectedId}
                    simulatedClasses={simulatedClasses}
                    viewMode={viewMode}
                    onZoneClickAction={openZone}
                    flyTarget={flyTarget}
                    portfolioZoneIds={portfolioSet}
                    onBBoxChangeAction={handleBBoxChange}
                    initialFit={initialFit}
                    onCityOverviewClickAction={handleCityOverviewClick}
                    onMapClickAction={handleMapClick}
                    mapCenter={activeCity ? [activeCity.lat, activeCity.lon] : INDIA_CENTER}
                    defaultZoom={mapZoom}
                  />
                )}
              </div>
            </>
          )}

          {section === "insights" && <InsightsPanel stats={stats} />}

          {section === "portfolio" && (
            <div className="flex h-full flex-col gap-0 overflow-hidden lg:flex-row">
              <div className="min-h-0 flex-1 overflow-y-auto lg:w-3/5">
                <StrategyChart
                  city={activeCity?.slug ?? "delhi"}
                  bbox={currentBbox}
                  onPortfolioChangeAction={setPortfolioIds}
                />
              </div>
              <div className="border-t border-slate-800 p-4 lg:w-2/5 lg:border-l lg:border-t-0">
                <h3 className="mb-3 text-sm font-medium text-white">Material performance</h3>
                <MaterialTable />
              </div>
            </div>
          )}

          {section === "priorities" && (
            <PriorityTable
              city={activeCity?.has_data ? activeCity.slug : null}
              bbox={currentBbox}
              onSelectZone={(id, lat, lon) => {
                setFlyTarget({ lat, lon, zoom: 15 });
                openZone(id, lat, lon);
              }}
            />
          )}
        </main>
      </div>

      <ZonePanel
        zone={selectedZone}
        loading={loadingZone}
        simulating={simulating}
        simulatedClass={selectedId ? simulatedClasses[selectedId] ?? null : null}
        onSimulateAction={handleSimulate}
        onCloseAction={() => {
          setSelectedZone(null);
          setSelectedId(null);
          setZoneLocation(null);
        }}
        stats={stats}
        location={zoneLocation}
      />
    </div>
  );
}
