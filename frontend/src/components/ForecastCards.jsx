import { STATUS_SHORT, bandText, fmt, riskBand } from "../theme.js";

export default function ForecastCards({ rows, year, onYear }) {
  const future = rows.filter((r) => r.year > 2025);
  if (!future.length) return null;
  return (
    <div className="fc-cards">
      {future.map((r) => {
        const has = r.depth_m != null && r.prediction_status !== "INSUFFICIENT_INPUT_DATA";
        const b = riskBand(has ? r.risk_score : null);
        return (
          <button key={r.year} className={`fc-card ${r.year === year ? "on" : ""}`} onClick={() => onYear(r.year)}
            aria-pressed={r.year === year}>
            <span className="fc-year">{r.year}</span>
            <span className="fc-label">Predicted depth</span>
            <span className="fc-val">{has ? `${fmt(r.depth_m)} m` : "No Data"}</span>
            <i className="badge" style={{ background: b.color, color: bandText(b) }}>{b.label}</i>
            {has && <span className="fc-status">{STATUS_SHORT[r.prediction_status]}</span>}
          </button>
        );
      })}
    </div>
  );
}
