"""A guaranteed threshold that always satisfies the false-positive cap.

Decision rule everywhere in this project: block a text if its score is at or above the threshold. For a target
false-positive rate f on a calibration set of benign scores, the guaranteed threshold is the smallest s such that the
share of calibration benigns at or above s is at most f. score_diagnostics.thresholds searches s among the benign
scores themselves and, when none qualifies (the top scores tie and the tied group is larger than f allows), falls
back to the largest benign score, which blocks the whole tied group and exceeds the cap. strict_threshold instead
takes s just above the largest benign score in that case: it blocks no calibration benign, so the cap holds, and the
miss rate at s is the share of injections scoring at or below the largest benign. Where a qualifying benign score
exists the two routines agree exactly."""
from __future__ import annotations
import numpy as np


def strict_threshold(p_ben, fpr=0.01):
    """Returns (threshold, blocked count on the calibration set, achieved calibration FPR)."""
    p = np.asarray(p_ben, float); cand = np.unique(p)
    for s in cand:
        if (p >= s).mean() <= fpr: return float(s), int((p >= s).sum()), float((p >= s).mean())
    s = float(np.nextafter(cand[-1], np.inf))
    return s, 0, 0.0


def loo_fpr(p_ben, fpr=0.01):
    """Leave-one-out estimate of the deployment false-positive rate of strict_threshold: for each benign, the threshold
    is set on the others and the held-out benign is scored against it."""
    p = np.asarray(p_ben, float); n = len(p); hits = 0
    for i in range(n):
        s, _, _ = strict_threshold(np.delete(p, i), fpr); hits += int(p[i] >= s)
    return hits / n


def fnr(p_atk, t):
    p_atk = np.asarray(p_atk, float); return float((p_atk < t).mean()) if len(p_atk) else float("nan")
