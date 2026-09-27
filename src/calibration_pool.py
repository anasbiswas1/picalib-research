"""Identification interval of a frozen 1 percent FPR threshold as a function of the benign calibration pool."""
from __future__ import annotations
import numpy as np
from interval_panel import three_thresholds, fnr, KEYS


def interval_row(pool_ben, atk_sets, fpr_target=0.01):
    """For one benign pool: thresholds, FNR at lo/hi/guar on every attack set, width, and the tail gap."""
    T = three_thresholds(pool_ben, fpr_target)
    out = {"N": int(len(pool_ben)), **{f"t_{k}": T[k] for k in KEYS}, "tail_gap": T["hi"] - T["lo"]}
    for name, pa in atk_sets.items():
        for k in KEYS:
            out[f"FNR_{k}_{name}"] = fnr(pa, T[k])
        out[f"width_{name}"] = out[f"FNR_hi_{name}"] - out[f"FNR_lo_{name}"]
    return out


def width_vs_n(pool_ben, atk_sets, Ns, draws=20, seed=0, fpr_target=0.01):
    """Subsample the pool at each N (without replacement) and average the interval width over draws."""
    rng = np.random.default_rng(seed); rows = []
    for N in Ns:
        N = int(min(N, len(pool_ben)))
        for d in range(draws):
            sub = pool_ben[rng.choice(len(pool_ben), N, replace=False)]
            r = interval_row(sub, atk_sets, fpr_target); r["draw"] = d; rows.append(r)
    return rows
