export default function ErrorState({ onRetry, compact = false }) {
  return (
    <div className={compact ? "error-state compact" : "error-state"} role="alert">
      <svg viewBox="0 0 40 40" aria-hidden="true">
        <path d="M20 5c7 9 12 15 12 21a12 12 0 0 1-24 0c0-6 5-12 12-21z" fill="none" stroke="#4FB3A5" strokeWidth="2" />
        <path d="M14 30l12-12" stroke="#5FB8F4" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <h2>Unable to load data</h2>
      <p>Please try again.</p>
      {onRetry && <button className="btn" onClick={onRetry}>Retry</button>}
    </div>
  );
}
