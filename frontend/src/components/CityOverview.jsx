import { usePalette } from "../ThemeContext.jsx";
import {
  Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { bandText, fmt, riskBand, score100 } from "../theme.js";
import { BAND_BY_KEY } from "../riskColors.js";


export default function CityOverview({ view, year, geo, years, counts, highlightBand, onHighlight, onSelect }) {
  const COLORS = usePalette();
  const axis = { fontSize: 11, fill: COLORS.axis };
  const feats = geo.features.map((f) => f.properties);
  const series = years.map((y) => {
    const vals = feats.map((p) => p[`depth_m_${y}`]).filter((v) => v != null);
    const lo = feats.map((p) => p[`lower_m_${y}`]).filter((v) => v != null);
    const hi = feats.map((p) => p[`upper_m_${y}`]).filter((v) => v != null);
    const act = feats.map((p) => p[`actual_m_${y}`]).filter((v) => v != null);
    const mean = (a) => (a.length ? a.reduce((s, v) => s + v, 0) / a.length : null);
    const hc = feats.filter((p) => ["high", "critical"].includes(riskBand(p[`depth_m_${y}`] == null ? null : p[`risk_score_${y}`]).key)).length;
    return { year: String(y), depth: mean(vals), band: lo.length ? [mean(lo), mean(hi)] : null, actual: mean(act), hc };
  });
  const ranked = feats
    .filter((p) => p[`depth_m_${year}`] != null)
    .sort((a, b) => view === "risk"
      ? (b[`risk_score_${year}`] ?? -1) - (a[`risk_score_${year}`] ?? -1)
      : b[`depth_m_${year}`] - a[`depth_m_${year}`])
    .slice(0, 6);

  return (
    <div className="panel-body">
      <h2 className="panel-title">{view === "risk" ? `Risk overview, ${year}` : `Depth overview, ${year}`}</h2>

      <section className="block">
        <h3>{view === "risk" ? "High and critical wards by year" : "Average depth by year"}</h3>
        <ResponsiveContainer width="100%" height={190}>
          <ComposedChart data={series} margin={{ top: 8, right: 10, left: -6, bottom: 0 }}>
            <CartesianGrid stroke={COLORS.grid} vertical={false} />
            <XAxis dataKey="year" tick={axis} />
            {view === "risk" ? (
              <>
                <YAxis tick={axis} allowDecimals={false} width={34} />
                <Tooltip formatter={(v) => [`${v} wards`, "High + critical"]} />
                <Line dataKey="hc" stroke={BAND_BY_KEY.high.color} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
              </>
            ) : (
              <>
                <YAxis reversed tick={axis} unit=" m" width={46} domain={["auto", "auto"]} />
                <Tooltip formatter={(v, n) => Array.isArray(v) ? [`${fmt(v[0])}–${fmt(v[1])} m`, n] : [`${fmt(v)} m`, n]} />
                <Area dataKey="band" name="Uncertainty range" fill={COLORS.band} fillOpacity={0.3} stroke="none" isAnimationActive={false} />
                <Line dataKey="depth" name="Model average" stroke={COLORS.model} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
                <Line dataKey="actual" name="Measured average" stroke={COLORS.measured} strokeWidth={0} dot={{ r: 3.5 }} isAnimationActive={false} />
              </>
            )}
          </ComposedChart>
        </ResponsiveContainer>
        <p className="caption">
          {view === "risk"
            ? "Counts wards whose risk score falls in the High or Critical band."
            : "Average over wards with data. Depth axis points down: greater depth means deeper groundwater."}
        </p>
      </section>

      <section className="block">
        <h3>{view === "risk" ? `Highest risk wards, ${year}` : `Deepest groundwater, ${year}`}</h3>
        {ranked.length ? (
          <ol className="rank">
            {ranked.map((p) => {
              const b = riskBand(p[`risk_score_${year}`]);
              return (
                <li key={p.ward_id}>
                  <button onClick={() => onSelect(String(p.ward_id))}>
                    <span className="rank-name">{p.ward_name}<small>Ward {p.ward_id}</small></span>
                    <span className="rank-val">
                      {view === "risk" ? score100(p[`risk_score_${year}`]) ?? "—" : `${fmt(p[`depth_m_${year}`])} m`}
                    </span>
                    <i className="badge" style={{ background: b.color, color: bandText(b) }}>{b.label}</i>
                  </button>
                </li>
              );
            })}
          </ol>
        ) : <p className="muted">No ward has data for {year}.</p>}
      </section>
      <p className="hint">Click any ward on the map for its readings, model fit and forecast.</p>
    </div>
  );
}
