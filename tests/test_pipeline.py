"""Tests.

IMPORTANT: the synthetic arrays below are *test fixtures* written to a pytest
temporary directory to exercise code paths. They are never written to the
project's data/ folder and the production pipeline never generates data.

Run: pytest -q
"""
from __future__ import annotations

import copy
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
import xarray as xr
from shapely.geometry import box

from backend.config import get_settings
from backend.errors import ConfigurationError


@pytest.fixture
def settings(tmp_path):
    s = copy.deepcopy(get_settings())
    s.raw["paths"]["data_dir"] = str(tmp_path / "data")
    s.raw["paths"]["groundwater_dir"] = str(tmp_path / "gw")
    s.raw["region"]["training_bbox"] = [77.50, 12.90, 77.62, 13.02]
    s.raw["model"].update(ensemble_size=2, epochs=3, patience=2, patch_px=8, min_test_samples=5)
    s.raw["wards"]["expected_count"] = 4
    return s


# ---------------------------------------------------------------- unit tests
def test_missing_credentials_message(settings):
    settings.secrets = {k: None for k in settings.secrets}
    with pytest.raises(ConfigurationError) as e:
        settings.require("CDS_API_KEY")
    assert "CDS_API_KEY" in str(e.value) and ".env" in str(e.value)


def test_schema_inference_unusual_columns(settings, tmp_path):
    from backend.data.groundwater_ingest import infer_schema
    gw = tmp_path / "gw"; gw.mkdir()
    df = pd.DataFrame({"Well Name": ["A"] * 5 + ["B"] * 5,
                       "Y Lat": [12.95] * 5 + [12.97] * 5, "X Long": [77.55] * 5 + [77.57] * 5,
                       "Obs Date": pd.date_range("2022-01-01", periods=10).strftime("%d/%m/%Y"),
                       "Depth to water (mbgl)": np.linspace(5, 9, 10)})
    df.columns = ["Well Name", "Latitude (deg)", "Longitude (deg)", "Obs Date", "Depth to water (mbgl)"]
    p = gw / "odd.csv"; df.to_csv(p, index=False)
    sch = infer_schema(p)
    assert sch.mapping["level"] == "Depth to water (mbgl)"
    assert sch.mapping["time"] == "Obs Date" and sch.date_format == "%d/%m/%Y"
    assert sch.sign_convention == "positive_below_ground"


def test_risk_is_deterministic_and_flags_missing(settings):
    from backend.ml.risk import risk_scores
    df = pd.DataFrame({"depth_m": [3, 22.5, 50, np.nan], "trend_m_per_year": [0, 1, 3, 1],
                       "ndbi": [-0.3, np.nan, 0.3, 0]})
    r1, r2 = risk_scores(df, settings.section("risk")), risk_scores(df, settings.section("risk"))
    pd.testing.assert_frame_equal(r1, r2)
    assert r1.loc[0, "risk_score"] == 0 and r1.loc[2, "risk_score"] == 1
    assert r1.loc[3, "risk_class"] == "INSUFFICIENT_INPUT_DATA"
    assert "renormalised" in r1.loc[1, "risk_note"]


def test_flatline_and_sentinel_qc(settings):
    from backend.data.groundwater_qc import _flatline_mask
    m = _flatline_mask(np.array([1, 2, 2, 2, 2, 3.0]), 4)
    assert m.tolist() == [False, True, True, True, True, False]


def test_viirs_tile_lookup():
    from backend.services.viirs_service import tiles_for_bbox
    assert tiles_for_bbox((77.2, 12.6, 78.0, 13.4)) == ["h25v07"]


