"""Aggregate station predictions to the 243 wards and write CSV / GeoJSON outputs."""
from __future__ import annotations

import json
import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from backend.config import Settings
from backend.data.spatial_join import aggregate_to_wards
from backend.errors import (INSUFFICIENT, PRED_STATUS_FORECAST, PRED_STATUS_FORECAST_EXTRAP,
                            PRED_STATUS_PREDICTED, SPATIAL_NONE)
from backend.ml.dataset import _period_start
from backend.ml.risk import risk_scores

log = logging.getLogger(__name__)
MIN_MONTHS_ANNUAL = 6


def _station_trend(frame_obs: pd.DataFrame, end_year: int) -> pd.Series:
    """Observed linear trend (m/yr) of monthly depth up to end_year (>= 24 months)."""
    out = {}
    d = frame_obs[frame_obs["month"].dt.year <= end_year].dropna(subset=["depth_bgl_m"])
    for sid, g in d.groupby("station_id"):
        if len(g) < 24:
            continue
        x = (g["month"] - g["month"].min()).dt.days.to_numpy() / 365.25
        out[sid] = float(np.polyfit(x, g["depth_bgl_m"].to_numpy(), 1)[0])
    return pd.Series(out, name="trend_m_per_year")


def station_year_table(settings: Settings, metrics_result: dict) -> pd.DataFrame:
    tcfg = settings.section("time")
    py, fy_end = int(tcfg["prediction_year"]), int(tcfg["forecast_end_year"])
    one = pd.read_parquet(settings.processed_dir / "station_one_step_predictions.parquet")
    fc = pd.read_parquet(settings.processed_dir / "station_forecasts.parquet")
    monthly = pd.read_parquet(settings.processed_dir / "groundwater_monthly.parquet")
    test_rmse = metrics_result["test_metrics_one_step"]["cnn_lstm"]["rmse_m"]

    rows = []
    # ---- prediction year (out-of-sample one-step) --------------------------------
    t = one[one["split"] == "test"].copy()
    sig = np.sqrt(t["ens_std_m"] ** 2 + test_rmse ** 2)
    t["lower_m"], t["upper_m"] = (t["pred_m"] - 1.96 * sig).clip(lower=0), t["pred_m"] + 1.96 * sig
    obs_py = monthly[monthly["month"].dt.year == py].groupby("station_id")["depth_bgl_m"].agg(["mean", "size"])
    for sid, g in t.groupby("station_id"):
        ok = len(g) >= MIN_MONTHS_ANNUAL
        a = obs_py.loc[sid] if sid in obs_py.index else None
        may = g[g["month"].dt.month == 5]
        rows.append({"station_id": sid, "year": py,
                     "depth_m": g["pred_m"].mean() if ok else np.nan,
                     "lower_m": g["lower_m"].mean() if ok else np.nan,
                     "upper_m": g["upper_m"].mean() if ok else np.nan,
                     "premonsoon_may_m": float(may["pred_m"].iloc[0]) if len(may) else np.nan,
                     "actual_m": float(a["mean"]) if a is not None and a["size"] >= MIN_MONTHS_ANNUAL else np.nan,
                     "actual_months": int(a["size"]) if a is not None else 0,
                     "months_predicted": len(g),
                     "status": PRED_STATUS_PREDICTED if ok else INSUFFICIENT})
    # ---- forecast years --------------------------------------------------------
    for (sid, year), g in fc.groupby(["station_id", fc["month"].dt.year]):
        if year > fy_end:
            continue
        may = g[g["month"].dt.month == 5]
        act = g["actual_m"].dropna()
        rows.append({"station_id": sid, "year": int(year), "depth_m": g["pred_m"].mean(),
                     "lower_m": g["lower_m"].mean(), "upper_m": g["upper_m"].mean(),
                     "premonsoon_may_m": float(may["pred_m"].iloc[0]) if len(may) else np.nan,
                     "actual_m": float(act.mean()) if len(act) else np.nan,
                     "actual_months": int(len(act)), "months_predicted": len(g),
                     "status": PRED_STATUS_FORECAST if g["within_validated_horizon"].all()
                     else PRED_STATUS_FORECAST_EXTRAP})
    sy = pd.DataFrame(rows)

    # ---- trends ------------------------------------------------------------------
    trend_py = _station_trend(monthly, py)
    base = sy[sy["year"] == py].set_index("station_id")
    baseline = base["actual_m"].fillna(base["depth_m"])
    def trend(r):
        if r["year"] == py:
            return trend_py.get(r["station_id"], np.nan)
        b = baseline.get(r["station_id"], np.nan)
        return (r["depth_m"] - b) / (r["year"] - py) if np.isfinite(b) and np.isfinite(r["depth_m"]) else np.nan
    sy["trend_m_per_year"] = sy.apply(trend, axis=1)
    return sy


