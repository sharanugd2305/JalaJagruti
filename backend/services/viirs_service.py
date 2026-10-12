"""NASA Earthdata / LAADS DAAC -> VIIRS Black Marble VNP46A3 monthly night-time lights.

Authentication: NASA_EARTHDATA_TOKEN sent as `Authorization: Bearer <token>`.
Archive layout: /archive/allData/<collection>/VNP46A3/<YYYY>/<DOY>/VNP46A3.AYYYYDOY.hHHvVV.*.h5
VNP46A3 tiles are 10x10 degree, 2400x2400 px (15 arc-second) on a lat/lon grid,
h = floor((lon+180)/10), v = floor((90-lat)/10).

Output: one GeoTIFF per month (radiance, nW/cm^2/sr) cropped to the training bbox,
fill values -> NaN.
"""
from __future__ import annotations

import logging
import math
import re
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.transform import from_origin

from backend.config import Settings
from backend.errors import AuthenticationError, ServiceError
from backend.http_utils import request_with_retry, stream_download

log = logging.getLogger(__name__)
SERVICE = "NASA LAADS (VIIRS VNP46A3)"
BASE = "https://ladsweb.modaps.eosdis.nasa.gov/archive/allData"
AUTH_HINT = ("Set NASA_EARTHDATA_TOKEN in .env to a valid Earthdata Login (EDL) token "
             "(https://urs.earthdata.nasa.gov/ -> Generate Token).")
TILE_PX = 2400
TILE_DEG = 10.0


def tiles_for_bbox(bbox: tuple[float, float, float, float]) -> list[str]:
    minx, miny, maxx, maxy = bbox
    hs = range(int(math.floor((minx + 180) / 10)), int(math.floor((maxx - 1e-9 + 180) / 10)) + 1)
    vs = range(int(math.floor((90 - maxy) / 10)), int(math.floor((90 - miny - 1e-9) / 10)) + 1)
    return [f"h{h:02d}v{v:02d}" for h in hs for v in vs]


def _find_dataset(h5: h5py.File, name: str) -> h5py.Dataset:
    found: list[h5py.Dataset] = []

    def visit(_, obj):
        if isinstance(obj, h5py.Dataset) and obj.name.split("/")[-1] == name:
            found.append(obj)
    h5.visititems(visit)
    if not found:
        raise ValueError(f"dataset '{name}' not found in {h5.filename}")
    return found[0]


def _attr(ds, key, default=None):
    v = ds.attrs.get(key, default)
    if isinstance(v, (np.ndarray, list)) and len(v):
        v = v[0]
    if isinstance(v, bytes):
        v = v.decode()
    return v


