import { usePalette } from "../ThemeContext.jsx";
import {
  Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { fmt } from "../theme.js";


export default function ForecastChart({ forecast }) {
  const COLORS = usePalette();
  const axis = { fontSize: 11, fill: COLORS.axis };
  if (!forecast?.length) return <p className="muted">No forecast for this ward.</p>;
  const data = forecast.map((r) => ({
    t: r.month, pred: r.pred_m, actual: r.actual_m,
    band: r.lower_m != null && r.upper_m != null ? [r.lower_m, r.upper_m] : null,
    tested: r.within_validated_horizon,
  }));
  const hasBand = data.some((d) => d.band);
  const tested = data.filter((d) => d.tested);
  const lastTested = tested.length ? tested[tested.length - 1].t : null;
  return (
    <>
      <ResponsiveContainer width="100%" height={210}>
        <ComposedChart data={data} margin={{ top: 8, right: 10, left: -4, bottom: 0 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          {lastTested && (
            <ReferenceArea x1={data[0].t} x2={lastTested} fill={COLORS.accent} fillOpacity={0.07}
              label={{ value: "Tested", fontSize: 10, fill: COLORS.axis, position: "insideTopLeft" }} />
          )}
          {lastTested && (
            <ReferenceLine x={lastTested} stroke={COLORS.axis} strokeDasharray="3 3"
              label={{ value: "Future forecast", fontSize: 10, fill: COLORS.axis, position: "insideTopRight" }} />
          )}
          <XAxis dataKey="t" tick={axis} minTickGap={36} />
          <YAxis reversed tick={axis} width={52} domain={["auto", "auto"]}
            label={{ value: "Depth (m)", angle: -90, position: "insideLeft", offset: 14, fontSize: 11, fill: COLORS.axis }} />
          <Tooltip formatter={(v, n) => (Array.isArray(v) ? [`${fmt(v[0])}–${fmt(v[1])} m`, n] : [`${fmt(v, 2)} m`, n])} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {hasBand && <Area dataKey="band" name="Uncertainty range" fill={COLORS.band} fillOpacity={0.3} stroke="none" animationDuration={400} />}
          <Line dataKey="pred" name="Forecast" stroke={COLORS.model} strokeWidth={1.9} dot={false} animationDuration={400} />
          <Line dataKey="actual" name="Measured" stroke={COLORS.measured} strokeWidth={0} dot={{ r: 2.2 }} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="caption">
        {hasBand ? "The shaded range combines ensemble spread with measured forecast error. " : ""}
        Future months assume average rainfall and temperature and today's land cover. Beyond the tested
        period, treat values as indicative.
      </p>
    </>
  );
}