def ward_ndbi_by_year(settings: Settings, years: list[int]) -> pd.DataFrame:
    z = pd.read_csv(settings.processed_dir / "ward_urban_indices.csv", dtype={"ward_id": str})
    z["start"] = z["period"].map(_period_start)
    rows = []
    for y in years:
        end = pd.Timestamp(y, 12, 31)
        sub = z[z["start"] <= end].dropna(subset=["ndbi"])
        last = sub.sort_values("start").groupby("ward_id").tail(4)   # latest 4 composites
        agg = last.groupby("ward_id").agg(ndbi=("ndbi", "mean"), ndvi=("ndvi", "mean"),
                                          ntl_log=("ntl_log", "mean"), urban_ref_end=("period", "max"))
        rows.append(agg.reset_index().assign(year=y))
    return pd.concat(rows, ignore_index=True)


def export_outputs(settings: Settings, metrics_result: dict) -> dict:
    tcfg = settings.section("time")
    years = list(range(int(tcfg["prediction_year"]), int(tcfg["forecast_end_year"]) + 1))
    out = settings.outputs_dir
    wards = gpd.read_file(settings.processed_dir / "wards_243.geojson")
    wards["ward_id"] = wards["ward_id"].astype(str)
    weights = pd.read_csv(settings.processed_dir / "ward_station_weights.csv", dtype={"ward_id": str})
    stations = pd.read_csv(settings.processed_dir / "stations.csv")

    sy = station_year_table(settings, metrics_result)
    sy = sy.merge(stations[["station_id", "station_name", "lat", "lon"]], on="station_id", how="left")
    sy.to_csv(out / "station_predictions_all_years.csv", index=False)

    val_cols = ["depth_m", "lower_m", "upper_m", "premonsoon_may_m", "actual_m", "trend_m_per_year"]
    good = sy[sy["status"] != INSUFFICIENT]
    wy = aggregate_to_wards(good[["station_id", "year", *val_cols]], weights, val_cols, ["year"])
    status = good.groupby("year")["status"].agg(lambda s: s.mode().iloc[0]).to_dict()

    basis = weights.groupby("ward_id").agg(
        spatial_basis=("basis", "first"),
        n_stations=("station_id", lambda s: int(s.notna().sum())),
        nearest_station_km=("distance_km", "min"),
        stations=("station_id", lambda s: ";".join(x for x in s.dropna())),
    ).reset_index()

    grid = pd.MultiIndex.from_product([wards["ward_id"], years], names=["ward_id", "year"]).to_frame(index=False)
    wy = grid.merge(wy, on=["ward_id", "year"], how="left")
    wy = wy.merge(wards[["ward_id", "ward_name"]], on="ward_id").merge(basis, on="ward_id", how="left")
    wy = wy.merge(ward_ndbi_by_year(settings, years), on=["ward_id", "year"], how="left")
    has = wy["depth_m"].notna() & (wy["spatial_basis"] != SPATIAL_NONE)
    wy["prediction_status"] = np.where(has, wy["year"].map(status), INSUFFICIENT)
    for c in val_cols:
        wy.loc[~has, c] = np.nan
    risk = risk_scores(wy, settings.section("risk"))
    wy = pd.concat([wy, risk], axis=1)
    wy.loc[~has, ["risk_score"]] = np.nan
    wy.loc[~has, "risk_class"] = INSUFFICIENT
    num = wy.select_dtypes("number").columns.difference(["year", "n_stations"])
    wy[num] = wy[num].round(3)

    py = int(tcfg["prediction_year"])
    cols = ["ward_id", "ward_name", "year", "prediction_status", "spatial_basis", "n_stations",
            "nearest_station_km", "depth_m", "lower_m", "upper_m", "premonsoon_may_m", "actual_m",
            "trend_m_per_year", "ndbi", "ndvi", "ntl_log", "urban_ref_end", "risk_score", "risk_class",
            "risk_note", "stations"]
    wy = wy[cols].sort_values(["year", "ward_id"], key=lambda s: pd.to_numeric(s, errors="coerce")
                              if s.name == "ward_id" else s)
    wy.to_csv(out / "ward_predictions_all_years.csv", index=False)
    wy[wy["year"] == py].to_csv(out / f"ward_predictions_{py}.csv", index=False)
    wy[wy["year"] > py].to_csv(out / f"ward_forecasts_{py + 1}_{years[-1]}.csv", index=False)

    # ---- GeoJSON (243 features, one property set per year) ------------------------
    g = wards[["ward_id", "ward_name", "geometry"]].merge(basis, on="ward_id", how="left")
    for y in years:
        sub = wy[wy["year"] == y].set_index("ward_id")
        for c in ["depth_m", "lower_m", "upper_m", "actual_m", "trend_m_per_year", "risk_score",
                  "risk_class", "prediction_status"]:
            g[f"{c}_{y}"] = g["ward_id"].map(sub[c])
    g["geometry"] = g.geometry.simplify(0.00005, preserve_topology=True)
    gj = out / "wards_predictions_243.geojson"
    g.to_file(gj, driver="GeoJSON")

    # ---- ward monthly time series (history one-step + forecast) -------------------
    one = pd.read_parquet(settings.processed_dir / "station_one_step_predictions.parquet")
    fc = pd.read_parquet(settings.processed_dir / "station_forecasts.parquet")
    hist = aggregate_to_wards(one[["station_id", "month", "actual_m", "pred_m"]], weights,
                              ["actual_m", "pred_m"], ["month"]).assign(kind="history")
    splits = one.groupby("month")["split"].agg(lambda s: s.mode().iloc[0])
    hist["split"] = hist["month"].map(splits)
    fut = aggregate_to_wards(fc[["station_id", "month", "pred_m", "lower_m", "upper_m", "actual_m"]],
                             weights, ["pred_m", "lower_m", "upper_m", "actual_m"], ["month"]).assign(kind="forecast")
    hz = fc.drop_duplicates("month").set_index("month")["within_validated_horizon"]
    fut["within_validated_horizon"] = fut["month"].map(hz)
    ts = pd.concat([hist, fut], ignore_index=True)
    no_basis = basis.loc[basis["spatial_basis"] == SPATIAL_NONE, "ward_id"]
    ts = ts[~ts["ward_id"].isin(no_basis)]
    ts.to_parquet(out / "ward_monthly_timeseries.parquet", index=False)

    with (out / "model_metrics.json").open("w") as fh:
        json.dump(metrics_result, fh, indent=2, default=str)

    summary = {
        "wards": int(len(wards)), "years": years,
        "wards_with_values_by_year": wy[wy["prediction_status"] != INSUFFICIENT].groupby("year").size().to_dict(),
        "status_by_year": wy.groupby(["year", "prediction_status"]).size().unstack(fill_value=0).to_dict("index"),
        "files": sorted(p.name for p in out.iterdir() if p.is_file()),
    }
    log.info("[export] %s", summary["wards_with_values_by_year"])
    return summary