class ViirsService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cfg = settings.section("viirs")
        self.cache = settings.dir("cache", "viirs")
        self.out_dir = settings.dir("processed", "viirs")
        self.session = requests.Session()
        self._collection: int | None = None

    def authenticate(self) -> None:
        token = self.settings.require("NASA_EARTHDATA_TOKEN")["NASA_EARTHDATA_TOKEN"]
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _list(self, url: str) -> list[dict]:
        resp = request_with_retry(SERVICE, "GET", url.rstrip("/") + ".json", session=self.session,
                                  auth_hint=AUTH_HINT, timeout=(20, 120))
        if "text/html" in resp.headers.get("Content-Type", ""):
            raise AuthenticationError(SERVICE, f"Directory listing returned HTML: {url}", AUTH_HINT)
        data = resp.json()
        if isinstance(data, dict):
            data = data.get("content", [])
        return data

    def _resolve_collection(self) -> int:
        if self._collection is not None:
            return self._collection
        product = self.cfg.get("product", "VNP46A3")
        errors = []
        for coll in self.cfg.get("collections", [5200, 5000]):
            try:
                years = self._list(f"{BASE}/{coll}/{product}")
                if years:
                    self._collection = int(coll)
                    log.info("[%s] using collection %s", SERVICE, coll)
                    return self._collection
            except AuthenticationError:
                raise
            except ServiceError as exc:
                errors.append(f"{coll}: {exc}")
        raise ServiceError(SERVICE, f"{product} not found in collections: {errors}",
                           "Check the 'viirs.collections' setting in config/project.yaml.")

    @staticmethod
    def _validate_h5(name: str):
        def check(path: Path):
            with h5py.File(path, "r") as h5:
                ds = _find_dataset(h5, name)
                if ds.shape[-2:] != (TILE_PX, TILE_PX):
                    raise ValueError(f"unexpected shape {ds.shape}")
        return check

    def _month_files(self, year: int, tiles: list[str]) -> dict[str, list[dict]]:
        coll, product = self._resolve_collection(), self.cfg.get("product", "VNP46A3")
        try:
            doys = [d["name"] for d in self._list(f"{BASE}/{coll}/{product}/{year}")]
        except ServiceError as exc:
            if "404" in str(exc):
                return {}
            raise
        out: dict[str, list[dict]] = {}
        for doy in sorted(doys):
            if not re.fullmatch(r"\d{3}", str(doy)):
                continue
            month = (pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=int(doy) - 1)).strftime("%Y-%m")
            files = self._list(f"{BASE}/{coll}/{product}/{year}/{doy}")
            sel = [{"name": f["name"], "url": f"{BASE}/{coll}/{product}/{year}/{doy}/{f['name']}"}
                   for f in files if any(f".{t}." in f["name"] for t in tiles) and f["name"].endswith(".h5")]
            if sel:
                out[month] = sel
        return out

    def _process_month(self, month: str, files: list[Path]) -> Path:
        out = self.out_dir / f"ntl_{month}.tif"
        if out.exists():
            return out
        minx, miny, maxx, maxy = self.settings.training_bbox
        res = TILE_DEG / TILE_PX
        width = int(round((maxx - minx) / res))
        height = int(round((maxy - miny) / res))
        canvas = np.full((height, width), np.nan, dtype="float32")
        name = self.cfg.get("dataset_name", "AllAngle_Composite_Snow_Free")
        for path in files:
            m = re.search(r"\.h(\d{2})v(\d{2})\.", path.name)
            h, v = int(m.group(1)), int(m.group(2))
            tile_minx, tile_maxy = h * TILE_DEG - 180, 90 - v * TILE_DEG
            with h5py.File(path, "r") as h5:
                ds = _find_dataset(h5, name)
                arr = ds[()].astype("float64")
                fill = _attr(ds, "_FillValue", 65535)
                scale = float(_attr(ds, "scale_factor", 0.1) or 0.1)
                offset = float(_attr(ds, "add_offset", 0.0) or 0.0)
            arr[arr == float(fill)] = np.nan
            arr = arr * scale + offset
            arr[arr < 0] = np.nan
            # place overlap into canvas
            c0 = int(round((minx - tile_minx) / res))
            r0 = int(round((tile_maxy - maxy) / res))
            for r in range(height):
                rr = r0 + r
                if not 0 <= rr < TILE_PX:
                    continue
                cc0, cc1 = max(c0, 0), min(c0 + width, TILE_PX)
                if cc1 <= cc0:
                    continue
                canvas[r, cc0 - c0:cc1 - c0] = arr[rr, cc0:cc1]
        profile = dict(driver="GTiff", width=width, height=height, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(minx, maxy, res, res),
                       nodata=np.nan, compress="deflate")
        tmp = out.with_suffix(".part.tif")
        with rasterio.open(tmp, "w", **profile) as dst:
            dst.write(canvas, 1)
            dst.set_band_description(1, "NTL_radiance_nW_cm2_sr")
        tmp.replace(out)
        return out

    def run(self, start_year: int, end_year: int) -> list[dict]:
        self.authenticate()
        tiles = tiles_for_bbox(self.settings.training_bbox)
        log.info("[%s] tiles %s, years %d-%d", SERVICE, tiles, start_year, end_year)
        check = self._validate_h5(self.cfg.get("dataset_name", "AllAngle_Composite_Snow_Free"))
        index = []
        for year in range(start_year, end_year + 1):
            for month, files in sorted(self._month_files(year, tiles).items()):
                local = [stream_download(SERVICE, f["url"], self.cache / f["name"],
                                         session=self.session, validate=check,
                                         auth_hint=AUTH_HINT, timeout=(20, 900))
                         for f in files]
                path = self._process_month(month, local)
                index.append({"month": month, "path": str(path.relative_to(self.settings.root))})
        if not index:
            raise ServiceError(SERVICE, "No VNP46A3 granules found for the requested period/tiles.")
        pd.DataFrame(index).to_csv(self.out_dir / "index.csv", index=False)
        log.info("[%s] %d monthly night-light rasters ready", SERVICE, len(index))
        return index
