"""Build CNN spatial inputs and LSTM temporal sequences from the processed panel.

One sample = predict depth at month t for one station from:
  sequence (L steps, j = t-L .. t-1), each step:
      [depth_z(j), depth_interpolated_flag(j), rain_z(j+1), temp_z(j+1),
       sin(month(j+1)), cos(month(j+1))]
    i.e. the last known level paired with the next month's forcing, so the final
    step carries the target month's forcing.
  patch  (C x P x P): NDVI, NDBI, log night lights, valid mask for the
    composite period of month t-1 (falls back to the most recent earlier valid
    composite, recording its age; none -> sample dropped).
Target: depth_z(t) (observed, never interpolated).

Normalisation statistics come from the training split only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SEQ_FEATURES = ["depth_z", "interp", "rain_z", "temp_z", "msin", "mcos"]


@dataclass
class Normalizer:
    station_mean: dict = field(default_factory=dict)
    station_std: dict = field(default_factory=dict)
    rain_mean: float = 0.0
    rain_std: float = 1.0
    temp_mean: float = 0.0
    temp_std: float = 1.0
    patch_mean: list = field(default_factory=list)
    patch_std: list = field(default_factory=list)

    @classmethod
    def fit(cls, panel: pd.DataFrame, train_end: pd.Timestamp, patches: np.ndarray,
            periods: list[str]) -> "Normalizer":
        tr = panel[panel["month"] <= train_end]
        g = tr.groupby("station_id")["depth_bgl_m"]
        n = cls()
        n.station_mean = g.mean().dropna().to_dict()
        n.station_std = g.std().fillna(0).clip(lower=0.5).to_dict()
        lr = np.log1p(tr["rain_mm"].clip(lower=0).dropna())
        n.rain_mean, n.rain_std = float(lr.mean()), float(max(lr.std(), 1e-6))
        t = tr["temp_c"].dropna()
        n.temp_mean, n.temp_std = float(t.mean()), float(max(t.std(), 1e-6))
        train_periods = [i for i, p in enumerate(periods) if _period_start(p) <= train_end]
        sub = patches[:, train_periods, :3] if train_periods else patches[:, :, :3]
        n.patch_mean = [float(np.nanmean(sub[:, :, c])) for c in range(3)]
        n.patch_std = [float(max(np.nanstd(sub[:, :, c]), 1e-6)) for c in range(3)]
        return n

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def _period_start(label: str) -> pd.Timestamp:
    if "Q" in label:
        y, q = label.split("Q")
        return pd.Timestamp(int(y), (int(q) - 1) * 3 + 1, 1)
    return pd.Timestamp(label + "-01")


def normalize_patches(patches: np.ndarray, norm: Normalizer) -> np.ndarray:
    out = patches.copy()
    for c in range(3):
        out[:, :, c] = (out[:, :, c] - norm.patch_mean[c]) / norm.patch_std[c]
    out[:, :, 3] = np.nan_to_num(out[:, :, 3])
    return np.nan_to_num(out, nan=0.0).astype("float32")  # NaN pixels -> 0 with mask channel = 0


def prepare_station_frame(panel: pd.DataFrame, norm: Normalizer, max_gap: int) -> pd.DataFrame:
    """Add normalised columns; interpolate depth gaps <= max_gap months (flagged)."""
    df = panel.sort_values(["station_id", "month"]).copy()
    df["depth_obs"] = df["depth_bgl_m"]
    parts = []
    for sid, g in df.groupby("station_id", sort=False):
        if sid not in norm.station_mean:
            continue
        s = g["depth_obs"]
        filled = s.interpolate(limit=max_gap, limit_area="inside")
        # only keep interpolations that bridge gaps of length <= max_gap entirely
        isna = s.isna()
        run_id = (isna != isna.shift()).cumsum()
        run_len = isna.groupby(run_id).transform("sum")
        bad = isna & (run_len > max_gap)
        filled[bad] = np.nan
        g = g.assign(depth_filled=filled, interp=(isna & filled.notna()).astype("float32"))
        g["depth_z"] = (g["depth_filled"] - norm.station_mean[sid]) / norm.station_std[sid]
        parts.append(g)
    df = pd.concat(parts, ignore_index=True)
    df["rain_z"] = (np.log1p(df["rain_mm"].clip(lower=0)) - norm.rain_mean) / norm.rain_std
    df["temp_z"] = (df["temp_c"] - norm.temp_mean) / norm.temp_std
    df["msin"] = np.sin(2 * np.pi * (df["month"].dt.month - 1) / 12).astype("float32")
    df["mcos"] = np.cos(2 * np.pi * (df["month"].dt.month - 1) / 12).astype("float32")
    return df


def patch_index_for(month_prev: pd.Timestamp, period_of: dict, periods: list[str],
                    valid_row: np.ndarray, thr: float) -> tuple[int | None, int]:
    """Composite index for month_prev, falling back to the latest earlier valid one."""
    label = period_of(month_prev)
    if label not in periods:
        candidates = [i for i, p in enumerate(periods) if _period_start(p) <= month_prev]
        if not candidates:
            return None, -1
        i0 = candidates[-1]
    else:
        i0 = periods.index(label)
    for age, i in enumerate(range(i0, -1, -1)):
        if valid_row[i] >= thr:
            return i, age
    return None, -1


@dataclass
class SampleSet:
    seq: np.ndarray        # N x L x F
    patch_idx: np.ndarray  # N x 2  (station_row, period_idx)
    y: np.ndarray          # N
    last_z: np.ndarray     # N
    station_id: np.ndarray
    month: np.ndarray
    patch_age: np.ndarray

    def __len__(self):
        return len(self.y)

    def subset(self, mask):
        return SampleSet(self.seq[mask], self.patch_idx[mask], self.y[mask], self.last_z[mask],
                         self.station_id[mask], self.month[mask], self.patch_age[mask])


def build_samples(frame: pd.DataFrame, station_rows: dict, periods: list[str], valid: np.ndarray,
                  L: int, thr: float, period_of) -> tuple[SampleSet, dict]:
    seqs, pidx, ys, lz, sids, months, ages = [], [], [], [], [], [], []
    drops = {"no_target": 0, "incomplete_sequence": 0, "missing_forcing": 0, "no_valid_patch": 0}
    for sid, g in frame.groupby("station_id", sort=False):
        if sid not in station_rows:
            continue
        g = g.reset_index(drop=True)
        dz, it = g["depth_z"].to_numpy(), g["interp"].to_numpy()
        rz, tz = g["rain_z"].to_numpy(), g["temp_z"].to_numpy()
        ms, mc = g["msin"].to_numpy(), g["mcos"].to_numpy()
        obs = g["depth_obs"].to_numpy()
        mon = g["month"].to_numpy()
        srow = station_rows[sid]
        for t in range(L, len(g)):
            if not np.isfinite(obs[t]):
                drops["no_target"] += 1
                continue
            win = slice(t - L, t)
            nxt = slice(t - L + 1, t + 1)
            if not np.isfinite(dz[win]).all():
                drops["incomplete_sequence"] += 1
                continue
            if not (np.isfinite(rz[nxt]).all() and np.isfinite(tz[nxt]).all()):
                drops["missing_forcing"] += 1
                continue
            pi, age = patch_index_for(pd.Timestamp(mon[t - 1]), period_of, periods, valid[srow], thr)
            if pi is None:
                drops["no_valid_patch"] += 1
                continue
            seqs.append(np.stack([dz[win], it[win], rz[nxt], tz[nxt], ms[nxt], mc[nxt]], axis=1))
            pidx.append((srow, pi)); ys.append(dz[t]); lz.append(dz[t - 1])
            sids.append(sid); months.append(mon[t]); ages.append(age)
    if not ys:
        empty = np.zeros((0,))
        return SampleSet(np.zeros((0, L, len(SEQ_FEATURES)), "float32"), np.zeros((0, 2), int),
                         empty, empty, np.array([]), np.array([], "datetime64[ns]"), empty), drops
    return SampleSet(np.asarray(seqs, "float32"), np.asarray(pidx, int), np.asarray(ys, "float32"),
                     np.asarray(lz, "float32"), np.asarray(sids), np.asarray(months, "datetime64[ns]"),
                     np.asarray(ages, int)), drops
