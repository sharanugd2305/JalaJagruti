// Central colour system and formatting. Every component takes colours from here.

// Per-theme colours for things drawn by JavaScript (charts, map strokes).
// Page colours are CSS variables in styles.css ([data-theme="dark"|"light"]).
// Data series keep the same colour in both themes; only neutral ink changes.
const MODEL_BLUE = "#2F86CF";
export const PALETTES = {
  dark: {
    accent: "#2DD4BF", text: "#F8FAFC", textSecondary: "#94A3B8", muted: "#64748B",
    grid: "#263247", axis: "#94A3B8",
    measured: "#F8FAFC", model: MODEL_BLUE, band: MODEL_BLUE, barMuted: "#475569",
    wardStroke: "rgba(255,255,255,0.70)", selectedStroke: "#FFFFFF", mapBg: "#0A0F1A",
  },
  light: {
    accent: "#0F766E", text: "#0F172A", textSecondary: "#475569", muted: "#64748B",
    grid: "#E2E8F0", axis: "#475569",
    measured: "#0F172A", model: MODEL_BLUE, band: MODEL_BLUE, barMuted: "#CBD5E1",
    wardStroke: "rgba(30,41,59,0.55)", selectedStroke: "#0F172A", mapBg: "#EEF1F4",
  },
};

// Theme-independent constants.
export const COLORS = { noData: NO_DATA.color };

export const INSUFFICIENT = "INSUFFICIENT_INPUT_DATA";

// Risk colours live in riskColors.js (single source of truth); re-exported here.
export { RISK_BANDS, NO_DATA as NO_DATA_BAND, riskBand, rangeLabel, isElevated } from "./riskColors.js";
import { NO_DATA, riskScore100 } from "./riskColors.js";

// Depth: sequential water palette, light (shallow) to dark (deep).
const DEPTH_STOPS = [
  [0, [189, 233, 245]], [10, [108, 198, 232]], [20, [47, 143, 214]],
  [30, [61, 91, 201]], [40, [106, 63, 181]],
];
export const DEPTH_TICKS = [0, 10, 20, 30, 40];
export function depthColor(d) {
  if (d == null || Number.isNaN(d)) return COLORS.noData;
  const v = Math.max(0, Math.min(40, d));
  for (let i = 1; i < DEPTH_STOPS.length; i++) {
    const [d1, c1] = DEPTH_STOPS[i];
    const [d0, c0] = DEPTH_STOPS[i - 1];
    if (v <= d1) {
      const t = (v - d0) / (d1 - d0);
      return `rgb(${c0.map((x, k) => Math.round(x + t * (c1[k] - x))).join(",")})`;
    }
  }
  return "rgb(106,63,181)";
}

export const STATUS_TEXT = {
  PREDICTED_OUT_OF_SAMPLE: "Model prediction, checked against 2025 readings",
  FORECAST_WITHIN_VALIDATED_HORIZON: "Forecast within the tested range",
  FORECAST_BEYOND_VALIDATED_HORIZON: "Forecast beyond the tested range (indicative)",
  INSUFFICIENT_INPUT_DATA: "No Data",
};
export const STATUS_SHORT = {
  PREDICTED_OUT_OF_SAMPLE: "Prediction",
  FORECAST_WITHIN_VALIDATED_HORIZON: "Tested forecast",
  FORECAST_BEYOND_VALIDATED_HORIZON: "Indicative forecast",
  INSUFFICIENT_INPUT_DATA: "No Data",
};
export const BASIS_TEXT = {
  STATION_IN_WARD: "Monitoring well inside this ward",
  INTERPOLATED_IDW: "Estimated from nearby wells",
  NO_STATION_WITHIN_RANGE: "No monitoring well close enough",
};

export const isNum = (v) => v != null && !Number.isNaN(Number(v));
export const fmt = (v, d = 1) => (isNum(v) ? Number(v).toFixed(d) : "—");
export const score100 = riskScore100;
export const yearKind = (y) => (y === 2025 ? "Prediction" : "Forecast");

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Text colour with sufficient contrast on each band colour (defined per band).
export const bandText = (b) => b.text;
