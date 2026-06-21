"""
metrics.py — Security-asymmetric calibration metric harness
============================================================
Project: Calibration Collapse under Security Shift in Prompt-Injection Detectors
Author : Md Anas Biswas (University of Portsmouth)

This is the DATASET-INDEPENDENT metric harness. Build and trust this first;
everything downstream (transport / LODO cells, ranking-reversal stats) calls it.

Conventions (locked in the concept note):
  - attack = positive class = 1 ; benign = 0
  - detector outputs p = P(attack) in [0, 1]
  - predicted benign when p < t  (t = operating threshold)
  - a MISS (false negative) = a true attack predicted benign  (y=1 and p<t)
  - benign-confidence on a sample = (1 - p)
  - N+ = number of attack samples  (denominators are conditioned on attacks)

Metric tiers (decided):
  1. S            -> HEADLINE: severity per miss, weight-free, base-rate-INVARIANT
  2. ECE_atk      -> PRIMARY companion: attack-conditional calibration, weight-free
  3. SeverityRisk(kappa) -> SECONDARY: cost-weighted family, report as a sweep
Supporting: FNR, FNCR (=FNR*S), HCFN(tau), CCI (collapse), pi*FNCR (deployed risk).

Only dependency: numpy.
"""

import numpy as np

__all__ = [
    "fnr", "fncr", "severity_S", "hcfn_rate", "hcfn_share_of_misses",
    "ece_pooled", "ece_attack_conditional", "severity_risk", "severity_risk_sweep",
    "cci", "deployed_risk", "bootstrap_ci", "all_metrics",
    "base_rate_invariance_check",
]

_EPS = 1e-12


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _prep(y_true, p):
    """Coerce to arrays; basic validation."""
    y = np.asarray(y_true).astype(int).ravel()
    p = np.asarray(p, dtype=float).ravel()
    if y.shape != p.shape:
        raise ValueError(f"y_true and p length mismatch: {y.shape} vs {p.shape}")
    if p.min() < -_EPS or p.max() > 1 + _EPS:
        raise ValueError("p must be probabilities in [0, 1].")
    return y, np.clip(p, 0.0, 1.0)


# --------------------------------------------------------------------------- #
# frequency / severity (attack-conditional)
# --------------------------------------------------------------------------- #
def fnr(y_true, p, t=0.5):
    """False-negative RATE = (1/N+) * #{attacks with p < t}.  How OFTEN you miss."""
    y, p = _prep(y_true, p)
    atk = y == 1
    nplus = atk.sum()
    if nplus == 0:
        return np.nan
    return np.sum(atk & (p < t)) / nplus


def fncr(y_true, p, t=0.5):
    """Severity-weighted miss rate = (1/N+) * sum_{attacks} (1-p) * 1{p<t}.
    A refinement of FNR (FNCR <= FNR always)."""
    y, p = _prep(y_true, p)
    atk = y == 1
    nplus = atk.sum()
    if nplus == 0:
        return np.nan
    miss = atk & (p < t)
    return np.sum(1.0 - p[miss]) / nplus


def severity_S(y_true, p, t=0.5, min_misses=10):
    """HEADLINE metric. S = FNCR / FNR = mean(1-p | y=attack, p<t).
    The mean benign-confidence of the misses: how CONFIDENTLY you miss.
    Base-rate-invariant (depends only on the attack class + frozen t).

    Returns:
      0.0     if there are no misses (convention),
      np.nan  if there are fewer than `min_misses` misses (NOT estimable),
      else    the severity in [0, 1].
    """
    y, p = _prep(y_true, p)
    miss = (y == 1) & (p < t)
    m = int(miss.sum())
    if m == 0:
        return 0.0
    if m < min_misses:
        return np.nan
    return float(np.mean(1.0 - p[miss]))


