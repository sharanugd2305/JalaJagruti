// Ward polygon styles. Controls ONLY fillColor, fillOpacity, color, weight and
// opacity: no shadows, glows, filters or blur in any state or theme.
import { COLORS, depthColor, riskBand } from "./theme.js";

export const WARD_WEIGHT = { normal: 1, hover: 2, selected: 3 };
export const WARD_FILL_OPACITY = { normal: 0.85, hover: 0.95, noData: 0.7, dimmed: 0.14 };

export function wardInfo(p, year) {
  const depth = p[`depth_m_${year}`];
  const hasPred = depth != null && p[`prediction_status_${year}`] !== "INSUFFICIENT_INPUT_DATA";
  return { depth: hasPred ? depth : null, band: riskBand(hasPred ? p[`risk_score_${year}`] : null) };
}

export function wardStyle(props, { year, view, selectedId, highlightBand, palette }) {
  const { depth, band } = wardInfo(props, year);
  const noData = view === "risk" ? band.key === "nodata" : depth == null;
  const isSel = String(props.ward_id) === String(selectedId);
  const dimmed = Boolean(highlightBand) && band.key !== highlightBand;
  return {
    fillColor: view === "risk" ? band.color : depth == null ? COLORS.noData : depthColor(depth),
    fillOpacity: dimmed ? WARD_FILL_OPACITY.dimmed : noData ? WARD_FILL_OPACITY.noData : WARD_FILL_OPACITY.normal,
    color: isSel ? palette.selectedStroke : palette.wardStroke,
    weight: isSel ? WARD_WEIGHT.selected : WARD_WEIGHT.normal,
    opacity: dimmed && !isSel ? 0.35 : 1,
  };
}

export function hoverStyle(base, palette) {
  return {
    weight: Math.max(base.weight, WARD_WEIGHT.hover),
    fillOpacity: Math.max(base.fillOpacity, WARD_FILL_OPACITY.hover),
    opacity: 1,
    color: base.weight >= WARD_WEIGHT.selected ? base.color : palette.selectedStroke,
  };
}
