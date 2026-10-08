import { useEffect, useRef } from "react";
import { MapContainer, GeoJSON, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { escapeHtml, fmt, score100 } from "../theme.js";
import { hoverStyle, wardInfo, wardStyle } from "../mapStyles.js";
import { useTheme } from "../ThemeContext.jsx";

// ---- basemaps (no keys; override or disable via frontend/.env) ----
const env = import.meta.env;
const ESRI = "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas";
const BASEMAPS = {
  dark: {
    base: env.VITE_BASEMAP_URL ?? `${ESRI}/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    labels: env.VITE_BASEMAP_LABELS_URL ?? `${ESRI}/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
    baseOpacity: 0.9, labelOpacity: 0.55,
  },
  light: {
    base: env.VITE_BASEMAP_LIGHT_URL ?? `${ESRI}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    labels: env.VITE_BASEMAP_LIGHT_LABELS_URL ?? `${ESRI}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
    baseOpacity: 1, labelOpacity: 0.7,
  },
};
const enabled = (u) => Boolean(u) && u !== "none";
const anyBasemap = enabled(BASEMAPS.dark.base) || enabled(BASEMAPS.light.base);
// The required credit is shown as a caption below the map (not on top of it).
export const basemapCredit = anyBasemap
  ? (env.VITE_BASEMAP_ATTRIBUTION ?? "Esri, HERE, Garmin, © OpenStreetMap contributors") : null;

const LOCKED = {
  zoomControl: false, attributionControl: false, dragging: false, touchZoom: false,
  doubleClickZoom: false, scrollWheelZoom: false, boxZoom: false, keyboard: false,
  zoomSnap: 0, zoomDelta: 0, inertia: false,
};

function EnsurePanes() {
  const map = useMap();
  const pane = map.getPane("map-labels") || map.createPane("map-labels");
  pane.style.zIndex = 450;           // labels above polygons, never intercept clicks
  pane.style.pointerEvents = "none";
  return null;
}

function LockToWards({ bounds }) {
  const map = useMap();
  useEffect(() => {
    const fit = () => {
      map.invalidateSize({ animate: false });
      map.setMinZoom(0); map.setMaxZoom(30); map.setMaxBounds(null);
      map.fitBounds(bounds, { padding: [18, 18], animate: false });
      const z = map.getZoom();
      map.setMinZoom(z); map.setMaxZoom(z);
      map.setMaxBounds(bounds.pad(0.25));
    };
    fit();
    const ro = new ResizeObserver(() => fit());
    ro.observe(map.getContainer());
    return () => ro.disconnect();
  }, [map, bounds]);
  return null;
}

// If a tile provider refuses requests, drop the basemap silently; the wards stay usable.
function SafeTiles({ url, pane, opacity }) {
  const ref = useRef(null);
  const stats = useRef({ ok: 0, err: 0 });
  const handlers = {
    tileload: () => { stats.current.ok += 1; },
    tileerror: () => {
      stats.current.err += 1;
      if (stats.current.err >= 6 && stats.current.ok === 0 && ref.current) {
        console.warn("[JalaJagruti] basemap unavailable; continuing without it");
        ref.current.remove();
      }
    },
  };
  return <TileLayer ref={ref} url={url} pane={pane} opacity={opacity} eventHandlers={handlers}
    maxNativeZoom={16} crossOrigin="anonymous" />;
}

export default function MapView({ geo, year, view, selectedId, highlightBand, onSelect }) {
  const { theme, palette } = useTheme();
  const layerRef = useRef(null);
  const state = useRef({});
  state.current = { year, view, selectedId, highlightBand, palette };
  const boundsRef = useRef(L.geoJSON(geo).getBounds());
  const bm = BASEMAPS[theme];

  const style = (f) => wardStyle(f.properties, state.current);

  const tooltip = (lyr) => {
    const p = lyr.feature.properties;
    const { depth, band } = wardInfo(p, state.current.year);
    const s = score100(depth == null ? null : p[`risk_score_${state.current.year}`]);
    const head = `<div class="tt-id">Ward ${escapeHtml(p.ward_id)}</div><div class="tt-name">${escapeHtml(p.ward_name)}</div>`;
    const rows = band.key === "nodata"
      ? `<div class="tt-row"><span>Risk</span><b>NO DATA</b></div>
         <div class="tt-row"><span>Depth</span><b>${depth == null ? "—" : `${fmt(depth)} m`}</b></div>`
      : `<div class="tt-row"><span>Risk</span><b class="tt-risk"><i style="background:${band.color}"></i>${band.label.toUpperCase()}</b></div>
         <div class="tt-row"><span>Score</span><b>${s} / 100</b></div>
         <div class="tt-row"><span>Depth</span><b>${fmt(depth)} m</b></div>`;
    return `<div class="tt" style="--tt-accent:${band.color}">${head}${rows}</div>`;
  };

  // Keep the tooltip inside the map near its edges.
  const placeTooltip = (lyr, e) => {
    const tt = lyr.getTooltip();
    const map = lyr._map;
    if (!tt || !map || !e?.containerPoint) return;
    const { x, y } = e.containerPoint;
    const size = map.getSize();
    let dir = "top", offset = [0, -10];
    if (y < 130) { dir = "bottom"; offset = [0, 12]; }
    if (x < 110) { dir = "right"; offset = [12, 0]; }
    else if (x > size.x - 110) { dir = "left"; offset = [-12, 0]; }
    if (tt.options.direction !== dir) {
      tt.options.direction = dir;
      tt.options.offset = L.point(offset);
      if (tt.isOpen?.()) tt.update();
    }
  };

  const bringSelectedToFront = () => {
    layerRef.current?.eachLayer((l) => {
      if (String(l.feature.properties.ward_id) === String(state.current.selectedId)) l.bringToFront();
    });
  };

  const onEach = (f, lyr) => {
    lyr.once("add", () => {
      const el = lyr.getElement();
      if (el) {
        el.dataset.ward = String(f.properties.ward_id);
        el.setAttribute("aria-label", `Ward ${f.properties.ward_id}, ${f.properties.ward_name}`);
        el.classList.add("ward");
      }
    });
    lyr.bindTooltip(tooltip, { sticky: true, direction: "top", offset: [0, -10], className: "ward-tip", opacity: 1 });
    lyr.on({
      mousemove: (e) => placeTooltip(lyr, e),
      mouseover: (e) => {
        placeTooltip(lyr, e);
        lyr.setStyle(hoverStyle(style(f), state.current.palette));
        lyr.bringToFront();
      },
      mouseout: () => { layerRef.current?.resetStyle(lyr); bringSelectedToFront(); },
      click: () => onSelect(String(f.properties.ward_id)),
    });
  };

  // Restyle in place (no remount) when year, view, selection, highlight or theme changes.
  useEffect(() => {
    if (!layerRef.current) return;
    layerRef.current.setStyle(style);
    bringSelectedToFront();
  }, [year, view, selectedId, highlightBand, theme]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <MapContainer className="map" center={boundsRef.current.getCenter()} zoom={11} {...LOCKED}>
      <EnsurePanes />
      {enabled(bm.base) && <SafeTiles key={`base-${theme}`} url={bm.base} pane="tilePane" opacity={bm.baseOpacity} />}
      <GeoJSON ref={layerRef} data={geo} style={style} onEachFeature={onEach} />
      {enabled(bm.labels) && <SafeTiles key={`labels-${theme}`} url={bm.labels} pane="map-labels" opacity={bm.labelOpacity} />}
      <LockToWards bounds={boundsRef.current} />
    </MapContainer>
  );
}
