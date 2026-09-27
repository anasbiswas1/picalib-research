"""Score-degeneracy diagnostics and tie-aware thresholds for the transport panel."""
from __future__ import annotations
import numpy as np


def unique_stats(p):
    p = np.asarray(p, float)
    vals, counts = np.unique(p, return_counts=True)
    i = int(np.argmax(counts))
    return dict(n=int(len(p)), n_unique=int(len(vals)), modal_value=float(vals[i]),
                modal_mass=float(counts[i] / len(p)), min_value=float(vals[0]),
                mass_at_min=float(counts[0] / len(p)))


def thresholds(p_ben, fpr=0.01):
    """Five threshold definitions on the calibration benigns for a target FPR."""
    p_ben = np.asarray(p_ben, float)
    q = 1.0 - fpr
    T = {m: float(np.quantile(p_ben, q, method=m)) for m in ("linear", "higher", "lower", "nearest")}
    cand = np.unique(p_ben)
    ok = [s for s in cand if (p_ben >= s).mean() <= fpr]      # block iff p >= s guarantees FPR <= fpr
    T["guar"] = float(min(ok)) if ok else float(cand[-1])
    return {f"t_{k}": v for k, v in T.items()}


def cell_report(p_atk, p_ben_cal, p_ben_tgt=None, fpr=0.01, min_misses=10):
    p_atk = np.asarray(p_atk, float); p_ben_cal = np.asarray(p_ben_cal, float)
    T = thresholds(p_ben_cal, fpr); out = dict(T)
    for k, t in T.items():
        out[f"FNR@{k}"] = float((p_atk < t).mean())
        out[f"calFPR@{k}"] = float((p_ben_cal >= t).mean())
    tg = T["t_guar"]
    out["FNR@t_guar_ties_as_miss"] = float((p_atk <= tg).mean())
    out["n_atk_eq_t_guar"] = int((p_atk == tg).sum())
    out["n_ben_eq_t_guar"] = int((p_ben_cal == tg).sum())
    lo, hi = sorted([T["t_linear"], T["t_higher"]])
    out["n_atk_in_interp_band"] = int(((p_atk >= lo) & (p_atk <= hi)).sum())
    out["frac_atk_in_interp_band"] = out["n_atk_in_interp_band"] / len(p_atk)
    fnrs = [out[f"FNR@{k}"] for k in T] + [out["FNR@t_guar_ties_as_miss"]]
    out["FNR_spread"] = float(max(fnrs) - min(fnrs))
    if p_ben_tgt is not None and len(p_ben_tgt):
        p_ben_tgt = np.asarray(p_ben_tgt, float)
        out["tgtFPR@t_guar"] = float((p_ben_tgt >= tg).mean())
        out["tgtFPR@t_linear"] = float((p_ben_tgt >= T["t_linear"]).mean())
    miss = p_atk < tg
    out["S@t_guar"] = float(np.mean(1 - p_atk[miss])) if miss.sum() >= min_misses else np.nan
    for pre, arr in (("atk", p_atk), ("calben", p_ben_cal)):
        out.update({f"{pre}_{k}": v for k, v in unique_stats(arr).items()})
    # how many distinct attack score values fall strictly below the guaranteed threshold
    out["atk_n_unique_below_t_guar"] = int(len(np.unique(p_atk[p_atk < tg])))
    return out
