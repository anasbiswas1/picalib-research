"""
detectors.py — detector panel (starts with the cheapest competent one)
======================================================================
Gate 2 uses slot 2: frozen e5-base-v2 sentence embeddings + XGBoost.
Every detector here must emit a continuous p = P(attack) (the study is about
confidence, not labels).

Split out so the full panel later reuses the same embed/train/threshold code.
Embedding is separated from the classifier so embeddings can be cached and
reused across classifiers (XGBoost, MLP, ...).
"""

import numpy as np


# --------------------------------------------------------------------------- #
# embeddings (frozen)
# --------------------------------------------------------------------------- #
def embed_e5(texts, model_name="intfloat/e5-base-v2", batch_size=64,
             device=None, prefix="query: ", show_progress=True):
    """Frozen e5-base-v2 embeddings, L2-normalised.
    e5 was trained with 'query: ' / 'passage: ' prefixes; we use 'query: ' for
    every input (symmetric classification use). Returns (n, 768) float32.
    """
    from sentence_transformers import SentenceTransformer
    import torch
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(model_name, device=device)
    texts = [prefix + str(t) for t in texts]
    return model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                        show_progress_bar=show_progress, convert_to_numpy=True)


# --------------------------------------------------------------------------- #
# classifier
# --------------------------------------------------------------------------- #
def train_xgb(X, y, seed=0, scale_pos_weight=None):
    """XGBoost on frozen embeddings. Returns a fitted classifier."""
    from xgboost import XGBClassifier
    y = np.asarray(y)
    if scale_pos_weight is None:
        n_pos = max(1, int((y == 1).sum()))
        n_neg = max(1, int((y == 0).sum()))
        scale_pos_weight = n_neg / n_pos
    clf = XGBClassifier(
        n_estimators=400, max_depth=6, learning_rate=0.1,
        subsample=0.9, colsample_bytree=0.9, eval_metric="logloss",
        n_jobs=4, random_state=seed, scale_pos_weight=scale_pos_weight,
    )
    clf.fit(X, y)
    return clf


def predict_p(clf, X):
    """p = P(attack)."""
    return clf.predict_proba(X)[:, 1]


# --------------------------------------------------------------------------- #
# operating threshold (set on SOURCE, then frozen — the transfer experiment)
# --------------------------------------------------------------------------- #
def threshold_at_fpr(p_benign, target_fpr=0.01):
    """Pick t so that ~target_fpr of benign inputs are flagged as attack.
    t = (1 - target_fpr) quantile of the benign score distribution."""
    p_benign = np.asarray(p_benign, dtype=float)
    if len(p_benign) == 0:
        return 0.5
    return float(np.quantile(p_benign, 1.0 - target_fpr))


def auroc(y, p):
    """Discrimination, threshold-free. Returns NaN if only one class present."""
    from sklearn.metrics import roc_auc_score
    y = np.asarray(y)
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, p))


# --------------------------------------------------------------------------- #
# released inference-only detectors (no training; emit p = P(attack))
# --------------------------------------------------------------------------- #
def score_released(texts, model_name, batch_size=16, max_length=512, device=None,
                   positive_hints=("inject", "malicious", "jailbreak", "unsafe",
                                   "attack", "label_1", "harmful")):
    """Score texts with a released sequence-classification guard model.
    Returns p = P(attack) by softmax over logits, picking the 'attack' class via
    id2label (falls back to the last class). Handles long inputs by truncation.

    Examples:
      protectai/deberta-v3-base-prompt-injection-v2   (id2label SAFE/INJECTION)
      meta-llama/Llama-Prompt-Guard-2-86M             (gated; benign/malicious)
    """
    import numpy as np
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device).eval()

    id2label = getattr(model.config, "id2label", {}) or {}
    pos_idx = None
    for idx, lab in id2label.items():
        if any(h in str(lab).lower() for h in positive_hints):
            pos_idx = int(idx)
            break
    if pos_idx is None:
        pos_idx = model.config.num_labels - 1     # fallback: last class
    print(f"  {model_name}: id2label={id2label} -> attack class index {pos_idx}")

    out = []
    texts = [str(t) for t in texts]
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            enc = tok(texts[i:i + batch_size], return_tensors="pt", truncation=True,
                      max_length=max_length, padding=True).to(device)
            logits = model(**enc).logits
            p = torch.softmax(logits, dim=-1)[:, pos_idx].detach().cpu().numpy()
            out.append(p)
    return np.concatenate(out)
