"""Train, evaluate and forecast with a CNN-LSTM ensemble.

Two model sets are trained (chronological splits, no shuffling across time):

  evaluation model : train <= eval_train_end, early-stop on (.., eval_val_end],
                     test = prediction_year  -> out-of-sample 2025 predictions & metrics,
                     plus a 12-month recursive rollout from eval_val_end (forecast skill)
  forecast model   : train <= final_train_end, early-stop on (.., final_val_end],
                     recursive rollout from final_val_end to forecast_end_year;
                     months with observations (e.g. Jan-Sep 2026) are a genuine
                     forecast hold-out.

Future forcing is not known, so forecasts use per-station ERA5-Land monthly
climatology and persistence of the most recent same-season satellite composite.
This is recorded as the covariate scenario in every forecast row.
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from torch import nn

from backend.config import Settings
from backend.errors import InsufficientDataError
from backend.data.features import month_to_period
from backend.ml.dataset import (SEQ_FEATURES, Normalizer, SampleSet, _period_start, build_samples,
                                normalize_patches, prepare_station_frame)
from backend.ml.model import CNNLSTM

log = logging.getLogger(__name__)
SCENARIO = "ERA5-Land monthly climatology + same-season satellite persistence"


def set_seed(seed: int):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ---------------------------------------------------------------------------- metrics
def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    m = np.isfinite(y) & np.isfinite(p)
    y, p = y[m], p[m]
    if len(y) == 0:
        return {"n": 0}
    err = p - y
    ss_res, ss_tot = float((err ** 2).sum()), float(((y - y.mean()) ** 2).sum())
    return {"n": int(len(y)), "rmse_m": float(np.sqrt((err ** 2).mean())),
            "mae_m": float(np.abs(err).mean()), "bias_m": float(err.mean()),
            "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else None}


# ---------------------------------------------------------------------------- training
@dataclass
class Bundle:
    norm: Normalizer
    frame: pd.DataFrame
    patches: np.ndarray       # normalised, station x period x C x P x P
    valid: np.ndarray
    periods: list[str]
    station_rows: dict
    samples: SampleSet
    drops: dict


def make_bundle(settings: Settings, train_end: pd.Timestamp) -> Bundle:
    mcfg, gcfg = settings.section("model"), settings.section("groundwater")
    mode = settings.section("sentinel2").get("composite", "quarterly")
    panel = pd.read_parquet(settings.processed_dir / "panel.parquet")
    z = np.load(settings.processed_dir / "patches.npz", allow_pickle=True)
    periods = [str(p) for p in z["periods"]]
    station_rows = {sid: i for i, sid in enumerate(z["station_ids"])}
    norm = Normalizer.fit(panel, train_end, z["patches"], periods)
    frame = prepare_station_frame(panel, norm, int(gcfg["max_interpolated_gap_months"]))
    patches = normalize_patches(z["patches"], norm)
    samples, drops = build_samples(frame, station_rows, periods, z["valid"], int(mcfg["lookback_months"]),
                                   float(settings.section("sentinel2")["min_valid_patch_fraction"]),
                                   lambda m: month_to_period(m, mode))
    return Bundle(norm, frame, patches, z["valid"], periods, station_rows, samples, drops)


def _tensors(s: SampleSet, patches: np.ndarray, dev):
    seq = torch.from_numpy(s.seq).to(dev)
    pt = torch.from_numpy(patches[s.patch_idx[:, 0], s.patch_idx[:, 1]]).to(dev)
    return seq, pt, torch.from_numpy(s.y).to(dev)


def train_member(train: SampleSet, val: SampleSet, patches: np.ndarray, cfg: dict, seed: int,
                 fixed_epochs: int | None = None) -> tuple[CNNLSTM, dict]:
    set_seed(seed)
    dev = device()
    model = CNNLSTM(len(SEQ_FEATURES), hidden=int(cfg["lstm_hidden"]), layers=int(cfg["lstm_layers"]),
                    dropout=float(cfg["dropout"])).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=float(cfg["learning_rate"]), weight_decay=1e-5)
    loss_fn = nn.MSELoss()
    tr_seq, tr_pt, tr_y = _tensors(train, patches, dev)
    va = _tensors(val, patches, dev) if len(val) else None
    bs, n = int(cfg["batch_size"]), len(train)
    best, best_state, best_epoch, bad = np.inf, None, 0, 0
    history = []
    epochs = fixed_epochs or int(cfg["epochs"])
    for epoch in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(n, device=dev)
        tot = 0.0
        for i in range(0, n, bs):
            b = perm[i:i + bs]
            if len(b) < 2:
                continue
            opt.zero_grad()
            loss = loss_fn(model(tr_seq[b], tr_pt[b]), tr_y[b])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item() * len(b)
        rec = {"epoch": epoch, "train_mse_z": tot / n}
        if va is not None and fixed_epochs is None:
            model.eval()
            with torch.no_grad():
                vl = float(loss_fn(model(va[0], va[1]), va[2]))
            rec["val_mse_z"] = vl
            if vl < best - 1e-5:
                best, best_epoch, bad = vl, epoch, 0
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            else:
                bad += 1
                if bad >= int(cfg["patience"]):
                    history.append(rec)
                    break
        history.append(rec)
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model, {"best_epoch": best_epoch or epochs, "best_val_mse_z": None if best == np.inf else best,
                   "epochs_run": len(history), "history": history}


def predict(models: list[CNNLSTM], s: SampleSet, patches: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(s) == 0:
        return np.zeros(0), np.zeros(0)
    dev = device()
    seq, pt, _ = _tensors(s, patches, dev)
    outs = []
    with torch.no_grad():
        for m in models:
            outs.append(torch.cat([m(seq[i:i + 2048], pt[i:i + 2048]) for i in range(0, len(s), 2048)])
                        .cpu().numpy())
    o = np.stack(outs)
    return o.mean(0), o.std(0)


def train_ensemble(b: Bundle, train_end, val_end, cfg, tag, settings) -> tuple[list[CNNLSTM], list[dict]]:
    months = b.samples.month
    tr = b.samples.subset(months <= np.datetime64(train_end))
    va = b.samples.subset((months > np.datetime64(train_end)) & (months <= np.datetime64(val_end)))
    if len(tr) < 100:
        raise InsufficientDataError(
            f"Only {len(tr)} training samples for the {tag} model (need >= 100). "
            f"Sample drop reasons: {b.drops}. Check input data coverage.")
    log.info("[model:%s] train %d samples, val %d samples", tag, len(tr), len(va))
    models, infos = [], []
    for k in range(int(cfg["ensemble_size"])):
        m, info = train_member(tr, va, b.patches, cfg, int(cfg["seed"]) + k)
        torch.save(m.state_dict(), settings.models_dir / f"{tag}_member_{k}.pt")
        log.info("[model:%s] member %d best epoch %d val_mse_z %s", tag, k, info["best_epoch"],
                 None if info["best_val_mse_z"] is None else round(info["best_val_mse_z"], 4))
        models.append(m); infos.append(info)
    with (settings.models_dir / f"{tag}_normalizer.json").open("w") as fh:
        json.dump(b.norm.to_dict(), fh)
    return models, infos


# ---------------------------------------------------------------------------- rollout
def climatology(settings: Settings, norm: Normalizer) -> pd.DataFrame:
    era = pd.read_parquet(settings.processed_dir / "era5_station_monthly.parquet").dropna()
    start = int(settings.section("time")["climatology_start_year"])
    full_years = era.groupby(era["month"].dt.year)["month"].nunique()
    last_full = int(full_years[full_years == 12].index.max())
    era = era[(era["month"].dt.year >= start) & (era["month"].dt.year <= last_full)]
    clim = era.groupby(["station_id", era["month"].dt.month]).agg(
        rain_mm=("rain_mm", "mean"), temp_c=("temp_c", "mean")).reset_index()
    clim = clim.rename(columns={"month": "cal_month"})
    clim["rain_z"] = (np.log1p(clim["rain_mm"].clip(lower=0)) - norm.rain_mean) / norm.rain_std
    clim["temp_z"] = (clim["temp_c"] - norm.temp_mean) / norm.temp_std
    clim.attrs["years"] = [start, last_full]
    return clim


def future_patch_index(month_prev: pd.Timestamp, periods: list[str], valid_row, thr, mode) -> int | None:
    label = month_to_period(month_prev, mode)
    if label in periods and valid_row[periods.index(label)] >= thr:
        return periods.index(label)
    same = label[4:]  # "Q3" or "-07"
    cands = [i for i, p in enumerate(periods) if p[4:] == same and _period_start(p) <= month_prev
             and valid_row[i] >= thr]
    if cands:
        return cands[-1]
    cands = [i for i, p in enumerate(periods) if _period_start(p) <= month_prev and valid_row[i] >= thr]
    return cands[-1] if cands else None


def rollout(models: list[CNNLSTM], b: Bundle, settings: Settings, start: pd.Timestamp,
            end: pd.Timestamp, clim: pd.DataFrame) -> pd.DataFrame:
    """Recursive multi-step forecast (each ensemble member rolls out independently)."""
    L = int(settings.section("model")["lookback_months"])
    thr = float(settings.section("sentinel2")["min_valid_patch_fraction"])
    mode = settings.section("sentinel2").get("composite", "quarterly")
    months = pd.date_range(start, end, freq="MS")
    clim_idx = clim.set_index(["station_id", "cal_month"])
    hist_months = pd.date_range(start - pd.DateOffset(months=L), start - pd.DateOffset(months=1), freq="MS")
    f = b.frame.set_index(["station_id", "month"])
    stations, init, forcing, pidx, insufficient = [], [], [], [], []
    for sid, row in b.station_rows.items():
        try:
            h = f.loc[[(sid, m) for m in hist_months]]
        except KeyError:
            insufficient.append(sid); continue
        if not np.isfinite(h["depth_z"]).all():
            insufficient.append(sid); continue
        # forcing for steps: history months+1 .. end (observed where in history, climatology after)
        forc = []
        ok = True
        for m in list(hist_months[1:]) + list(months):
            if m < start and (sid, m) in f.index and np.isfinite(f.loc[(sid, m), ["rain_z", "temp_z"]]).all():
                forc.append(f.loc[(sid, m), ["rain_z", "temp_z"]].to_numpy(float))
            elif (sid, m.month) in clim_idx.index:
                forc.append(clim_idx.loc[(sid, m.month), ["rain_z", "temp_z"]].to_numpy(float))
            else:
                ok = False; break
        pis = [future_patch_index(m - pd.DateOffset(months=1), b.periods, b.valid[row], thr, mode)
               for m in months]
        if not ok or any(p is None for p in pis):
            insufficient.append(sid); continue
        stations.append(sid)
        init.append(np.c_[h["depth_z"].to_numpy(float), h["interp"].to_numpy(float)])
        forcing.append(np.asarray(forc))
        pidx.append([(row, p) for p in pis])
    if not stations:
        return pd.DataFrame()
    S, T = len(stations), len(months)
    all_months = list(hist_months[1:]) + list(months)  # forcing timeline, length L-1+T
    msin = np.sin(2 * np.pi * (np.array([m.month for m in all_months]) - 1) / 12)
    mcos = np.cos(2 * np.pi * (np.array([m.month for m in all_months]) - 1) / 12)
    forcing = np.asarray(forcing)          # S x (L-1+T) x 2
    pidx = np.asarray(pidx)                # S x T x 2
    dev = device()
    member_preds = np.zeros((len(models), S, T), dtype="float32")
    for k, model in enumerate(models):
        depth = np.zeros((S, L + T)); interp = np.zeros((S, L + T))
        depth[:, :L] = np.asarray(init)[:, :, 0]; interp[:, :L] = np.asarray(init)[:, :, 1]
        for t in range(T):
            win = slice(t, t + L)               # depth/interp indices
            fwin = slice(t, t + L)              # forcing index j+1 aligned
            seq = np.stack([depth[:, win], interp[:, win], forcing[:, fwin, 0], forcing[:, fwin, 1],
                            np.broadcast_to(msin[fwin], (S, L)), np.broadcast_to(mcos[fwin], (S, L))],
                           axis=2).astype("float32")
            patch = b.patches[pidx[:, t, 0], pidx[:, t, 1]]
            with torch.no_grad():
                out = model(torch.from_numpy(seq).to(dev), torch.from_numpy(patch).to(dev)).cpu().numpy()
            depth[:, L + t] = out
            member_preds[k, :, t] = out
    rows = []
    for si, sid in enumerate(stations):
        mu, sd = b.norm.station_mean[sid], b.norm.station_std[sid]
        for t, m in enumerate(months):
            zs = member_preds[:, si, t]
            rows.append({"station_id": sid, "month": m, "horizon": t + 1,
                         "pred_m": float(zs.mean() * sd + mu), "ens_std_m": float(zs.std() * sd)})
    out = pd.DataFrame(rows)
    out.attrs["insufficient_stations"] = insufficient
    return out


def _denorm(b: Bundle, sids, z):
    mu = np.array([b.norm.station_mean[s] for s in sids]); sd = np.array([b.norm.station_std[s] for s in sids])
    return z * sd + mu, sd


def horizon_metrics(fc: pd.DataFrame, b: Bundle) -> pd.DataFrame:
    obs = b.frame[["station_id", "month", "depth_obs"]]
    m = fc.merge(obs, on=["station_id", "month"], how="left").dropna(subset=["depth_obs"])
    rows = []
    for h, g in m.groupby("horizon"):
        rows.append({"horizon": int(h), **metrics(g["depth_obs"].to_numpy(), g["pred_m"].to_numpy())})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------- main entry
def run_modeling(settings: Settings) -> dict:
    tcfg, mcfg = settings.section("time"), settings.section("model")
    torch.set_num_threads(max(1, torch.get_num_threads()))
    eval_train_end = pd.Timestamp(tcfg["eval_train_end"]); eval_val_end = pd.Timestamp(tcfg["eval_val_end"])
    final_train_end = pd.Timestamp(tcfg["final_train_end"]); final_val_end = pd.Timestamp(tcfg["final_val_end"])
    pred_year = int(tcfg["prediction_year"])
    min_n = int(mcfg["min_test_samples"])

    # ---- evaluation model ------------------------------------------------------
    be = make_bundle(settings, eval_train_end)
    models_e, info_e = train_ensemble(be, eval_train_end, eval_val_end, mcfg, "eval", settings)
    mu, sd = predict(models_e, be.samples, be.patches)
    pred_m, scale = _denorm(be, be.samples.station_id, mu)
    true_m, _ = _denorm(be, be.samples.station_id, be.samples.y)
    last_m, _ = _denorm(be, be.samples.station_id, be.samples.last_z)
    months = pd.DatetimeIndex(be.samples.month)
    split = np.where(months <= eval_train_end, "train",
                     np.where(months <= eval_val_end, "validation",
                              np.where(months.year == pred_year, "test", "after_test")))
    one_step = pd.DataFrame({"station_id": be.samples.station_id, "month": months, "actual_m": true_m,
                             "pred_m": pred_m, "ens_std_m": sd * scale, "split": split,
                             "persistence_m": last_m})
    obs = be.frame[["station_id", "month", "depth_obs"]].rename(columns={"depth_obs": "lag12_m"})
    obs["month"] = obs["month"] + pd.DateOffset(years=1)
    one_step = one_step.merge(obs, on=["station_id", "month"], how="left")
    test = one_step[one_step["split"] == "test"]
    if len(test) < min_n:
        raise InsufficientDataError(f"Only {len(test)} test samples in {pred_year} (need >= {min_n}).")
    test_metrics = {
        "cnn_lstm": metrics(test["actual_m"].to_numpy(), test["pred_m"].to_numpy()),
        "baseline_persistence": metrics(test["actual_m"].to_numpy(), test["persistence_m"].to_numpy()),
        "baseline_seasonal_naive": metrics(test.dropna(subset=["lag12_m"])["actual_m"].to_numpy(),
                                           test.dropna(subset=["lag12_m"])["lag12_m"].to_numpy()),
    }
    split_metrics = {s: metrics(g["actual_m"].to_numpy(), g["pred_m"].to_numpy())
                     for s, g in one_step.groupby("split")}
    per_station = [{"station_id": s, **metrics(g["actual_m"].to_numpy(), g["pred_m"].to_numpy())}
                   for s, g in test.groupby("station_id")]

    clim_e = climatology(settings, be.norm)
    fc_e = rollout(models_e, be, settings, eval_val_end + pd.offsets.MonthBegin(1),
                   pd.Timestamp(pred_year, 12, 1), clim_e)
    hz_e = horizon_metrics(fc_e, be) if len(fc_e) else pd.DataFrame()

    # ---- forecast model --------------------------------------------------------
    bf = make_bundle(settings, final_train_end)
    models_f, info_f = train_ensemble(bf, final_train_end, final_val_end, mcfg, "final", settings)
    clim_f = climatology(settings, bf.norm)
    fc_start = final_val_end + pd.offsets.MonthBegin(1)
    fc_end = pd.Timestamp(int(tcfg["forecast_end_year"]), 12, 1)
    fc = rollout(models_f, bf, settings, fc_start, fc_end, clim_f)
    if fc.empty:
        raise InsufficientDataError("No station had a complete input window for forecasting.")
    hz_f = horizon_metrics(fc, bf)

    # validated horizon: contiguous horizons with >= min_n hold-out comparisons
    parts = []
    if len(hz_e):
        parts.append(hz_e.assign(source=f"eval_rollout_{pred_year}"))
    if len(hz_f):
        parts.append(hz_f.assign(source="forecast_holdout"))
    hz_all = pd.concat(parts, ignore_index=True) if parts else None
    validated = 0
    if hz_all is not None and len(hz_all):
        ok = set(hz_all.loc[hz_all["n"] >= min_n, "horizon"])
        while validated + 1 in ok:
            validated += 1
    # empirical error by horizon (prefer forecast hold-out, else eval rollout)
    err_by_h = {}
    for src in [hz_e, hz_f]:
        if len(src):
            for _, r in src[src["n"] >= min_n].iterrows():
                err_by_h[int(r["horizon"])] = float(r["rmse_m"])
    max_known = max(err_by_h) if err_by_h else None
    def rmse_for(h):
        if not err_by_h:
            return np.nan
        return err_by_h.get(h, err_by_h[max_known] if h > max_known else np.nan)
    fc["horizon_rmse_m"] = fc["horizon"].map(rmse_for)
    sigma = np.sqrt(fc["ens_std_m"] ** 2 + fc["horizon_rmse_m"].fillna(0) ** 2)
    fc["lower_m"] = (fc["pred_m"] - 1.96 * sigma).clip(lower=0)
    fc["upper_m"] = fc["pred_m"] + 1.96 * sigma
    fc["within_validated_horizon"] = fc["horizon"] <= validated
    fc["covariate_scenario"] = SCENARIO
    fc = fc.merge(bf.frame[["station_id", "month", "depth_obs"]].rename(columns={"depth_obs": "actual_m"}),
                  on=["station_id", "month"], how="left")

    one_step.to_parquet(settings.processed_dir / "station_one_step_predictions.parquet", index=False)
    fc.to_parquet(settings.processed_dir / "station_forecasts.parquet", index=False)

    result = {
        "model": "CNN-LSTM ensemble (CNN on NDVI/NDBI/VIIRS patches + LSTM on monthly groundwater & ERA5-Land)",
        "device": str(device()),
        "ensemble_size": int(mcfg["ensemble_size"]),
        "lookback_months": int(mcfg["lookback_months"]),
        "splits": {"eval_train_end": str(eval_train_end.date()), "eval_val_end": str(eval_val_end.date()),
                   "test_year": pred_year, "final_train_end": str(final_train_end.date()),
                   "final_val_end": str(final_val_end.date()), "forecast_start": str(fc_start.date()),
                   "forecast_end": str(fc_end.date())},
        "samples": {"eval_total": int(len(be.samples)), "eval_drops": be.drops,
                    "final_total": int(len(bf.samples)), "final_drops": bf.drops},
        "test_metrics_one_step": test_metrics,
        "metrics_by_split_one_step": split_metrics,
        "per_station_test_metrics": per_station,
        "rollout_metrics_by_horizon": hz_all.to_dict(orient="records") if hz_all is not None else [],
        "validated_horizon_months": validated,
        "forecast_covariate_scenario": SCENARIO,
        "climatology_years": clim_f.attrs.get("years"),
        "stations_forecast": int(fc["station_id"].nunique()),
        "stations_insufficient_for_forecast": fc.attrs.get("insufficient_stations", []),
        "training": {"eval": [{k: v for k, v in i.items() if k != "history"} for i in info_e],
                     "final": [{k: v for k, v in i.items() if k != "history"} for i in info_f]},
        "loss_curves": {"eval": [i["history"] for i in info_e], "final": [i["history"] for i in info_f]},
    }
    log.info("[model] test RMSE %.3f m (persistence %.3f, seasonal-naive %.3f); validated horizon %d months",
             test_metrics["cnn_lstm"].get("rmse_m", np.nan),
             test_metrics["baseline_persistence"].get("rmse_m", np.nan),
             test_metrics["baseline_seasonal_naive"].get("rmse_m", np.nan), validated)
    return result
