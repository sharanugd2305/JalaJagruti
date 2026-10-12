"""Copernicus Data Space Ecosystem -> Sentinel-2 L2A -> NDVI & NDBI composites.

Uses the Sentinel Hub Process API hosted by CDSE with OAuth2 client credentials
(COPERNICUS_CLIENT_ID / COPERNICUS_CLIENT_SECRET).

For each composite period (quarter by default) we request, server-side, a
per-pixel *median* of cloud/shadow-masked observations (SCL-based) for:
  NDVI = (B08 - B04) / (B08 + B04)
  NDBI = (B11 - B08) / (B11 + B08)
plus the number of clear observations. Output: one float32 GeoTIFF per period
on the project's common EPSG:4326 grid. Pixels with no clear observation are NaN
(never filled with invented values).
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.merge import merge
from rasterio.transform import from_bounds

from backend.config import Settings
from backend.errors import ServiceError
from backend.http_utils import atomic_write, request_with_retry

log = logging.getLogger(__name__)
SERVICE = "Copernicus Data Space"
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
AUTH_HINT = ("Set COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET in .env to an OAuth client "
             "created in the CDSE Sentinel Hub dashboard (account settings -> OAuth clients).")

EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "B11", "SCL", "dataMask"] }],
    output: { id: "default", bands: 3, sampleType: "FLOAT32" },
    mosaicking: "ORBIT"
  };
}
// SCL classes excluded: 0 no data, 1 saturated, 3 cloud shadow, 8/9 cloud, 10 cirrus, 11 snow
var BAD = [0, 1, 3, 8, 9, 10, 11];
function median(a) {
  if (a.length === 0) return NaN;
  a.sort(function (x, y) { return x - y; });
  var m = Math.floor(a.length / 2);
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}
function evaluatePixel(samples) {
  var nd = [], nb = [];
  for (var i = 0; i < samples.length; i++) {
    var s = samples[i];
    if (!s.dataMask || BAD.indexOf(s.SCL) !== -1) continue;
    var a = s.B08 + s.B04, b = s.B11 + s.B08;
    if (a > 0) nd.push((s.B08 - s.B04) / a);
    if (b > 0) nb.push((s.B11 - s.B08) / b);
  }
  return [median(nd), median(nb), nd.length];
}
"""


@dataclass
class Grid:
    bbox: tuple[float, float, float, float]   # min_lon, min_lat, max_lon, max_lat
    width: int
    height: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "Grid":
        res = float(settings.section("sentinel2")["resolution_deg"])
        b = settings.training_bbox
        return cls(b, int(round((b[2] - b[0]) / res)), int(round((b[3] - b[1]) / res)))

    @property
    def transform(self):
        return from_bounds(*self.bbox, self.width, self.height)


def composite_periods(start: str, end: str, mode: str) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    freq = "QS" if mode == "quarterly" else "MS"
    starts = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=freq)
    out = []
    for s in starts:
        e = (s + (pd.offsets.QuarterEnd(0) if mode == "quarterly" else pd.offsets.MonthEnd(0)))
        label = f"{s.year}Q{(s.month - 1) // 3 + 1}" if mode == "quarterly" else s.strftime("%Y-%m")
        out.append((label, s, e))
    return out


