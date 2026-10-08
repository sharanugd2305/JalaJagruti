import { useEffect, useState } from "react";
import { api } from "../api.js";
import { usePalette } from "../ThemeContext.jsx";
import {
  BASIS_TEXT, INSUFFICIENT, STATUS_TEXT, bandText, fmt, isNum, riskBand, score100,
} from "../theme.js";
import HistoricalChart from "./HistoricalChart.jsx";
import ForecastChart from "./ForecastChart.jsx";
import ForecastCards from "./ForecastCards.jsx";
import { PanelSkeleton } from "./LoadingState.jsx";
import ErrorState from "./ErrorState.jsx";

function Metric({ label, value, unit, sub, accent }) {
  return (
    <div className="metric" style={accent ? { borderLeftColor: accent } : undefined}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}{unit && <span>{unit}</span>}</p>
      {sub && <p className="metric-sub">{sub}</p>}
    </div>
  );
}

function pickClimate(climate, year) {
  const ys = (climate?.years || []).filter((r) => isNum(r.rain_mm) || isNum(r.temp_c));
  if (!ys.length) return null;
  const exact = ys.find((r) => r.year === year);
  return exact ? { ...exact, exact: true } : { ...ys[ys.length - 1], exact: false };
}

export default function WardDetails({ wardId, year, onYear, onClose }) {
  const COLORS = usePalette();
  const [ward, setWard] = useState(null);
  const [ts, setTs] = useState(null);
  const [climate, setClimate] = useState(null);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setWard(null); setTs(null); setClimate(null); setError(null);
    Promise.all([api.ward(wardId, ctrl), api.timeseries(wardId, ctrl)])
      .then(([w, t]) => { setWard(w); setTs(t); })
      .catch((e) => { if (e.name !== "AbortError") setError(e); });
    // Climate indicators are optional; their absence never blocks the panel.
    api.climate(wardId, ctrl).then(setClimate).catch(() => setClimate({ years: [] }));
    return () => ctrl.abort();
  }, [wardId, attempt]);

  const head = (name) => (
    <div className="panel-head">
      <div>
        <h2>{name || `Ward ${wardId}`}</h2>
        <p className="muted">Ward {wardId}</p>
      </div>
      <button className="close" onClick={onClose} aria-label="Close ward details">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" /></svg>
      </button>
    </div>
  );

  if (error) return <div className="panel-body">{head()}<ErrorState compact onRetry={() => setAttempt((a) => a + 1)} /></div>;
  if (!ward) return <div className="panel-body">{head()}<PanelSkeleton label="Loading ward data…" /></div>;

  const cur = ward.years.find((r) => r.year === year) || {};
  const noData = cur.prediction_status === INSUFFICIENT || cur.depth_m == null;
  const band = riskBand(noData ? null : cur.risk_score);
  const cl = pickClimate(climate, year);
  const ntl = isNum(cur.ntl_log) ? Math.expm1(Number(cur.ntl_log)) : null;

  return (
    <div className="panel-body ward" key={wardId}>
      {head(ward.ward_name)}

      {noData ? (
        <div className="nodata-box">
          <p><strong>Insufficient input data for this ward.</strong></p>
          <p className="muted">{BASIS_TEXT[cur.spatial_basis] || "No usable monitoring data"}
            {isNum(cur.nearest_station_km) && ` (nearest well ${fmt(cur.nearest_station_km)} km away)`}.
            No value is shown for {year}.</p>
        </div>
      ) : (
        <>
          <div className="metrics-grid">
            <Metric label={`Groundwater depth, ${year}`} value={fmt(cur.depth_m)} unit=" m"
              sub={isNum(cur.lower_m) ? `Range ${fmt(cur.lower_m)}–${fmt(cur.upper_m)} m` : null} accent={COLORS.accent} />
            <Metric label="Risk score" value={score100(cur.risk_score) ?? "—"} unit=" / 100" accent={band.color} />
            <div className="metric" style={{ borderLeftColor: band.color }}>
              <p className="metric-label">Risk level</p>
              <p className="metric-value"><i className="badge badge-lg" style={{ background: band.color, color: bandText(band) }}>{band.label}</i></p>
              {isNum(cur.trend_m_per_year) && (
                <p className="metric-sub">{cur.trend_m_per_year > 0 ? "Deepening" : "Rising"} {fmt(Math.abs(cur.trend_m_per_year), 2)} m/yr</p>
              )}
            </div>
            <Metric label="Measured" value={fmt(cur.actual_m)} unit={isNum(cur.actual_m) ? " m" : ""}
              sub={isNum(cur.actual_m) ? (year > 2025 ? "months observed so far" : "annual average") : "No readings for this year"} />
          </div>
          <dl className="facts">
            <div><dt>Prediction status</dt><dd>{STATUS_TEXT[cur.prediction_status]}</dd></div>
            <div><dt>Data basis</dt><dd>{BASIS_TEXT[cur.spatial_basis]}
              {cur.spatial_basis === "INTERPOLATED_IDW" && isNum(cur.nearest_station_km) && ` (nearest ${fmt(cur.nearest_station_km)} km)`}</dd></div>
          </dl>
        </>
      )}

      <section className="block">
        <h3>Environmental indicators</h3>
        <div className="ind-grid">
          <Metric label="NDVI" value={fmt(cur.ndvi, 2)} sub="Vegetation" />
          <Metric label="NDBI" value={fmt(cur.ndbi, 2)} sub="Built-up" />
          <Metric label="Night-time light" value={fmt(ntl, 1)} unit={ntl != null ? " nW/cm²/sr" : ""} sub="VIIRS radiance" />
          <Metric label="Rainfall" value={cl && isNum(cl.rain_mm) ? Math.round(cl.rain_mm) : "—"}
            unit={cl && isNum(cl.rain_mm) ? " mm" : ""} sub={cl ? `${cl.year}, ${cl.months} months` : "Not available"} />
          <Metric label="Temperature" value={cl ? fmt(cl.temp_c, 1) : "—"} unit={cl && isNum(cl.temp_c) ? " °C" : ""}
            sub={cl ? `${cl.year} average` : "Not available"} />
        </div>
        <p className="caption">
          Satellite indicators average the latest four composites{cur.urban_ref_end ? ` up to ${cur.urban_ref_end}` : ""}
          {year > 2025 ? " and are held constant for forecasts" : ""}.
          {cl && !cl.exact ? ` Climate shows ${cl.year}, the latest year with ERA5-Land data; forecasts use long-term monthly averages.` : ""}
        </p>
      </section>

      <section className="block">
        <h3>Past Readings &amp; Model Fit</h3>
        <HistoricalChart history={ts?.history} />
      </section>

      <section className="block">
        <h3>Forecast to 2030</h3>
        <ForecastChart forecast={ts?.forecast} />
        <ForecastCards rows={ward.years} year={year} onYear={onYear} />
      </section>
    </div>
  );
}