def hcfn_rate(y_true, p, t=0.5, tau=0.9):
    """High-confidence false-negative rate = (1/N+) * #{attack, p<t, (1-p)>tau}.
    Fraction of ALL attacks that are both missed and confidently waved through."""
    y, p = _prep(y_true, p)
    atk = y == 1
    nplus = atk.sum()
    if nplus == 0:
        return np.nan
    cond = atk & (p < t) & ((1.0 - p) > tau)
    return np.sum(cond) / nplus


def hcfn_share_of_misses(y_true, p, t=0.5, tau=0.9):
    """HCFN(tau)/FNR = P((1-p) > tau | miss). Share of misses that are confident.
    Base-rate-invariant (attack-conditional)."""
    f = fnr(y_true, p, t)
    if f is None or np.isnan(f) or f == 0:
        return np.nan
    return hcfn_rate(y_true, p, t, tau) / f


# --------------------------------------------------------------------------- #
# calibration
# --------------------------------------------------------------------------- #
def _ece_from_subset(p_sub, correct_sub, n_bins=15):
    """Equal-width-bin ECE on a subset.
    p_sub      : predicted confidence in the attack class for each sample
    correct_sub: 1 if the predicted class == true class, else 0
    """
    if len(p_sub) == 0:
        return np.nan
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p_sub, bins[1:-1]), 0, n_bins - 1)
    N = len(p_sub)
    ece = 0.0
    for b in range(n_bins):
        sel = idx == b
        nb = int(sel.sum())
        if nb == 0:
            continue
        conf = p_sub[sel].mean()
        acc = correct_sub[sel].mean()
        ece += (nb / N) * abs(acc - conf)
    return float(ece)


def ece_pooled(y_true, p, t=0.5, n_bins=15):
    """STANDARD pooled ECE (kept only for CONTRAST). Class-marginal, base-rate
    dependent. This is the metric the paper argues is insufficient/non-binding."""
    y, p = _prep(y_true, p)
    pred = (p >= t).astype(int)
    conf = np.where(pred == 1, p, 1.0 - p)      # confidence in predicted class
    correct = (pred == y).astype(float)
    return _ece_from_subset(conf, correct, n_bins)


def ece_attack_conditional(y_true, p, t=0.5, n_bins=15):
    """PRIMARY companion to S. Calibration of P(attack)=p restricted to TRUE
    attacks: within each confidence bin, |mean(p) - fraction-correctly-flagged|.
    Weight-free (no cross-class weights) and base-rate-invariant.

    Design note: computed over {y == attack} only. Confidence = p (prob of the
    attack class). 'Correct' = predicted attack (p >= t). This is the honest
    'ECE on attacks' the reviewer will ask about -- and that is the point.
    """
    y, p = _prep(y_true, p)
    atk = y == 1
    if atk.sum() == 0:
        return np.nan
    p_atk = p[atk]
    correct = (p_atk >= t).astype(float)        # true label is attack for all
    return _ece_from_subset(p_atk, correct, n_bins)


# --------------------------------------------------------------------------- #
# secondary cost-weighted family (sensitivity sweep)
# --------------------------------------------------------------------------- #
def severity_risk(y_true, p, t=0.5, kappa=10.0):
    """SECONDARY, cost-weighted. SeverityRisk(kappa) = kappa * FNCR + FPR.
    kappa = relative cost of a confident missed attack vs a false alarm.
    Report as a SWEEP over kappa, never a single number (see severity_risk_sweep).
    """
    y, p = _prep(y_true, p)
    fp_rate = _fpr(y, p, t)
    fc = fncr(y, p, t)
    if np.isnan(fc) or np.isnan(fp_rate):
        return np.nan
    return kappa * fc + fp_rate


def severity_risk_sweep(y_true, p, t=0.5, kappas=(1, 3, 10, 30, 100)):
    """SeverityRisk over a grid of kappa -> {kappa: value}. The whole point of
    the secondary tier is that you report the curve and show conclusions are
    robust across kappa, rather than defending one weighting."""
    return {float(k): severity_risk(y_true, p, t, k) for k in kappas}


