"""FastAPI backend: serves only what the pipeline saved to data/outputs.

    uvicorn backend.api.main:app --reload
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings

settings = get_settings()
OUT: Path = settings.outputs_dir
app = FastAPI(title="JalaJagruti AI", version="1.0.0",
              description="Bengaluru ward-level groundwater predictions (CNN-LSTM)")
app.add_middleware(CORSMiddleware, allow_origins=settings.section("api").get("cors_origins", ["*"]),
                   allow_methods=["GET"], allow_headers=["*"])

NOT_READY = ("Pipeline outputs not found ({}). Run `python -m backend.pipeline` first; "
             "see data/outputs/run_manifest.json for stage status.")


def _need(path: Path) -> Path:
    if not path.exists():
        raise HTTPException(status_code=503, detail=NOT_READY.format(path.name))
    return path


def _clean(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in r.items()} for r in df.to_dict(orient="records")]


@lru_cache(maxsize=4)
def _load_csv(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"ward_id": str})


@lru_cache(maxsize=2)
def _load_ts(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["ward_id"] = df["ward_id"].astype(str)
    df["month"] = pd.to_datetime(df["month"]).dt.strftime("%Y-%m")
    return df


def ward_table() -> pd.DataFrame:
    p = _need(OUT / "ward_predictions_all_years.csv")
    return _load_csv(str(p), p.stat().st_mtime)


@app.get("/api/health")
def health():
    return {"status": "ok", "outputs_ready": (OUT / "wards_predictions_243.geojson").exists(),
            "credentials_present": settings.credential_status()}


@app.get("/api/status")
def status():
    p = OUT / "run_manifest.json"
    return json.loads(p.read_text()) if p.exists() else {"stages": {}}


@app.get("/api/years")
def years():
    df = ward_table()
    return {"years": sorted(int(y) for y in df["year"].unique())}


@app.get("/api/wards/geojson")
def wards_geojson():
    p = _need(OUT / "wards_predictions_243.geojson")
    data = json.loads(p.read_text())
    return data


@app.get("/api/wards")
def wards(year: int = Query(..., ge=2000, le=2100)):
    df = ward_table()
    sub = df[df["year"] == year]
    if sub.empty:
        raise HTTPException(404, f"No outputs for year {year}")
    return _records(sub)


@app.get("/api/wards/{ward_id}")
def ward(ward_id: str):
    df = ward_table()
    sub = df[df["ward_id"] == ward_id].sort_values("year")
    if sub.empty:
        raise HTTPException(404, f"Unknown ward {ward_id}")
    return {"ward_id": ward_id, "ward_name": sub["ward_name"].iloc[0], "years": _records(sub)}


@app.get("/api/wards/{ward_id}/timeseries")
def ward_timeseries(ward_id: str):
    p = _need(OUT / "ward_monthly_timeseries.parquet")
    ts = _load_ts(str(p), p.stat().st_mtime)
    sub = ts[ts["ward_id"] == ward_id].sort_values("month")
    hist = sub[sub["kind"] == "history"][["month", "actual_m", "pred_m", "split"]]
    fc = sub[sub["kind"] == "forecast"][["month", "pred_m", "lower_m", "upper_m", "actual_m",
                                         "within_validated_horizon"]]
    return {"ward_id": ward_id, "history": _records(hist), "forecast": _records(fc),
            "available": not sub.empty}


@app.get("/api/metrics")
def metrics():
    p = _need(OUT / "model_metrics.json")
    m = json.loads(p.read_text())
    m.pop("loss_curves", None)
    return m


@app.get("/api/data-quality")
def data_quality():
    p = _need(settings.reports_dir / "data_quality_report.json")
    return json.loads(p.read_text())
