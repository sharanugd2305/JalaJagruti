"""Reproducible, project-specific groundwater risk score.

risk = w_depth * ramp(depth, d0, d1)
     + w_trend * ramp(trend, t0, t1)
     + w_urban * ramp(NDBI, n0, n1)
with fixed ramps from config/project.yaml (no data-dependent rescaling, so the
same inputs always give the same score across runs and years).
If depth is unavailable the score is INSUFFICIENT_INPUT_DATA. If only the urban
component is missing, its weight is redistributed and this is flagged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ramp(x, lo, hi):
    return np.clip((np.asarray(x, float) - lo) / (hi - lo), 0, 1)


def risk_scores(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """df columns: depth_m, trend_m_per_year, ndbi. Returns risk_score, risk_class, risk_note."""
    w = cfg["weights"]
    d = ramp(df["depth_m"], *cfg["depth_ramp_m"])
    t = ramp(df["trend_m_per_year"], *cfg["trend_ramp_m_per_year"])
    u = ramp(df["ndbi"], *cfg["ndbi_ramp"])
    has_d, has_t, has_u = df["depth_m"].notna(), df["trend_m_per_year"].notna(), df["ndbi"].notna()
    num = w["depth"] * np.where(has_d, d, 0) + w["trend"] * np.where(has_t, t, 0) + w["urban"] * np.where(has_u, u, 0)
    den = w["depth"] * has_d + w["trend"] * has_t + w["urban"] * has_u
    score = np.where(has_d & has_t, num / np.where(den > 0, den, 1), np.nan)
    classes = sorted(cfg["classes"].items(), key=lambda kv: kv[1])
    cls = []
    for s in score:
        if not np.isfinite(s):
            cls.append("INSUFFICIENT_INPUT_DATA")
            continue
        cls.append(next(name for name, ub in classes if s < ub))
    note = np.where(~(has_d & has_t), "depth or trend unavailable",
                    np.where(~has_u, "urban (NDBI) component unavailable; weights renormalised", ""))
    return pd.DataFrame({"risk_score": np.round(score, 4), "risk_class": cls, "risk_note": note},
                        index=df.index)
