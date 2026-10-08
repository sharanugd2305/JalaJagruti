import { usePalette } from "../ThemeContext.jsx";
import {
  CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmt } from "../theme.js";


export default function HistoricalChart({ history }) {
  const COLORS = usePalette();
  const axis = { fontSize: 11, fill: COLORS.axis };
  if (!history?.length) return <p className="muted">No monthly history for this ward.</p>;
  const data = history.map((r) => ({ t: r.month, actual: r.actual_m, model: r.pred_m, split: r.split }));
  const test = data.filter((d) => d.split === "test");
  return (
    <>
      <ResponsiveContainer width="100%" height={210}>
        <ComposedChart data={data} margin={{ top: 8, right: 10, left: -4, bottom: 0 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          {test.length > 0 && (
            <ReferenceArea x1={test[0].t} x2={test[test.length - 1].t} fill={COLORS.accent} fillOpacity={0.07}
              label={{ value: "2025 test period", fontSize: 10, fill: COLORS.axis, position: "insideTop" }} />
          )}
          <XAxis dataKey="t" tick={axis} minTickGap={36} />
          <YAxis reversed tick={axis} width={52} domain={["auto", "auto"]}
            label={{ value: "Depth (m)", angle: -90, position: "insideLeft", offset: 14, fontSize: 11, fill: COLORS.axis }} />
          <Tooltip formatter={(v, n) => [`${fmt(v, 2)} m`, n]} labelFormatter={(l) => l} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />
          <Line dataKey="actual" name="Measured" stroke={COLORS.measured} strokeWidth={1.7} dot={false} connectNulls={false} animationDuration={400} />
          <Line dataKey="model" name="CNN-LSTM prediction" stroke={COLORS.model} strokeWidth={1.7} strokeDasharray="5 4" dot={false} animationDuration={400} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="caption">Groundwater depth (m). The axis points down: greater depth indicates deeper groundwater.</p>
      {test.length > 0 && (
        <p className="caption">Each 2025 value is predicted one month ahead by a model that was not trained on
          2025 data, using only readings from before that month.</p>
      )}
    </>
  );
}
