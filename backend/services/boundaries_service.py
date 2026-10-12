"""BBMP 243-ward boundaries (no credentials needed).

Source order:
 1. `paths.wards_override` in config/project.yaml (any GeoJSON/SHP/KML/GPKG)
 2. any ward file the user placed in data/boundaries/
 3. download from `wards.source_url` (datameet Municipal_Spatial_Data, KGIS 243 wards)
Output: data/processed/wards_243.geojson with columns ward_id, ward_name, geometry (EPSG:4326).
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import requests

from backend.config import Settings
from backend.errors import DataValidationError
from backend.http_utils import request_with_retry, atomic_write

log = logging.getLogger(__name__)
SERVICE = "Ward boundaries"
EXTS = {".geojson", ".json", ".shp", ".kml", ".gpkg"}


def _pick(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    lower = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


class BoundariesService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cfg = settings.section("wards")
        self.local_dir = settings.dir("boundaries")

    def _source(self) -> Path:
        override = self.settings.section("paths").get("wards_override")
        if override:
            p = (self.settings.root / override)
            if not p.exists():
                raise DataValidationError(f"wards_override file not found: {p}")
            return p
        local = sorted(p for p in self.local_dir.iterdir() if p.suffix.lower() in EXTS)
        if local:
            return local[0]
        dest = self.settings.dir("cache", "wards") / "BBMP_wards.geojson"
        if not dest.exists():
            log.info("[%s] downloading %s", SERVICE, self.cfg["source_url"])
            resp = request_with_retry(SERVICE, "GET", self.cfg["source_url"],
                                      session=requests.Session(), timeout=(20, 120))
            atomic_write(dest, resp.content)
        return dest

    def run(self) -> Path:
        src = self._source()
        gdf = gpd.read_file(src)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        gdf = gdf.to_crs("EPSG:4326")
        id_col = _pick(gdf.columns, self.cfg.get("id_field_candidates", []))
        name_col = _pick(gdf.columns, self.cfg.get("name_field_candidates", []))
        if id_col is None:
            raise DataValidationError(
                f"Could not find a ward-number column in {src.name}; columns: {list(gdf.columns)}. "
                "Add the correct name to wards.id_field_candidates in config/project.yaml.")
        out = gpd.GeoDataFrame({
            "ward_id": gdf[id_col].astype(str).str.strip(),
            "ward_name": gdf[name_col].astype(str).str.strip() if name_col else gdf[id_col].astype(str),
        }, geometry=gdf.geometry.make_valid(), crs="EPSG:4326")
        out = out.dissolve(by="ward_id", aggfunc="first", as_index=False)
        expected = int(self.cfg.get("expected_count", 243))
        if len(out) != expected:
            raise DataValidationError(
                f"{src.name} has {len(out)} wards; expected {expected}. "
                "Provide the 243-ward BBMP (2022 delimitation) boundaries via data/boundaries/.")
        out["sort"] = out["ward_id"].str.extract(r"(\d+)")[0].astype(float)
        out = out.sort_values("sort").drop(columns="sort").reset_index(drop=True)
        path = self.settings.processed_dir / "wards_243.geojson"
        out.to_file(path, driver="GeoJSON")
        log.info("[%s] %d wards from %s", SERVICE, len(out), src.name)
        return path
