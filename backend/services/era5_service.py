"""Copernicus Climate Data Store -> ERA5-Land monthly means -> rainfall & temperature.

Uses the official `cdsapi` client with CDS_API_KEY (personal access token) and the
CDS API URL from config/project.yaml. The ERA5-Land licence must be accepted once
on the CDS website by the account owning the token.

Conversions (monthly-averaged reanalysis):
  total_precipitation: metres/day (mean daily accumulation) -> mm/month
  2m_temperature: K -> degC
Output: data/processed/era5/era5_land_monthly.nc  (time, latitude, longitude)
"""
from __future__ import annotations

import logging
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from backend.config import Settings
from backend.errors import AuthenticationError, ServiceError

log = logging.getLogger(__name__)
SERVICE = "Copernicus CDS (ERA5-Land)"
AUTH_HINT = ("Set CDS_API_KEY in .env to your CDS personal access token "
             "(https://cds.climate.copernicus.eu/profile) and accept the ERA5-Land licence "
             "on the dataset page (Download tab -> Terms of use).")


def _open_any(path: Path) -> xr.Dataset:
    """Open a CDS NetCDF download, which may be a zip of several NetCDFs."""
    if zipfile.is_zipfile(path):
        extract = path.with_suffix("")
        extract.mkdir(exist_ok=True)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(extract)
        parts = [xr.open_dataset(p).load() for p in sorted(extract.glob("*.nc"))]
        ds = xr.merge(parts, compat="override")
    else:
        ds = xr.open_dataset(path).load()
    rename = {}
    if "valid_time" in ds.dims or "valid_time" in ds.coords:
        rename["valid_time"] = "time"
    ds = ds.rename(rename)
    drop = [c for c in ("number", "expver") if c in ds.coords or c in ds.dims]
    for c in drop:
        if c in ds.dims and ds.sizes[c] > 1:
            ds = ds.max(c, skipna=True)  # expver: combine ERA5/ERA5T
        ds = ds.drop_vars(c, errors="ignore")
    return ds


class Era5Service:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cfg = settings.section("era5")
        self.cache = settings.dir("cache", "era5")
        self.out_dir = settings.dir("processed", "era5")
        self._client = None

    def authenticate(self):
        key = self.settings.require("CDS_API_KEY")["CDS_API_KEY"]
        try:
            import cdsapi
        except ImportError as exc:
            raise ServiceError(SERVICE, "Python package 'cdsapi' is not installed.",
                               "pip install -r requirements.txt") from exc
        self._client = cdsapi.Client(url=self.cfg.get("api_url"), key=key, quiet=True,
                                     progress=False, retry_max=10, sleep_max=120, timeout=600)
        return self._client

    @staticmethod
    def _validate(path: Path) -> None:
        ds = _open_any(path)
        if not {"t2m", "tp"} <= set(ds.data_vars):
            raise ValueError(f"missing variables, found {list(ds.data_vars)}")

    def _area(self) -> list[float]:
        minx, miny, maxx, maxy = self.settings.training_bbox
        pad = 0.2  # ~2 grid cells so edge stations have neighbours
        return [round(maxy + pad, 2), round(minx - pad, 2), round(miny - pad, 2), round(maxx + pad, 2)]

    def _fetch_year(self, year: int) -> Path | None:
        target = self.cache / f"era5_land_{year}.nc"
        now = pd.Timestamp.utcnow().tz_localize(None)
        months = [f"{m:02d}" for m in range(1, 13) if pd.Timestamp(year, m, 1) < now]
        if target.exists():
            try:
                self._validate(target)
                # refresh the current year if new months may have been published
                if year < now.year or (now - pd.Timestamp(target.stat().st_mtime, unit="s")).days < 15:
                    return target
            except Exception as exc:
                log.warning("[%s] cached %s invalid (%s); re-downloading", SERVICE, target.name, exc)
            target.unlink(missing_ok=True)
        if not months:
            return None
        request = {
            "product_type": ["monthly_averaged_reanalysis"],
            "variable": ["2m_temperature", "total_precipitation"],
            "year": [str(year)], "month": months, "time": ["00:00"],
            "area": self._area(), "data_format": "netcdf", "download_format": "unarchived",
        }
        tmp = target.with_suffix(".part")
        last = None
        for attempt in range(1, 4):
            try:
                self._client.retrieve(self.cfg.get("dataset"), request, str(tmp))
                break
            except Exception as exc:  # cdsapi raises generic exceptions
                msg = str(exc)
                low = msg.lower()
                if any(k in low for k in ("401", "403", "authentication", "unauthorized", "licence",
                                          "license", "required licences not accepted", "forbidden")):
                    raise AuthenticationError(SERVICE, msg[:500], AUTH_HINT) from exc
                if "no data" in low or "none of the data" in low:
                    log.warning("[%s] no data yet for %d (%s)", SERVICE, year, msg[:120])
                    return None
                last = msg
                log.warning("[%s] attempt %d failed for %d: %s", SERVICE, attempt, year, msg[:200])
                time.sleep(30 * attempt)
        else:
            raise ServiceError(SERVICE, f"ERA5-Land request for {year} failed: {last}",
                               "CDS may be busy; re-run later (cached years are reused).")
        try:
            self._validate(tmp)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise ServiceError(SERVICE, f"Downloaded ERA5-Land file for {year} is invalid: {exc}")
        tmp.replace(target)
        return target

    def run(self, start_year: int, end_year: int) -> Path:
        self.authenticate()
        parts = []
        for year in range(start_year, end_year + 1):
            p = self._fetch_year(year)
            if p is not None:
                parts.append(_open_any(p)[["t2m", "tp"]])
                log.info("[%s] %d ready", SERVICE, year)
        if not parts:
            raise ServiceError(SERVICE, "No ERA5-Land data retrieved.")
        ds = xr.concat(parts, dim="time").sortby("time")
        ds = ds.sel(time=~ds.get_index("time").duplicated())
        times = pd.DatetimeIndex(ds["time"].values).to_period("M").to_timestamp()
        ds = ds.assign_coords(time=times)
        days = xr.DataArray(times.days_in_month.values, dims="time", coords={"time": times})
        out = xr.Dataset({
            "rain_mm": (ds["tp"] * 1000.0 * days).astype("float32"),
            "temp_c": (ds["t2m"] - 273.15).astype("float32"),
        })
        out["rain_mm"].attrs = {"units": "mm/month", "source": "ERA5-Land total_precipitation"}
        out["temp_c"].attrs = {"units": "degC", "source": "ERA5-Land 2m_temperature"}
        path = self.out_dir / "era5_land_monthly.nc"
        out.to_netcdf(path)
        n_valid = int(np.isfinite(out["rain_mm"]).any(dim=[d for d in out["rain_mm"].dims if d != "time"]).sum())
        log.info("[%s] %d months processed -> %s", SERVICE, n_valid, path.name)
        return path
