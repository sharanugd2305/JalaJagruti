import { useTheme } from "../ThemeContext.jsx";

// Compact sun/moon switch. Keyboard accessible (native button, Enter/Space).
export default function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  const hint = `Switch to ${next} mode`;
  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label="Toggle theme"
      title={hint} aria-pressed={theme === "light"} data-theme-current={theme}>
      <span className="tt-track" aria-hidden="true">
        <svg className="ico ico-sun" viewBox="0 0 20 20"><circle cx="10" cy="10" r="3.6" />
          <path d="M10 1.8v2.1M10 16.1v2.1M1.8 10h2.1M16.1 10h2.1M4.2 4.2l1.5 1.5M14.3 14.3l1.5 1.5M4.2 15.8l1.5-1.5M14.3 5.7l1.5-1.5" /></svg>
        <svg className="ico ico-moon" viewBox="0 0 20 20"><path d="M15.8 12.6A6.6 6.6 0 0 1 7.4 4.2a6.6 6.6 0 1 0 8.4 8.4z" /></svg>
        <span className="tt-thumb" />
      </span>
      <span className="sr-only">{hint}</span>
    </button>
  );
}
