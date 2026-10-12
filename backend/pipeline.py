"""JalaJagruti AI end-to-end pipeline.

    python -m backend.pipeline                 # run everything
    python -m backend.pipeline --serve         # ...then start the FastAPI backend
    python -m backend.pipeline --check         # validation only (structure, data, .env)
    python -m backend.pipeline --from features # resume from a stage
    python -m backend.pipeline --only era5     # run a single stage

Each stage writes its outputs to data/ and records itself in
data/outputs/run_manifest.json. Downloads are cached, so re-runs are cheap.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from datetime import datetime, timezone

import pandas as pd

from backend.config import get_settings, validate_project_structure
from backend.errors import ConfigurationError, JalaJagrutiError

log = logging.getLogger("jalajagruti")


def _years(settings):
    t = settings.section("time")
    start = pd.Timestamp(t["data_start"])
    now = pd.Timestamp.utcnow().tz_localize(None)
    return start, now


# ---------------------------------------------------------------------------- stages
def st_validate(s, ctx):
    problems = validate_project_structure(s)
    from backend.data.groundwater_ingest import discover_files
    files = discover_files(s.groundwater_dir)
    ctx["groundwater_files"] = [str(f.relative_to(s.root)) for f in files]
    creds = s.credential_status()
    missing = [k for k, v in creds.items() if not v]
    if missing:
        s.require(*missing)  # raises with actionable message
    for p in problems:
        log.warning(p)
    return {"groundwater_files": ctx["groundwater_files"], "credentials_present": creds}


def st_ingest(s, ctx):
    from backend.data.groundwater_ingest import ingest
    _, report = ingest(s)
    return {k: report[k] for k in ("n_files", "stations", "rows_after_dedup", "date_min", "date_max")}


def st_qc(s, ctx):
    from backend.data.groundwater_qc import run_qc
    _, _, report = run_qc(s)
    return {k: report[k] for k in ("record_counts", "stations_eligible", "monthly_records", "month_range")}


def st_sentinel2(s, ctx):
    from backend.services.copernicus_service import CopernicusService
    start, now = _years(s)
    idx = CopernicusService(s).run(str(start.date()), str(now.date()))
    return {"composites": len(idx)}


def st_viirs(s, ctx):
    from backend.services.viirs_service import ViirsService
    start, now = _years(s)
    idx = ViirsService(s).run(start.year, now.year)
    return {"months": len(idx)}


def st_era5(s, ctx):
    from backend.services.era5_service import Era5Service
    _, now = _years(s)
    start_year = min(int(s.section("time")["climatology_start_year"]), _years(s)[0].year)
    path = Era5Service(s).run(start_year, now.year)
    return {"file": str(path.relative_to(s.root))}


def st_wards(s, ctx):
    from backend.services.boundaries_service import BoundariesService
    path = BoundariesService(s).run()
    return {"file": str(path.relative_to(s.root))}


def st_join(s, ctx):
    from backend.data.spatial_join import build_ward_station_weights
    stations = pd.read_csv(s.processed_dir / "stations.csv")
    w = build_ward_station_weights(s, stations)
    return w.drop_duplicates("ward_id")["basis"].value_counts().to_dict()


def st_features(s, ctx):
    from backend.data.features import build_features
    r = build_features(s)
    return {k: v for k, v in r.items() if k != "patch_valid_fraction_mean_by_period"}


def st_quality(s, ctx):
    """Aggregate data-quality report; blocks training if inputs are unusable."""
    reports = {}
    for name in ["groundwater_schema_report", "groundwater_qc_report", "spatial_join_report",
                 "features_report"]:
        p = s.reports_dir / f"{name}.json"
        if p.exists():
            reports[name] = json.loads(p.read_text())
    f = reports.get("features_report", {})
    issues = []
    if f.get("panel_rain_available_share", 0) < 0.5:
        issues.append("ERA5-Land rainfall covers < 50% of station-months.")
    if f.get("panel_depth_observed_share", 0) < 0.2:
        issues.append("Groundwater observations cover < 20% of station-months.")
    reports["blocking_issues"] = issues
    with (s.reports_dir / "data_quality_report.json").open("w") as fh:
        json.dump(reports, fh, indent=2, default=str)
    if issues:
        raise JalaJagrutiError("Data-quality checks failed:\n  - " + "\n  - ".join(issues))
    return {"blocking_issues": 0}


def st_model(s, ctx):
    from backend.ml.train import run_modeling
    ctx["metrics"] = run_modeling(s)
    with (s.outputs_dir / "model_metrics.json").open("w") as fh:
        json.dump(ctx["metrics"], fh, indent=2, default=str)
    m = ctx["metrics"]["test_metrics_one_step"]
    return {"test_rmse_m": m["cnn_lstm"].get("rmse_m"),
            "validated_horizon_months": ctx["metrics"]["validated_horizon_months"]}


def st_export(s, ctx):
    from backend.outputs.export import export_outputs
    metrics = ctx.get("metrics")
    if metrics is None:
        p = s.outputs_dir / "model_metrics.json"
        if not p.exists():
            raise JalaJagrutiError("model_metrics.json not found; run the 'model' stage first.")
        metrics = json.loads(p.read_text())
    return export_outputs(s, metrics)


STAGES = [
    ("validate", "Validate project structure, GroundWaterDataset/ and .env", st_validate),
    ("ingest", "Inspect & standardise groundwater files", st_ingest),
    ("qc", "Groundwater quality control & monthly aggregation", st_qc),
    ("sentinel2", "Sentinel-2 L2A NDVI/NDBI composites (Copernicus)", st_sentinel2),
    ("viirs", "VIIRS VNP46A3 night-time lights (NASA LAADS)", st_viirs),
    ("era5", "ERA5-Land rainfall & temperature (CDS)", st_era5),
    ("wards", "BBMP 243-ward boundaries", st_wards),
    ("join", "Spatial join stations -> wards", st_join),
    ("features", "Temporal sync, CNN patches, LSTM panel", st_features),
    ("quality", "Data-quality checks", st_quality),
    ("model", "Train/evaluate CNN-LSTM, 2025 prediction, 2026-2030 forecast", st_model),
    ("export", "Risk scores, ward CSVs, 243-ward GeoJSON", st_export),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.pipeline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    names = [n for n, _, _ in STAGES]
    ap.add_argument("--from", dest="start", choices=names)
    ap.add_argument("--only", choices=names)
    ap.add_argument("--check", action="store_true", help="run validation only")
    ap.add_argument("--serve", action="store_true", help="start the API after the pipeline")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    s = get_settings()
    if args.check:
        sel = ["validate"]
    elif args.only:
        sel = [args.only]
    else:
        i = names.index(args.start) if args.start else 0
        sel = names[i:]
    manifest_path = s.outputs_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"stages": {}}
    ctx: dict = {}
    for i, (name, desc, fn) in enumerate(STAGES, 1):
        if name not in sel:
            continue
        log.info("=== [%d/%d] %s ===", i, len(STAGES), desc)
        t0 = time.time()
        try:
            result = fn(s, ctx)
            manifest["stages"][name] = {"status": "ok", "seconds": round(time.time() - t0, 1),
                                        "finished": datetime.now(timezone.utc).isoformat(),
                                        "result": result}
        except JalaJagrutiError as exc:
            manifest["stages"][name] = {"status": "failed", "error": str(exc),
                                        "finished": datetime.now(timezone.utc).isoformat()}
            manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
            log.error("Stage '%s' failed:\n%s", name, exc)
            log.error("Fix the issue above, then resume with: python -m backend.pipeline --from %s", name)
            return 2
        except Exception as exc:
            manifest["stages"][name] = {"status": "failed", "error": repr(exc),
                                        "finished": datetime.now(timezone.utc).isoformat()}
            manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
            log.error("Stage '%s' crashed: %r\n%s", name, exc, traceback.format_exc())
            return 3
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    log.info("Pipeline finished. Outputs in %s", s.outputs_dir)
    if args.serve:
        import uvicorn
        api = s.section("api")
        uvicorn.run("backend.api.main:app", host=api.get("host", "127.0.0.1"), port=int(api.get("port", 8000)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
