"""Three scoring-only checks a referee will ask for: a wider guard panel, over-defense on benign documents that
legitimately carry instructions, and an injection-position sweep."""
from __future__ import annotations
import re
import numpy as np

EXTRA_GUARDS = {
    "deepset_injection": ["deepset/deberta-v3-base-injection"],
    "protectai_v1":      ["protectai/deberta-v3-base-prompt-injection"],
    "piguard":           ["leolee99/PIGuard", "leolee99/InjecGuard"],
    "fmops_distilbert":  ["fmops/distilbert-prompt-injection"],
}

# Benign documents that legitimately contain imperatives. Wikibooks Cookbook (CC BY-SA 4.0) first; the rest are fallbacks.
HOWTO_SOURCES = [
    ("gossminn/wikibooks-cookbook", "main", None),          # nested: recipe_data.text_lines[].text, joined
    ("corbt/all-recipes", "train", "input"),
    ("Hieu-Pham/kaggle_food_recipes", "train", "Instructions"),
]


def _wikibooks_text(rec):
    rd = rec.get("recipe_data") or {}
    lines = rd.get("text_lines") or []
    return " ".join(str(l.get("text", "")) for l in lines if isinstance(l, dict) and l.get("text"))


def load_howto(n=500, min_chars=200, max_chars=1500, seed=0):
    """First candidate that loads; returns (texts, source_id) or ([], None)."""
    from datasets import load_dataset
    for cid, split, field in HOWTO_SOURCES:
        try:
            ds = load_dataset(cid, split=split)
            raw = [_wikibooks_text(r) for r in ds] if field is None else ds[field]
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
    parts = text.rstrip().split("\n")
    return "\n".join(parts[:-1]).rstrip(), parts[-1].strip()


def _sentences(doc):
    parts = re.split(r"(?<=[a-z0-9]{2}[.!?])\s+(?=[\"'(A-Z])", doc.strip())
    return [p for p in parts if p]


def position_variants(text, rng):
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
    from sklearn.metrics import roc_auc_score
    a = roc_auc_score(y_direct, p_direct)
    if a < 0.5:
        return {k: 1.0 - v for k, v in scores_by_set.items()}, True, a
    return scores_by_set, False, a
