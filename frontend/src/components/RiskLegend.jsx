import { ALL_BANDS, rangeLabel } from "../riskColors.js";
import { DEPTH_TICKS, NO_DATA_BAND, depthColor } from "../theme.js";

// Sidebar legend. Rendered OUTSIDE the Leaflet map as its own layout column,
// so it can never cover ward polygons. Counts are computed from backend data.
export default function RiskLegend({ view, year, counts, highlightBand, onHighlight }) {
  if (view !== "risk") {
    return (
      <div className="legend-card" aria-label="Groundwater depth legend">
        <h2 className="legend-title">Groundwater depth</h2>
        <p className="legend-sub">Metres below ground, {year}</p>
        <div className="ramp" style={{ background: `linear-gradient(90deg, ${DEPTH_TICKS.map(depthColor).join(",")})` }} />
        <div className="ramp-ticks">{DEPTH_TICKS.map((t) => <span key={t}>{t === 40 ? "40+" : t}</span>)}</div>
        <p className="legend-row-static"><i style={{ background: NO_DATA_BAND.color }} />No Data</p>
        <p className="legend-foot">This is a depth scale, not risk. Switch to the Risk view for depletion risk.</p>
      </div>
    );
  }
  const total = ALL_BANDS.reduce((s, b) => s + (counts[b.key] || 0), 0);
  return (
    <div className="legend-card" aria-label="Groundwater depletion risk legend">
      <h2 className="legend-title">Groundwater depletion risk</h2>
      <p className="legend-sub">{year}, wards per level</p>
      <ul className="legend-list">
        {ALL_BANDS.map((b) => (
          <li key={b.key}>
            <button className={highlightBand === b.key ? "on" : ""} aria-pressed={highlightBand === b.key}
              title={`${b.meaning}. Click to highlight these wards.`}
              onClick={() => onHighlight(highlightBand === b.key ? null : b.key)}>
              <i style={{ background: b.color }} />
              <span className="lg-label">{b.label}</span>
              <span className="lg-range">{rangeLabel(b)}</span>
              <span className="lg-count">{counts[b.key] || 0}</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="dist-bar" aria-hidden="true">
        {ALL_BANDS.map((b) => counts[b.key] > 0 && (
          <span key={b.key} style={{ flexGrow: counts[b.key], background: b.color }} />
        ))}
      </div>
      <p className="legend-foot">Risk score out of 100. {total} wards. Click a level to highlight it.</p>
    </div>
  );
}