def _fpr(y, p, t):
    ben = y == 0
    nneg = ben.sum()
    if nneg == 0:
        return np.nan
    return np.sum(ben & (p >= t)) / nneg


# --------------------------------------------------------------------------- #
# dynamics + deployed risk
# --------------------------------------------------------------------------- #
def cci(metric_clean, metric_shift):
    """Calibration Collapse Index = relative degradation of a metric
    in-distribution -> shifted.  CCI = (shift - clean) / clean.
    Pass ECE_atk (primary) or FNCR. Positive = collapse."""
    if metric_clean is None or np.isnan(metric_clean) or abs(metric_clean) < _EPS:
        return np.nan
    return (metric_shift - metric_clean) / metric_clean


def deployed_risk(y_true, p, t=0.5, pi=None):
    """DEPLOYED risk (base-rate DEPENDENT, on purpose). Expected confident-miss
    mass per input at deployment prevalence pi:  pi * FNCR.
    If pi is None, uses the empirical attack prevalence in (y_true)."""
    y, p = _prep(y_true, p)
    if pi is None:
        pi = (y == 1).mean()
    return pi * fncr(y, p, t)


# --------------------------------------------------------------------------- #
# uncertainty
# --------------------------------------------------------------------------- #
def bootstrap_ci(metric_fn, y_true, p, n_boot=1000, alpha=0.05, seed=0, **kwargs):
    """Percentile bootstrap CI for any metric_fn(y_true, p, **kwargs).
    Returns (point_estimate, lo, hi). Resamples (y, p) pairs with replacement.
    """
    y, p = _prep(y_true, p)
    rng = np.random.default_rng(seed)
    n = len(y)
    point = metric_fn(y, p, **kwargs)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        stats[b] = metric_fn(y[idx], p[idx], **kwargs)
    stats = stats[~np.isnan(stats)]
    if len(stats) == 0:
        return point, np.nan, np.nan
    lo = np.percentile(stats, 100 * alpha / 2)
    hi = np.percentile(stats, 100 * (1 - alpha / 2))
    return point, float(lo), float(hi)


# --------------------------------------------------------------------------- #
# one-call convenience
# --------------------------------------------------------------------------- #
def all_metrics(y_true, p, t=0.5, tau=0.9, n_bins=15, min_misses=10, pi=None):
    """Compute the full panel for one (y_true, p, t) cell."""
    return {
        "FNR":            fnr(y_true, p, t),
        "FNCR":           fncr(y_true, p, t),
        "S":              severity_S(y_true, p, t, min_misses),
        "HCFN":           hcfn_rate(y_true, p, t, tau),
        "HCFN_share":     hcfn_share_of_misses(y_true, p, t, tau),
        "ECE_atk":        ece_attack_conditional(y_true, p, t, n_bins),
        "ECE_pooled":     ece_pooled(y_true, p, t, n_bins),
        "deployed_risk":  deployed_risk(y_true, p, t, pi),
        "n_attacks":      int(np.sum(np.asarray(y_true) == 1)),
        "n_misses":       int(np.sum((np.asarray(y_true) == 1) &
                                     (np.asarray(p, float) < t))),
    }


