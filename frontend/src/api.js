// Data access. Errors are reduced to a user-safe message; technical detail
// goes to the browser console for developers only.
const BASE = import.meta.env.VITE_API_BASE || "";

export class DataError extends Error {
  constructor(status) {
    super(status === 404 ? "No data available" : "Unable to load data");
    this.status = status;
  }
}

async function get(path, { signal } = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, { signal });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    console.warn(`[JalaJagruti] network error for ${path}`, e);
    throw new DataError(0);
  }
  if (!res.ok) {
    console.warn(`[JalaJagruti] ${path} returned HTTP ${res.status}`);
    throw new DataError(res.status);
  }
  return res.json();
}

export const api = {
  years: (o) => get("/api/years", o),
  geojson: (o) => get("/api/wards/geojson", o),
  metrics: (o) => get("/api/metrics", o),
  ward: (id, o) => get(`/api/wards/${encodeURIComponent(id)}`, o),
  timeseries: (id, o) => get(`/api/wards/${encodeURIComponent(id)}/timeseries`, o),
  climate: (id, o) => get(`/api/wards/${encodeURIComponent(id)}/climate`, o),
};
