// ============================================================
// Groundwater depletion risk — the ONE place risk colours and
// score ranges are defined. Every component imports from here.
// ============================================================
//
// The backend supplies risk_score in [0, 1]. The dashboard shows it as an
// integer out of 100 (Math.round(score * 100)) and classifies that same
// displayed integer, so the label always agrees with the number shown.
// Scores themselves are never changed.

export const RISK_BANDS = [
  { key: "critical", label: "Critical", min: 85, max: 100, color: "#8B0000", text: "#FFFFFF",
    meaning: "Extremely high groundwater depletion risk" },
  { key: "high", label: "High", min: 70, max: 84, color: "#D32F2F", text: "#FFFFFF",
    meaning: "High groundwater depletion risk" },
  { key: "medhigh", label: "Medium-High", min: 55, max: 69, color: "#F57C00", text: "#1A1A1A",
    meaning: "Elevated groundwater depletion risk" },
  { key: "medium", label: "Medium", min: 40, max: 54, color: "#FBC02D", text: "#1A1A1A",
    meaning: "Moderate groundwater depletion risk" },
  { key: "lowmed", label: "Low-Medium", min: 25, max: 39, color: "#8BC34A", text: "#1A1A1A",
    meaning: "Relatively low groundwater depletion risk" },
  { key: "safe", label: "Safe", min: 0, max: 24, color: "#2E7D32", text: "#FFFFFF",
    meaning: "Low groundwater depletion risk" },
];

export const NO_DATA = {
  key: "nodata", label: "No Data", min: null, max: null, color: "#6B7280", text: "#FFFFFF",
  meaning: "Insufficient data for a valid prediction",
};

export const ALL_BANDS = [...RISK_BANDS, NO_DATA];          // Critical first
export const BAND_BY_KEY = Object.fromEntries(ALL_BANDS.map((b) => [b.key, b]));

/** Display score (0-100 integer) from the backend's 0-1 risk_score, or null. */
export function riskScore100(score01) {
  if (score01 == null || Number.isNaN(Number(score01))) return null;
  return Math.round(Number(score01) * 100);
}

/** Band for a backend risk_score in [0, 1]; null/NaN -> No Data (never a risk colour). */
export function riskBand(score01) {
  const s = riskScore100(score01);
  if (s == null) return NO_DATA;
  return RISK_BANDS.find((b) => s >= b.min) || RISK_BANDS[RISK_BANDS.length - 1];
}

export const rangeLabel = (b) => (b.min == null ? "" : `${b.min}–${b.max}`);
export const isElevated = (b) => b.key === "critical" || b.key === "high";
