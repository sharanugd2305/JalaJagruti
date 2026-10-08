// Map header control: selecting a ward highlights it and opens its details.
// The map view stays fixed (no zoom or pan).
export default function WardSearch({ options, value, onSelect }) {
  return (
    <label className="ward-find">
      <span className="sr-only">Find a ward</span>
      <select value={value || ""} onChange={(e) => e.target.value && onSelect(e.target.value)}>
        <option value="">Find a ward…</option>
        {options.map((w) => <option key={w.id} value={w.id}>{w.id}  {w.name}</option>)}
      </select>
    </label>
  );
}
