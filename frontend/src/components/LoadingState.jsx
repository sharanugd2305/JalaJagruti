export function PanelSkeleton({ label = "Loading…" }) {
  return (
    <div className="skeleton-wrap" role="status" aria-live="polite">
      <p className="skeleton-label">{label}</p>
      <div className="sk sk-title" />
      <div className="sk-row"><div className="sk sk-card" /><div className="sk sk-card" /></div>
      <div className="sk sk-chart" />
      <div className="sk sk-chart" />
    </div>
  );
}

export default function LoadingState() {
  return (
    <div className="app">
      <header className="header">
        <div className="brand"><div><h1>JalaJagruti AI</h1><p>Groundwater Intelligence Across Bengaluru's 243 Wards</p></div></div>
      </header>
      <div className="stats">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="stat"><div className="sk sk-stat" /></div>)}</div>
      <main className="layout">
        <section className="map-wrap"><div className="sk sk-map" role="status"><span>Loading ward data…</span></div></section>
        <aside className="panel"><PanelSkeleton label="Loading groundwater predictions…" /></aside>
      </main>
    </div>
  );
}
