import { usePalette } from "../ThemeContext.jsx";
import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmt } from "../theme.js";
import ErrorState from "./ErrorState.jsx";
import { PanelSkeleton } from "./LoadingState.jsx";

// Rows shown in the comparison. Values are read from the saved metrics; models the
// backend did not evaluate are listed as such rather than given numbers.
const MODELS = [
  { keys: ["cnn_lstm"], name: "CNN-LSTM", primary: true },
  // { keys: ["lstm_only", "lstm"], name: "LSTM only" },
  // { keys: ["cnn_only", "cnn"], name: "CNN only" },
  { keys: ["baseline_persistence"], name: "Persistence (last month carried forward)" },
  { keys: ["baseline_seasonal_naive"], name: "Seasonal naive (same month last year)" },
];

function Kpi({ label, value, unit, sub }) {
  return (
    <div className="kpi">
      <p className="metric-label">{label}</p>
      <p className="kpi-value">{value}{unit && <span>{unit}</span>}</p>
      {sub && <p className="metric-sub">{sub}</p>}
    </div>
  );
}

export default function ModelMetrics({ metrics, error, onRetry }) {
  const COLORS = usePalette();
  const axis = { fontSize: 11, fill: COLORS.axis };
  const [metric, setMetric] = useState("rmse_m");
  if (error) return <div className="acc-card"><ErrorState onRetry={onRetry} /></div>;
  if (!metrics) return <div className="acc-card"><PanelSkeleton label="Loading model metrics…" /></div>;

  const t = metrics.test_metrics_one_step || {};
  const rows = MODELS.map((m) => {
    const k = m.keys.find((key) => t[key] && t[key].n);
    return { ...m, m: k ? t[k] : null };
  });
  const main = rows[0].m || {};
  const evaluated = rows.filter((r) => r.m);
  const notEvaluated = rows.filter((r) => !r.m).map((r) => r.name);
  const chart = evaluated.map((r) => ({ name: r.name.split(" (")[0], value: r.m[metric], primary: r.primary }));
  const hz = metrics.rollout_metrics_by_horizon || [];
  const sources = [...new Set(hz.map((r) => r.source))];
  const hzData = [...new Set(hz.map((r) => r.horizon))].sort((a, b) => a - b).map((h) => {
    const o = { h };
    sources.forEach((s) => { const r = hz.find((x) => x.horizon === h && x.source === s); if (r) o[s] = r.rmse_m; });
    return o;
  });
  const srcName = (s) => (s === "forecast_holdout" ? "Forecast vs 2026 readings" : s.startsWith("eval_rollout") ? `Rollout through ${s.split("_").pop()}` : s);
  const splits = metrics.metrics_by_split_one_step || {};

  return (
    <div className="acc">
      <div className="acc-intro">
        <h2>Model accuracy</h2>
        <p className="muted">Monthly well readings in {metrics.splits?.test_year}, each predicted one month ahead by
          models that were not trained on that year. Lower error is better.</p>
      </div>

      <div className="kpis">
        <Kpi label="CNN-LSTM MAE" value={fmt(main.mae_m, 2)} unit=" m" sub="average miss" />
        <Kpi label="CNN-LSTM RMSE" value={fmt(main.rmse_m, 2)} unit=" m" sub="typical error" />
        <Kpi label="CNN-LSTM R²" value={fmt(main.r2, 2)} sub="variance explained" />
        <Kpi label="Tested forecast range" value={metrics.validated_horizon_months ?? "—"} unit=" months"
          sub={`${main.n ?? "—"} test readings`} />
      </div>

      <div className="acc-grid">
        <section className="acc-card">
          <h3>Model comparison</h3>
          <div className="table-wrap">
            <table className="acc-table">
              <thead><tr><th>Model</th><th>MAE</th><th>RMSE</th><th>R²</th><th>Readings</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.name} className={r.primary ? "primary" : r.m ? "" : "na"}>
                    <td>{r.name}{r.primary && <i className="tag">Primary</i>}</td>
                    {r.m ? (
                      <><td>{fmt(r.m.mae_m, 2)} m</td><td>{fmt(r.m.rmse_m, 2)} m</td><td>{fmt(r.m.r2, 2)}</td><td>{r.m.n}</td></>
                    ) : <td colSpan={4} className="muted">Not evaluated in this run</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {notEvaluated.length > 0 && (
            <p className="caption">{notEvaluated.join(" and ")} {notEvaluated.length > 1 ? "were" : "was"} not trained
              by the pipeline, so no figures exist for {notEvaluated.length > 1 ? "them" : "it"}.</p>
          )}
        </section>

        <section className="acc-card">
          <div className="card-head">
            <h3>Error by model</h3>
            <div className="seg seg-small" role="radiogroup" aria-label="Error measure">
              {[["rmse_m", "RMSE"], ["mae_m", "MAE"]].map(([k, l]) => (
                <button key={k} role="radio" aria-checked={metric === k} className={metric === k ? "on" : ""}
                  onClick={() => setMetric(k)}>{l}</button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chart} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 0 }}>
              <CartesianGrid stroke={COLORS.grid} horizontal={false} />
              <XAxis type="number" tick={axis} unit=" m" />
              <YAxis type="category" dataKey="name" tick={axis} width={110} />
              <Tooltip formatter={(v) => [`${fmt(v, 3)} m`, metric === "rmse_m" ? "RMSE" : "MAE"]} />
              <Bar dataKey="value" radius={[0, 3, 3, 0]} animationDuration={400}
                shape={(p) => <rect x={p.x} y={p.y} width={p.width} height={p.height} rx={3}
                  fill={p.payload.primary ? COLORS.accent : COLORS.barMuted} />} />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="acc-card">
          <h3>Forecast error by lead time</h3>
          {hzData.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={hzData} margin={{ top: 4, right: 16, left: -4, bottom: 0 }}>
                <CartesianGrid stroke={COLORS.grid} vertical={false} />
                <XAxis dataKey="h" tick={axis} label={{ value: "Months ahead", position: "insideBottom", offset: -2, fontSize: 11, fill: COLORS.axis }} height={36} />
                <YAxis tick={axis} unit=" m" width={50} />
                <Tooltip formatter={(v, n) => [`${fmt(v, 2)} m RMSE`, srcName(n)]} labelFormatter={(h) => `${h} months ahead`} />
                <Legend formatter={srcName} wrapperStyle={{ fontSize: 12 }} />
                {sources.map((s, i) => (
                  <Line key={s} dataKey={s} stroke={i === 0 ? COLORS.accent : COLORS.model} strokeWidth={2} dot={{ r: 2.5 }} animationDuration={400} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : <p className="muted">No multi-month forecast evaluation was saved.</p>}
          <p className="caption">Recursive forecasts compared with real hold-out readings. Forecasts further ahead
            than the tested range are labelled indicative throughout the dashboard.</p>
        </section>

        <section className="acc-card">
          <h3>Fit by data split</h3>
          <div className="table-wrap">
            <table className="acc-table">
              <thead><tr><th>Split</th><th>MAE</th><th>RMSE</th><th>R²</th><th>Readings</th></tr></thead>
              <tbody>
                {["train", "validation", "test"].filter((s) => splits[s]).map((s) => (
                  <tr key={s}><td>{s[0].toUpperCase() + s.slice(1)}</td><td>{fmt(splits[s].mae_m, 2)} m</td>
                    <td>{fmt(splits[s].rmse_m, 2)} m</td><td>{fmt(splits[s].r2, 2)}</td><td>{splits[s].n}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="caption">{metrics.model}. Ensemble of {metrics.ensemble_size} networks.
            Forecast assumption: {metrics.forecast_covariate_scenario}.</p>
        </section>
      </div>
    </div>
  );
}
