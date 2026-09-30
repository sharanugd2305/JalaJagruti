export default function RiskTable({ currentScore = 50 }) {
  const data = [
    { min: 95, max: 100, range: "95-100", cat: "Critical", months: "0-2 months", color: "bg-rose-600 text-white", highlightColor: "bg-rose-700/40 border-l-4 border-rose-500" },
    { min: 85, max: 94, range: "85-95", cat: "High", months: "2-4 months", color: "bg-rose-500 text-rose-50", highlightColor: "bg-rose-700/40 border-l-4 border-rose-500" },
    { min: 70, max: 84, range: "70-85", cat: "Medium-High", months: "4-6 months", color: "bg-orange-500 text-orange-50", highlightColor: "bg-orange-700/40 border-l-4 border-orange-500" },
    { min: 50, max: 69, range: "50-70", cat: "Medium", months: "6-9 months", color: "bg-amber-400 text-amber-950", highlightColor: "bg-amber-700/40 border-l-4 border-amber-500" },
    { min: 30, max: 49, range: "30-50", cat: "Low-Medium", months: "9-12 months", color: "bg-emerald-500 text-emerald-50", highlightColor: "bg-emerald-700/40 border-l-4 border-emerald-500" },
    { min: 0, max: 29, range: "0-30", cat: "Safe", months: ">12 months", color: "bg-cyan-500 text-cyan-50", highlightColor: "bg-cyan-700/40 border-l-4 border-cyan-500" },
  ];

  const getRiskCategory = (score) => {
    return data.find((d) => score >= d.min && score <= d.max);
  };

  const activeCategory = getRiskCategory(currentScore);

  return (
    <div className="rounded-xl border border-blue-500/25 bg-[#051733]/70 p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-[15px] font-extrabold uppercase tracking-[0.12em] text-blue-100">
          Risk Classification
        </h2>
        {activeCategory && (
          <div className="text-right">
            <p className="text-xs text-blue-200/70 uppercase tracking-wider">Current Risk</p>
            <p className={`text-lg font-bold ${activeCategory.color} px-3 py-1 rounded-lg`}>
              {activeCategory.cat} ({currentScore})
            </p>
          </div>
        )}
      </div>

      <table className="w-full table-fixed text-sm text-blue-100/85">
        <thead className="border-b border-blue-500/20 text-[12px] uppercase tracking-[0.12em] text-blue-200/70">
          <tr>
            <th className="pb-3 text-left font-semibold w-[24%]">Risk Score</th>
            <th className="pb-3 text-left font-semibold w-[40%]">Category</th>
            <th className="pb-3 text-left font-semibold w-[36%]">Time Remaining</th>
          </tr>
        </thead>

        <tbody className="divide-y divide-blue-500/15">
          {data.map((d, i) => {
            const isActive = activeCategory && d.min === activeCategory.min;
            return (
              <tr
                key={i}
                className={`h-[44px] transition ${
                  isActive ? d.highlightColor : ""
                }`}
              >
                <td className="py-3 font-medium text-blue-100/90">{d.range}</td>
                <td className="py-3">
                  <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${d.color}`}>
                    <span className="h-2.5 w-2.5 rounded-full bg-white/70" />
                    {d.cat}
                  </span>
                </td>
                <td className="py-3 font-semibold text-blue-50">{d.months}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}