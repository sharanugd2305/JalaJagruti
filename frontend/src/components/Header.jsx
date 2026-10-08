import YearSelector from "./YearSelector.jsx";
import DashboardTabs from "./DashboardTabs.jsx";
import ThemeToggle from "./ThemeToggle.jsx";

export default function Header({ years, year, onYear, view, onView }) {
  return (
    <header className="header">
      <div className="brand">
        <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
          <path d="M16 3c5 7 9 11.5 9 16.5A9 9 0 0 1 7 19.5C7 14.5 11 10 16 3z" fill="#2A7F7A" />
          <path d="M9 21.5h14M10.5 25h11" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <div>
          <h1>JalaJagruti AI</h1>
          <p>Groundwater Intelligence Across Bengaluru's 243 Wards</p>
        </div>
      </div>
      <div className="header-controls">
        <DashboardTabs view={view} onView={onView} />
        {view !== "accuracy" && <YearSelector years={years} year={year} onYear={onYear} />}
        <ThemeToggle />
      </div>
    </header>
  );
}