class CopernicusService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cfg = settings.section("sentinel2")
        self.cache = settings.dir("cache", "sentinel2")
        self.out_dir = settings.dir("processed", "sentinel2")
        self.session = requests.Session()
        self._token_expiry = 0.0

    # ---- auth ------------------------------------------------------------------
    def authenticate(self) -> None:
        creds = self.settings.require("COPERNICUS_CLIENT_ID", "COPERNICUS_CLIENT_SECRET")
        resp = request_with_retry(
            SERVICE, "POST", TOKEN_URL, auth_hint=AUTH_HINT,
            data={"grant_type": "client_credentials",
                  "client_id": creds["COPERNICUS_CLIENT_ID"],
                  "client_secret": creds["COPERNICUS_CLIENT_SECRET"]},
            timeout=(20, 60))
        payload = resp.json()
        if "access_token" not in payload:
            raise ServiceError(SERVICE, f"Token response missing access_token: {str(payload)[:200]}",
                               AUTH_HINT)
        self.session.headers["Authorization"] = f"Bearer {payload['access_token']}"
        self._token_expiry = time.time() + float(payload.get("expires_in", 600)) - 60
        log.info("[%s] authenticated", SERVICE)

    def _ensure_token(self) -> None:
        if time.time() >= self._token_expiry:
            self.authenticate()

    # ---- requests --------------------------------------------------------------
    def _tiles(self, grid: Grid):
        n = int(self.cfg.get("tile_max_px", 512))
        nx, ny = math.ceil(grid.width / n), math.ceil(grid.height / n)
        minx, miny, maxx, maxy = grid.bbox
        dx, dy = (maxx - minx) / grid.width, (maxy - miny) / grid.height
        for iy in range(ny):
            for ix in range(nx):
                c0, c1 = ix * n, min((ix + 1) * n, grid.width)
                r0, r1 = iy * n, min((iy + 1) * n, grid.height)
                yield (ix, iy, (minx + c0 * dx, maxy - r1 * dy, minx + c1 * dx, maxy - r0 * dy),
                       c1 - c0, r1 - r0)

    @staticmethod
    def _validate_tiff(path: Path) -> None:
        with rasterio.open(path) as src:
            if src.count != 3:
                raise ValueError(f"expected 3 bands, got {src.count}")
            src.read(1, window=((0, 1), (0, 1)))

    def _fetch_tile(self, label, t0, t1, ix, iy, bbox, w, h) -> Path:
        path = self.cache / f"s2_{label}_{ix}_{iy}_{w}x{h}.tif"
        if path.exists():
            try:
                self._validate_tiff(path)
                return path
            except Exception:
                path.unlink(missing_ok=True)
        self._ensure_token()
        body = {
            "input": {
                "bounds": {"bbox": list(bbox),
                           "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
                "data": [{"type": "sentinel-2-l2a",
                          "dataFilter": {"timeRange": {"from": t0.strftime("%Y-%m-%dT00:00:00Z"),
                                                       "to": t1.strftime("%Y-%m-%dT23:59:59Z")},
                                         "maxCloudCoverage": int(self.cfg.get("max_cloud_cover", 80))}}],
            },
            "output": {"width": w, "height": h,
                       "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
            "evalscript": EVALSCRIPT,
        }
        resp = request_with_retry(SERVICE, "POST", PROCESS_URL, session=self.session, json=body,
                                  headers={"Accept": "image/tiff"}, auth_hint=AUTH_HINT,
                                  on_auth_failure=self.authenticate, timeout=(20, 600))
        if not resp.headers.get("Content-Type", "").startswith("image/tiff"):
            raise ServiceError(SERVICE, f"Unexpected response type {resp.headers.get('Content-Type')}: "
                                        f"{resp.text[:300]}")
        atomic_write(path, resp.content)
        self._validate_tiff(path)
        return path

    def fetch_period(self, label: str, t0: pd.Timestamp, t1: pd.Timestamp, grid: Grid) -> Path:
        out = self.out_dir / f"s2_indices_{label}.tif"
        if out.exists():
            return out
        tiles = [self._fetch_tile(label, t0, t1, ix, iy, b, w, h)
                 for ix, iy, b, w, h in self._tiles(grid)]
        srcs = [rasterio.open(p) for p in tiles]
        try:
            mosaic, _ = merge(srcs, bounds=grid.bbox, res=(
                (grid.bbox[2] - grid.bbox[0]) / grid.width,
                (grid.bbox[3] - grid.bbox[1]) / grid.height), nodata=np.nan)
        finally:
            for s in srcs:
                s.close()
        mosaic = mosaic[:, :grid.height, :grid.width].astype("float32")
        mosaic[2][~np.isfinite(mosaic[2])] = 0
        # pixels with zero clear observations are NaN for the indices
        no_obs = mosaic[2] <= 0
        mosaic[0][no_obs] = np.nan
        mosaic[1][no_obs] = np.nan
        profile = dict(driver="GTiff", width=grid.width, height=grid.height, count=3,
                       dtype="float32", crs="EPSG:4326", transform=grid.transform,
                       nodata=np.nan, compress="deflate")
        tmp = out.with_suffix(".part.tif")
        with rasterio.open(tmp, "w", **profile) as dst:
            dst.write(mosaic)
            dst.set_band_description(1, "NDVI")
            dst.set_band_description(2, "NDBI")
            dst.set_band_description(3, "clear_obs_count")
        tmp.replace(out)
        valid = float(np.isfinite(mosaic[0]).mean())
        log.info("[%s] %s composite written (%.1f%% pixels with clear observations)",
                 SERVICE, label, 100 * valid)
        return out

    def run(self, start: str, end: str) -> list[dict]:
        grid = Grid.from_settings(self.settings)
        periods = composite_periods(start, end, self.cfg.get("composite", "quarterly"))
        log.info("[%s] %d composite periods, grid %dx%d", SERVICE, len(periods), grid.width, grid.height)
        index = []
        for label, t0, t1 in periods:
            if t0 > pd.Timestamp.utcnow().tz_localize(None):
                continue
            path = self.fetch_period(label, t0, min(t1, pd.Timestamp.utcnow().tz_localize(None)), grid)
            index.append({"period": label, "start": str(t0.date()), "end": str(t1.date()),
                          "path": str(path.relative_to(self.settings.root))})
        pd.DataFrame(index).to_csv(self.out_dir / "index.csv", index=False)
        return index
