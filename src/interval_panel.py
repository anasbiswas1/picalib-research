"""Interval re-reporting for frozen-threshold transport panels.

For a target FPR on a benign calibration set, the threshold is identified only up to the gap between
two consecutive benign order statistics. Every threshold-dependent metric is therefore reported at the
low end (t_lower), the high end (t_higher) and at the guaranteed-FPR threshold (t_guar).
"""
from __future__ import annotations
import numpy as np
from score_diagnostics import thresholds as _thresholds

KEYS = ("lo", "hi", "guar")


def three_thresholds(p_ben_cal, fpr=0.01):
    T = _thresholds(p_ben_cal, fpr)
    return {"lo": T["t_lower"], "hi": T["t_higher"], "guar": T["t_guar"]}


def fnr(pa, t):
    return float((pa < t).mean()) if len(pa) else np.nan


def severity(pa, t, min_misses=10):
    m = pa < t
    return float(np.mean(1 - pa[m])) if m.sum() >= min_misses else np.nan


def fpr(pb, t):
    return float((pb >= t).mean()) if len(pb) else np.nan


def bootstrap_fnr(pa, t, B=1000, seed=0):
    rng = np.random.default_rng(seed); n = len(pa)
    v = [fnr(pa[rng.integers(0, n, n)], t) for _ in range(B)]
    return tuple(np.percentile(v, [2.5, 97.5]))


def interval_cell(pa, pb_cal, pb_tgt=None, fpr_target=0.01, auroc_fn=None):
    """All three thresholds' worth of metrics for one detector x shift cell."""
    T = three_thresholds(pb_cal, fpr_target); out = {f"t_{k}": T[k] for k in KEYS}
    for k in KEYS:
        t = T[k]
        out[f"FNR_{k}"] = fnr(pa, t)
        out[f"FNR_{k}_lo95"], out[f"FNR_{k}_hi95"] = bootstrap_fnr(pa, t)
        out[f"n_miss_{k}"] = int((pa < t).sum())
        out[f"S_{k}"] = severity(pa, t)
        out[f"calFPR_{k}"] = fpr(pb_cal, t)
        if pb_tgt is not None and len(pb_tgt):
            out[f"tgtFPR_{k}"] = fpr(pb_tgt, t)
    out["FNR_width_lo_hi"] = out["FNR_hi"] - out["FNR_lo"]
    if pb_tgt is not None and len(pb_tgt) and auroc_fn is not None:
        y = np.r_[np.ones(len(pa)), np.zeros(len(pb_tgt))]
        out["AUROC"] = auroc_fn(y, np.r_[pa, pb_tgt])
    return out


def rel_change(v_shift, v_direct):
    return float((v_shift - v_direct) / v_direct) if v_direct not in (0, None) and not np.isnan(v_direct) else np.nan
