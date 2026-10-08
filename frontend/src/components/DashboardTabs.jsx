const TABS = [["depth", "Water Depth"], ["risk", "Risk"], ["accuracy", "Model Accuracy"]];

export default function DashboardTabs({ view, onView }) {
  return (
    <nav className="seg seg-tabs" role="tablist" aria-label="Dashboard view">
      {TABS.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={view === k}
          className={view === k ? "on" : ""} onClick={() => onView(k)}>{label}</button>
      ))}
    </nav>
  );
}
