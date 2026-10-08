import { yearKind } from "../theme.js";

export default function YearSelector({ years, year, onYear }) {
  return (
    <div className="seg seg-years" role="radiogroup" aria-label="Year">
      {years.map((y) => (
        <button key={y} role="radio" aria-checked={y === year}
          className={y === year ? "on" : ""} onClick={() => onYear(y)}>
          <span className="yr">{y}</span>
          <span className="yr-kind">{yearKind(y)}</span>
        </button>
      ))}
    </div>
  );
}
