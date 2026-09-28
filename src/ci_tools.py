"""Uncertainty for the paper's headline numbers: item bootstrap for AUROC, Wilson intervals for rates, and the
identification gap side by side with the sampling interval at each endpoint."""
from __future__ import annotations
import numpy as np


def wilson(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def boot_auroc(y, p, B=2000, seed=0):
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(seed); y = np.asarray(y); p = np.asarray(p); pos = np.where(y == 1)[0]; neg = np.where(y == 0)[0]; v = []
    for _ in range(B):
        a = rng.choice(pos, len(pos), replace=True); b = rng.choice(neg, len(neg), replace=True)
        v.append(roc_auc_score(np.r_[np.ones(len(a)), np.zeros(len(b))], np.r_[p[a], p[b]]))
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def boot_rate(x, B=2000, seed=0):
    rng = np.random.default_rng(seed); x = np.asarray(x, float); v = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(B)]
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def fmt(v, lo, hi, d=3):
    return f"{v:.{d}f} [{lo:.{d}f}, {hi:.{d}f}]"