# --------------------------------------------------------------------------- #
# THE load-bearing check (run this FIRST, per the plan)
# --------------------------------------------------------------------------- #
def base_rate_invariance_check(y_true, p, t=0.5, tau=0.9,
                               pis=(0.5, 0.1, 0.01, 0.001),
                               seed=0, tol=1e-9):
    """Resample BENIGNS to hit several attack prevalences pi, keeping the attack
    scores and t frozen, then recompute metrics at each pi.

    EXPECT: S, FNR, HCFN_share, ECE_atk  -> FLAT across pi (invariant).
            ECE_pooled                   -> MOVES with pi.

    Returns: (rows, passed)
      rows   = list of dicts, one per pi
      passed = True iff every invariant metric is constant within `tol`
    """
    y, p = _prep(y_true, p)
    rng = np.random.default_rng(seed)
    atk_mask = y == 1
    ben_mask = y == 0
    p_atk = p[atk_mask]
    p_ben_pool = p[ben_mask]
    n_atk = len(p_atk)
    if n_atk == 0 or len(p_ben_pool) == 0:
        raise ValueError("Need both attacks and benigns to run the check.")

    invariant_keys = ["S", "FNR", "HCFN_share", "ECE_atk"]
    rows, history = [], {k: [] for k in invariant_keys}

    for pi in pis:
        # number of benigns to give attack prevalence pi  ->  n_ben = n_atk*(1-pi)/pi
        n_ben = max(1, int(round(n_atk * (1 - pi) / pi)))
        ben_idx = rng.integers(0, len(p_ben_pool), n_ben)
        p_ben = p_ben_pool[ben_idx]
        yy = np.concatenate([np.ones(n_atk, int), np.zeros(n_ben, int)])
        pp = np.concatenate([p_atk, p_ben])
        m = all_metrics(yy, pp, t=t, tau=tau)
        m["pi"] = pi
        m["n_benign"] = n_ben
        rows.append(m)
        for k in invariant_keys:
            history[k].append(m[k])

    passed = True
    for k in invariant_keys:
        vals = np.array([v for v in history[k] if not np.isnan(v)])
        if len(vals) > 1 and (vals.max() - vals.min()) > tol:
            passed = False
    return rows, passed


# --------------------------------------------------------------------------- #
# self-test
# --------------------------------------------------------------------------- #
def _synthetic(seed=0, n_attack=2000, n_benign=2000):
    """Synthetic detector scores with a deliberate sprinkle of CONFIDENT misses."""
    rng = np.random.default_rng(seed)
    # attacks: mostly high p (correctly flagged) but a confident-miss tail near 0
    p_atk = np.clip(rng.beta(5, 2, n_attack), 0, 1)
    n_conf_miss = int(0.05 * n_attack)
    p_atk[:n_conf_miss] = rng.uniform(0.0, 0.05, n_conf_miss)   # confident benign on real attacks
    # benigns: mostly low p
    p_ben = np.clip(rng.beta(2, 5, n_benign), 0, 1)
    y = np.concatenate([np.ones(n_attack, int), np.zeros(n_benign, int)])
    p = np.concatenate([p_atk, p_ben])
    return y, p


if __name__ == "__main__":
    y, p = _synthetic()
    t = 0.5

    print("=" * 64)
    print("METRIC PANEL (t = %.2f)" % t)
    print("=" * 64)
    for k, v in all_metrics(y, p, t=t).items():
        print(f"  {k:14s} : {v}")

    print("\nSeverityRisk(kappa) sweep (secondary):")
    for k, v in severity_risk_sweep(y, p, t=t).items():
        print(f"  kappa={k:6.1f} : {v:.4f}")

    print("\nBootstrap 95% CI for S:")
    pt, lo, hi = bootstrap_ci(severity_S, y, p, n_boot=500, t=t)
    print(f"  S = {pt:.4f}  [{lo:.4f}, {hi:.4f}]")

    print("\n" + "=" * 64)
    print("BASE-RATE INVARIANCE CHECK (the load-bearing assumption)")
    print("=" * 64)
    rows, passed = base_rate_invariance_check(y, p, t=t)
    hdr = f"{'pi':>8} {'S':>8} {'FNR':>8} {'HCFN_sh':>8} {'ECE_atk':>9} {'ECE_pool':>9}"
    print(hdr)
    for r in rows:
        print(f"{r['pi']:>8.3f} {r['S']:>8.4f} {r['FNR']:>8.4f} "
              f"{r['HCFN_share']:>8.4f} {r['ECE_atk']:>9.4f} {r['ECE_pooled']:>9.4f}")
    print("-" * 64)
    print("EXPECT: S / FNR / HCFN_sh / ECE_atk flat;  ECE_pool moves with pi.")
    print("INVARIANCE CHECK:", "PASS \u2713" if passed else "FAIL \u2717")
