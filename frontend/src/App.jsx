import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import { INSUFFICIENT, RISK_BANDS, riskBand } from "./theme.js";
import Header from "./components/Header.jsx";
import StatisticsCards from "./components/StatisticsCards.jsx";
import MapView, { basemapCredit } from "./components/MapView.jsx";
import RiskLegend from "./components/RiskLegend.jsx";
import WardSearch from "./components/WardSearch.jsx";
import WardDetails from "./components/WardDetails.jsx";
import CityOverview from "./components/CityOverview.jsx";
import ModelMetrics from "./components/ModelMetrics.jsx";
import LoadingState from "./components/LoadingState.jsx";
import ErrorState from "./components/ErrorState.jsx";

export default function App() {
  const [core, setCore] = useState({ status: "loading" });
  const [metrics, setMetrics] = useState({ data: null, error: null });
  const [view, setView] = useState("risk");
  const [year, setYear] = useState(null);
  const [selected, setSelected] = useState(null);
  const [highlightBand, setHighlightBand] = useState(null);
  const panelRef = useRef(null);

  const loadCore = useCallback(() => {
    setCore({ status: "loading" });
    Promise.all([api.years(), api.geojson()])
      .then(([y, g]) => {
        const years = y.years || [];
        if (!years.length || !g?.features?.length) throw new Error("empty");
        setCore({ status: "ready", years, geo: g });
        setYear((cur) => cur ?? (years.includes(2025) ? 2025 : years[0]));
      })
      .catch(() => setCore({ status: "error" }));
  }, []);

  const loadMetrics = useCallback(() => {
    setMetrics({ data: null, error: null });
    api.metrics().then((d) => setMetrics({ data: d, error: null })).catch((e) => setMetrics({ data: null, error: e }));
  }, []);

  useEffect(() => { loadCore(); loadMetrics(); }, [loadCore, loadMetrics]);
  useEffect(() => { if (view !== "risk") setHighlightBand(null); }, [view]);
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") setSelected(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const select = useCallback((id) => {
    setSelected(id);
    if (window.matchMedia("(max-width: 1020px)").matches) {
      requestAnimationFrame(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  }, []);

  const derived = useMemo(() => {
    if (core.status !== "ready" || year == null) return null;
    const props = core.geo.features.map((f) => f.properties);
    const counts = Object.fromEntries([...RISK_BANDS.map((b) => [b.key, 0]), ["nodata", 0]]);
    let observed = 0, available = 0, sum = 0;
    props.forEach((p) => {
      const d = p[`depth_m_${year}`];
      const ok = d != null && p[`prediction_status_${year}`] !== INSUFFICIENT;
      if (p[`actual_m_${year}`] != null) observed += 1;
      if (ok) { available += 1; sum += d; }
      counts[riskBand(ok ? p[`risk_score_${year}`] : null).key] += 1;
    });
    return {
      counts,
      stats: { total: props.length, observed, available, highCrit: counts.high + counts.critical,
        avgDepth: available ? sum / available : null },
      wardOptions: props.map((p) => ({ id: String(p.ward_id), name: p.ward_name }))
        .sort((a, b) => Number(a.id) - Number(b.id)),
    };
  }, [core, year]);

  if (core.status === "loading") return <LoadingState />;
  if (core.status === "error") {
    return (
      <div className="app">
        <Header years={[]} year={null} onYear={() => {}} view="depth" onView={() => {}} />
        <main className="center-state"><ErrorState onRetry={loadCore} /></main>
      </div>
    );
  }

  return (
    <div className="app">
      <Header years={core.years} year={year} onYear={setYear} view={view} onView={setView} />
      {view === "accuracy" ? (
        <main className="accuracy-view">
          <ModelMetrics metrics={metrics.data} error={metrics.error} onRetry={loadMetrics} />
        </main>
      ) : (
        <>
          <StatisticsCards stats={derived.stats} year={year} />
          <main className="layout">
            <div className="map-col">
              <div className="map-head">
                <h2>{view === "risk" ? "Groundwater depletion risk" : "Groundwater depth"}, {year}</h2>
                <WardSearch options={derived.wardOptions} value={selected} onSelect={select} />
              </div>
              <div className="map-section">
                <div className="map-container">
                  <section className="map-wrap" aria-label="Bengaluru ward map">
                    <MapView geo={core.geo} year={year} view={view} selectedId={selected}
                      highlightBand={view === "risk" ? highlightBand : null} onSelect={select} />
                  </section>
                  {basemapCredit && <p className="map-credit">Basemap: {basemapCredit}</p>}
                </div>
                <aside className="legend-side">
                  <RiskLegend view={view} year={year} counts={derived.counts}
                    highlightBand={highlightBand} onHighlight={setHighlightBand} />
                </aside>
              </div>
            </div>
            <aside className={`panel ${selected ? "has-ward" : ""}`} ref={panelRef}>
              {selected ? (
                <WardDetails wardId={selected} year={year} onYear={setYear} onClose={() => setSelected(null)} />
              ) : (
                <CityOverview view={view} year={year} geo={core.geo} years={core.years} counts={derived.counts}
                  highlightBand={highlightBand} onHighlight={setHighlightBand} onSelect={select} />
              )}
            </aside>
          </main>
        </>
      )}
    </div>
  );
}
