"""Transfer of the notebook-12 severity-maximizing adversary to the structural detector.

Recovers which original attack each cached rewrite group paraphrases, verifies that recovery against the cached
released-detector scores, and provides the flat variant layout, the group-minimum (adaptive) selection and the
layout of the cached execution outputs.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def recover_subset(bip, REW, P5=None, PB=None, lam=1.0, min_margin=0.02):
    """Recover which original attack each rewrite group paraphrases. Two independent fingerprints: content-word
    overlap between the four rewrites and each candidate original, and (optionally) agreement between the cached
    flat scores of the group's original and the candidate's BIPIA panel score, for each released detector.
    Solved as a one-to-one assignment so no original is claimed twice. Independent of any random generator."""
    import re
    from scipy.optimize import linear_sum_assignment
    atk = bip[bip.label == 1].copy().reset_index().rename(columns={"index": "bip_index"})
    tok = lambda t: set(re.findall(r"[a-z0-9]{3,}", str(t).lower()))
    cand = [tok(t) for t in atk.text]
    S = np.zeros((len(REW), len(atk)))
    for i in range(len(REW)):
        rt = set().union(*[tok(r) for r in REW[i]]) if len(REW[i]) else set()
        S[i] = [len(rt & c) / max(1, len(rt | c)) for c in cand]
    cost = -S.copy()
    if P5 is not None and PB is not None:
        counts = np.array([1 + len(r) for r in REW]); first = np.r_[0, np.cumsum(counts)[:-1]]
        for t in P5:
            a = np.asarray(P5[t])[first][:, None]; b = np.asarray(PB[t])[atk.bip_index.values][None, :]
            cost += lam * np.abs(a - b)
    gi, cj = linear_sum_assignment(cost)
    rows = []
    for i, j in zip(gi, cj):
        others = np.delete(-cost[i], j)
        rows.append(dict(group=int(i), bip_index=int(atk.bip_index.iloc[j]), meta=atk.meta.iloc[j], text=atk.text.iloc[j],
                         sim=float(S[i, j]), margin=float(-cost[i, j] - others.max())))
    sub = pd.DataFrame(rows).sort_values("group").reset_index(drop=True)
    sub["instruction"] = sub.text.map(lambda t: t.split("\n")[-1].strip())
    sub["unique"] = ~sub.bip_index.duplicated(keep=False)
    sub["confident"] = sub.margin >= min_margin
    return sub


def flat_variants(sub, REW):
    """variants list, owner array, and index of each attack's original within the flat list."""
    variants, owner, first = [], [], []
    for i in range(len(sub)):
        first.append(len(variants)); variants.append(sub.text.iloc[i]); owner.append(i)
        for r in REW[i]:
            variants.append(r); owner.append(i)
    return variants, np.array(owner), np.array(first)


def alignment_check(p_flat, first, p_bip_full, bip_index, atol=2e-3, frac_ok=0.95):
    """The originals in the flat list were scored by the same model as the BIPIA panel; their scores must agree.
    Use it with both released detectors: agreement on two independent scorers at a tight tolerance is strong evidence."""
    a = np.asarray(p_flat)[first]; b = np.asarray(p_bip_full)[np.asarray(bip_index)]
    d = np.abs(a - b)
    ok = float((d < atol).mean())
    return dict(max_abs_diff=float(d.max()), frac_within_tol=ok, passed=bool(ok >= frac_ok))


def group_min_index(scores, owner):
    scores = np.asarray(scores); n = owner.max() + 1
    return np.array([np.where(owner == i)[0][int(np.argmin(scores[owner == i]))] for i in range(n)])


def exec_layout(n, source_tags=("protectai_v2", "prompt_guard_2")):
    """Index into exec_out.npy: originals first, then the selected rewrite per source detector, in that order."""
    lay = {"orig": np.arange(n)}
    for k, tag in enumerate(source_tags):
        lay[tag] = np.arange(n) + n * (k + 1)
    return lay
