import { fmt } from "../theme.js";

const ICONS = {
  wards: <path d="M3 4h7v7H3zM12 4h7v7h-7zM3 13h7v7H3zM12 13h7v7h-7z" />,
  observed: <path d="M11 3v12M7 11l4 4 4-4M4 19h14" />,
  predicted: <path d="M3 17l5-6 4 3 7-9M15 5h4v4" />,
  risk: <path d="M11 3l9 16H2zM11 9v5M11 16.5v.5" />,
  depth: <path d="M11 3c3.5 5 6 8 6 11a6 6 0 0 1-12 0c0-3 2.5-6 6-11z" />,
};

function Card({ icon, label, value, unit, sub }) {
  return (
    <div className="stat">
      <svg viewBox="0 0 22 22" className="stat-icon" aria-hidden="true">{ICONS[icon]}</svg>
      <div>
        <p className="stat-label">{label}</p>
        <p className="stat-value">{value}{unit && <span>{unit}</span>}</p>
        {sub && <p className="stat-sub">{sub}</p>}
      </div>
    </div>
  );
}

export default function StatisticsCards({ stats, year }) {
  return (
    <section className="stats" aria-label={`Summary for ${year}`}>
      <Card icon="wards" label="Total wards" value={stats.total} />
      <Card icon="observed" label="Observed wards" value={stats.observed}
        sub={year === 2025 ? "with measured readings" : "with readings so far"} />
      <Card icon="predicted" label="Prediction available" value={stats.available} sub={`of ${stats.total}`} />
      <Card icon="risk" label="High / critical risk" value={stats.highCrit} sub="wards" />
      <Card icon="depth" label="Average depth" value={fmt(stats.avgDepth)} unit=" m"
        sub="across wards with data" />
    </section>
  );
}
