"""The identification interval of a quantile convention, defined by the blocked set rather than by order-statistic
index, so that ties and the excluded lower end are handled exactly.

Decision rule everywhere in this project: block a text if its score is at or above the threshold t.

A quantile convention (numpy's method, 'linear' by default, which is what the preprint used) applied to the calibration
benigns at level 1 - f gives a threshold t_c. That threshold blocks some set of k calibration benigns. Every threshold in
the half-open interval (v_lo, v_hi] blocks exactly the same k benigns, where v_hi is the smallest blocked benign score
and v_lo is the largest benign score that is not blocked. The calibration data cannot distinguish thresholds inside that
interval. Because the blocked set is defined by the comparison score >= t, tied benign scores are always blocked or
passed together, and k may exceed the nominal f * N (for N = 399 and f = 0.01 the linear convention blocks four
benigns, 4 / 399 = 1.003 percent).

Over the interval, the miss rate FNR(t) = share of injections with score < t
  - reaches its maximum share(score < v_hi) at t = v_hi (attained), and
  - approaches its infimum share(score <= v_lo) as t falls towards v_lo (not attained, because v_lo is excluded).
The false-positive rate on any other benign set, share(score >= t), runs from share(score >= v_hi) at t = v_hi up to its
supremum share(score > v_lo).

The guaranteed threshold (strict_threshold) is the smallest observed benign score s with share(benign >= s) <= f, or a
value just above the largest benign score when no observed score qualifies; it blocks at most floor(f * N) benigns.
"""
from __future__ import annotations
import numpy as np
from strict_threshold import strict_threshold


def convention_interval(p_ben, fpr=0.01, method="linear"):
    p = np.asarray(p_ben, float)
    t_c = float(np.quantile(p, 1.0 - fpr, method=method))
    blk = p >= t_c
    k = int(blk.sum())
    v_hi = float(p[blk].min()) if k else float(np.nextafter(p.max(), np.inf))
    v_lo = float(p[~blk].max()) if (~blk).any() else float("-inf")
    return dict(t_conv=t_c, k=k, n=int(len(p)), calFPR=k / len(p), v_lo=v_lo, v_hi=v_hi,
                n_ben_at_v_lo=int((p == v_lo).sum()), n_ben_at_v_hi=int((p == v_hi).sum()))


def fnr_at(pa, t):
    pa = np.asarray(pa, float); return float((pa < t).mean()) if len(pa) else float("nan")


def fnr_high(pa, iv):
    """Largest miss rate over the interval, attained at t = v_hi."""
    return fnr_at(pa, iv["v_hi"])


def fnr_low(pa, iv):
    """Smallest miss rate over the interval (an infimum, approached as t falls to the excluded end v_lo)."""
    pa = np.asarray(pa, float); return float((pa <= iv["v_lo"]).mean()) if len(pa) else float("nan")


def fnr_low_closed(pa, iv):
    """The earlier report's low end: the miss rate at t = v_lo itself, where one more tied group of benigns is blocked."""
    return fnr_at(pa, iv["v_lo"])


def fpr_high_end(pb, iv):
    """False-positive rate on another benign set at t = v_hi (the strict end of the interval)."""
    pb = np.asarray(pb, float); return float((pb >= iv["v_hi"]).mean()) if len(pb) else float("nan")


def fpr_low_end(pb, iv):
    """Supremum of the false-positive rate on another benign set over the interval (the permissive end)."""
    pb = np.asarray(pb, float); return float((pb > iv["v_lo"]).mean()) if len(pb) else float("nan")


def guaranteed(p_ben, fpr=0.01):
    """(threshold, blocked count, achieved calibration FPR) of the strict guaranteed threshold."""
    return strict_threshold(p_ben, fpr)


def boot_share(ind, B=1000, seed=0):
    """95 percent bootstrap interval of the mean of a 0/1 vector (resampling items)."""
    x = np.asarray(ind, float); rng = np.random.default_rng(seed); n = len(x)
    v = [x[rng.integers(0, n, n)].mean() for _ in range(B)]
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def top_tie(p_ben, fpr=0.01):
    """Size of the tied group at the largest benign score and the cap floor(f * N): the earlier guaranteed-threshold
    routine exceeds the cap exactly when the first is larger than the second."""
    p = np.asarray(p_ben, float); return int((p == p.max()).sum()), int(np.floor(fpr * len(p) + 1e-9))
