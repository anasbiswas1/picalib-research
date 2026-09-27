"""Rank-based severity and monotone recalibration maps.

R(s)      = 1 - F_ben(s), F_ben the empirical CDF of the benign calibration scores.
CMR(tau)  = fraction of attacks with R >= tau  (equivalently p <= benign (1-tau)-quantile).
Both are invariant under any strictly increasing map g applied to all scores with the
threshold re-set at the same benign order statistic.
"""
from __future__ import annotations
import numpy as np

EPS = 1e-6


def ecdf(ref):
    ref = np.sort(np.asarray(ref, float))
    def F(s):
        return np.searchsorted(ref, np.asarray(s, float), side="right") / len(ref)
    return F


def rank_severity(p, ref_benign):
    """R for every score in p (attacks), against the benign reference distribution."""
    return 1.0 - ecdf(ref_benign)(p)


def order_stat_threshold(p_benign, target_fpr=0.01):
    """Highest benign score such that at most target_fpr of benigns are >= it (method='higher').
    Under a strictly increasing map g, g(t) is exactly the same order statistic of g(p_benign)."""
    return float(np.quantile(np.asarray(p_benign, float), 1.0 - target_fpr, method="higher"))


def cmr(p_atk, ref_benign, tau=0.95):
    return float((rank_severity(p_atk, ref_benign) >= tau).mean()) if len(p_atk) else np.nan


def severity_S(p_atk, t, min_misses=10):
    miss = p_atk < t
    return float(np.mean(1.0 - p_atk[miss])) if miss.sum() >= min_misses else np.nan


def fnr(p_atk, t):
    return float((p_atk < t).mean()) if len(p_atk) else np.nan


# ---------- monotone recalibration maps, fitted on the calibration (direct) set ----------
def _logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def _nll(q, y, w_fn=1.0, w_fp=1.0):
    q = np.clip(q, EPS, 1 - EPS)
    return float(np.mean(-w_fn * y * np.log(q) - w_fp * (1 - y) * np.log(1 - q)))


def fit_temperature(p, y, w_fn=1.0, w_fp=1.0):
    from scipy.optimize import minimize_scalar
    z = _logit(p)
    res = minimize_scalar(lambda T: _nll(_sigmoid(z / T), y, w_fn, w_fp), bounds=(0.05, 50.0), method="bounded")
    T = float(res.x)
    return lambda q: _sigmoid(_logit(q) / T), {"T": T}


def fit_platt(p, y):
    from sklearn.linear_model import LogisticRegression
    z = _logit(p).reshape(-1, 1)
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(z, y)
    a, b = float(lr.coef_[0, 0]), float(lr.intercept_[0])
    return lambda q: _sigmoid(a * _logit(q) + b), {"a": a, "b": b}


def fit_isotonic(p, y):
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip", increasing=True).fit(np.asarray(p, float), y)
    return lambda q: iso.predict(np.asarray(q, float)), {"n_knots": int(len(iso.X_thresholds_))}


def all_maps(p_cal, y_cal, fn_cost=10.0):
    """Dict name -> (map, params). 'asym_temperature' is a cost-weighted temperature fit (false-negative
    cost fn_cost times the false-positive cost), a monotone proxy for cost-aware temperature scaling."""
    out = {}
    out["temperature"] = fit_temperature(p_cal, y_cal)
    out["platt"] = fit_platt(p_cal, y_cal)
    out["isotonic"] = fit_isotonic(p_cal, y_cal)
    out["asym_temperature"] = fit_temperature(p_cal, y_cal, w_fn=fn_cost, w_fp=1.0)
    return out


def bootstrap(fn, p_atk, B=1000, seed=0, **kw):
    rng = np.random.default_rng(seed); vals = []
    for _ in range(B):
        idx = rng.integers(0, len(p_atk), len(p_atk)); vals.append(fn(p_atk[idx], **kw))
    return tuple(np.nanpercentile(vals, [2.5, 97.5]))
