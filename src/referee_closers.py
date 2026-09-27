"""Three scoring-only checks a referee will ask for: a wider guard panel, over-defense on benign documents that
legitimately carry instructions, and an injection-position sweep."""
from __future__ import annotations
import re
import numpy as np

# Additional public encoder guards. Each entry: tag -> list of candidate Hub ids (first that loads is used).
EXTRA_GUARDS = {
    "deepset_injection": ["deepset/deberta-v3-base-injection"],
    "protectai_v1":      ["protectai/deberta-v3-base-prompt-injection"],
    "piguard":           ["leolee99/PIGuard", "leolee99/InjecGuard"],
    "fmops_distilbert":  ["fmops/distilbert-prompt-injection"],
}

# Benign documents that legitimately contain imperatives (recipes, how-to). Candidate Hub datasets and text fields.
HOWTO_SOURCES = [
    ("corbt/all-recipes", "train", "input"),
    ("Hieu-Pham/kaggle_food_recipes", "train", "Instructions"),
    ("Shengtao/recipe", "train", "directions"),
]


def load_howto(n=500, min_chars=200, max_chars=1500, seed=0):
    """First candidate that loads; returns (texts, source_id) or ([], None)."""
    from datasets import load_dataset
    for cid, split, field in HOWTO_SOURCES:
        try:
            ds = load_dataset(cid, split=split)
            raw = ds[field]
            texts, seen = [], set()
            for t in raw:
                t = re.sub(r"\s+", " ", str(t if t is not None else "")).strip()
                if min_chars <= len(t) <= max_chars and t not in seen:
                    seen.add(t); texts.append(t)
            if len(texts) >= 100:
                rng = np.random.default_rng(seed)
                idx = rng.choice(len(texts), size=min(n, len(texts)), replace=False)
                return [texts[i] for i in sorted(idx)], cid
        except Exception:
            continue
    return [], None


def split_host_instruction(text):
    """BIPIA attack text is host + newline + injected instruction (last line)."""
    parts = text.rstrip().split("\n")
    return "\n".join(parts[:-1]).rstrip(), parts[-1].strip()


def _sentences(doc):
    parts = re.split(r"(?<=[a-z0-9]{2}[.!?])\s+(?=[\"'(A-Z])", doc.strip())
    return [p for p in parts if p]


def position_variants(text, rng):
    """start / middle / end placements of the same instruction in the same host, newline-delimited."""
    host, ins = split_host_instruction(text)
    out = {"end": host + "\n" + ins, "start": ins + "\n" + host}
    sents = _sentences(host)
    if len(sents) >= 3:
        k = rng.integers(1, len(sents))
        out["middle"] = " ".join(sents[:k]) + "\n" + ins + "\n" + " ".join(sents[k:])
    else:
        out["middle"] = out["end"]
    return out


def polarity_fix(p_direct, y_direct, scores_by_set):
    """If a guard ranks direct injections below benigns (AUROC < 0.5), its attack class was picked wrong: invert."""
    from sklearn.metrics import roc_auc_score
    a = roc_auc_score(y_direct, p_direct)
    if a < 0.5:
        return {k: 1.0 - v for k, v in scores_by_set.items()}, True, a
    return scores_by_set, False, a