# ---------------------------------------------------------------- smoke test
def _write_fixture(s, tmp_path):
    rng = np.random.default_rng(0)
    proc = s.processed_dir
    minx, miny, maxx, maxy = s.training_bbox
    # wards: 2x2 grid
    xs, ys = np.linspace(minx + .01, maxx - .01, 3), np.linspace(miny + .01, maxy - .01, 3)
    polys = [box(xs[i], ys[j], xs[i + 1], ys[j + 1]) for i in range(2) for j in range(2)]
    gpd.GeoDataFrame({"ward_id": ["1", "2", "3", "4"], "ward_name": list("ABCD")}, geometry=polys,
                     crs="EPSG:4326").to_file(proc / "wards_243.geojson", driver="GeoJSON")
    # stations + monthly levels
    months = pd.date_range("2021-01-01", "2026-09-01", freq="MS")
    st, rows = [], []
    for k in range(12):
        lat, lon = rng.uniform(miny + .015, maxy - .015), rng.uniform(minx + .015, maxx - .015)
        sid = f"S{k}@{lat:.4f},{lon:.4f}"
        st.append({"station_id": sid, "station_name": f"S{k}", "lat": lat, "lon": lon,
                   "raw_records": 1, "valid_months": len(months), "eligible": True, "status": "OK"})
        base = rng.uniform(5, 25)
        for i, m in enumerate(months):
            rows.append({"station_id": sid, "month": m, "valid_days": 20,
                         "depth_bgl_m": base + 2 * np.sin(2 * np.pi * m.month / 12) + .05 * i})
    pd.DataFrame(st).to_csv(proc / "stations.csv", index=False)
    pd.DataFrame(rows).to_parquet(proc / "groundwater_monthly.parquet", index=False)
    # rasters
    from backend.services.copernicus_service import Grid, composite_periods
    g = Grid.from_settings(s)
    (proc / "sentinel2").mkdir(exist_ok=True); (proc / "viirs").mkdir(exist_ok=True)
    prof = dict(driver="GTiff", width=g.width, height=g.height, crs="EPSG:4326",
                transform=g.transform, dtype="float32", nodata=np.nan)
    for label, t0, _ in composite_periods("2021-01-01", "2026-09-30", "quarterly"):
        with rasterio.open(proc / "sentinel2" / f"s2_indices_{label}.tif", "w", count=3, **prof) as d:
            d.write(rng.uniform(-.2, .6, (3, g.height, g.width)).astype("float32"))
    for m in months:
        with rasterio.open(proc / "viirs" / f"ntl_{m:%Y-%m}.tif", "w", count=1, **prof) as d:
            d.write(rng.uniform(0, 50, (1, g.height, g.width)).astype("float32"))
    # ERA5
    t = pd.date_range("2011-01-01", "2026-08-01", freq="MS")
    lat = np.arange(maxy + .2, miny - .2, -.1); lon = np.arange(minx - .2, maxx + .2, .1)
    shp = (len(t), len(lat), len(lon))
    xr.Dataset({"rain_mm": (("time", "latitude", "longitude"), rng.gamma(2, 40, shp).astype("float32")),
                "temp_c": (("time", "latitude", "longitude"), rng.normal(24, 2, shp).astype("float32"))},
               coords={"time": t, "latitude": lat, "longitude": lon}).to_netcdf(
        s.dir("processed", "era5") / "era5_land_monthly.nc")


def test_end_to_end_smoke(settings, tmp_path):
    from backend.data.features import build_features
    from backend.data.spatial_join import build_ward_station_weights
    from backend.ml.train import run_modeling
    from backend.outputs.export import export_outputs
    _write_fixture(settings, tmp_path)
    settings.raw["region"]["idw_max_distance_km"] = 20
    build_ward_station_weights(settings, pd.read_csv(settings.processed_dir / "stations.csv"))
    build_features(settings)
    metrics = run_modeling(settings)
    assert metrics["test_metrics_one_step"]["cnn_lstm"]["n"] > 0
    assert metrics["validated_horizon_months"] >= 1
    summary = export_outputs(settings, metrics)
    gj = json.loads((settings.outputs_dir / "wards_predictions_243.geojson").read_text())
    assert len(gj["features"]) == 4 and "depth_m_2030" in gj["features"][0]["properties"]
    wy = pd.read_csv(settings.outputs_dir / "ward_predictions_all_years.csv")
    assert set(wy["year"]) == set(range(2025, 2031))
    assert set(wy.loc[wy["year"] == 2025, "prediction_status"]) == {"PREDICTED_OUT_OF_SAMPLE"}
    assert "FORECAST_BEYOND_VALIDATED_HORIZON" in set(wy.loc[wy["year"] == 2030, "prediction_status"])
