"""Task-drift probe: a behavioral guard that reads the protected model itself. The model is given a task, then the
untrusted content, then a repeat of the task; hidden states on the repeated task are pooled and a linear probe is
trained to tell whether the content changed the model's representation of what it is supposed to do. An injection
that works must change behavior, so a probe on behavior can be evaded only by injections that fail."""
from __future__ import annotations
import numpy as np

TASKS = {
    "summarize": ("Summarize the key information in the content below.", "Now summarize the key information in the content above."),
    "qa":        ("Answer using only the content below: what is the main subject of the content?", "Now answer: what is the main subject of the content above?"),
    "extract":   ("List the named people, places and organizations in the content below.", "Now list the named people, places and organizations in the content above."),
}
SYSTEM = "You are a helpful assistant."
MAX_CONTENT_TOKENS = 448


def _truncate(tok, content, max_tokens=MAX_CONTENT_TOKENS):
    ids = tok(content, add_special_tokens=False).input_ids
    return content if len(ids) <= max_tokens else tok.decode(ids[:max_tokens])


def build_text(tok, task_key, content):
    task, echo = TASKS[task_key]
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"{task}\n\nContent:\n{content}\n\n{echo}"}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)


def echo_span(tok, task_key):
    """Number of trailing tokens that belong to the repeated task, and the number of template tokens after it."""
    task, echo = TASKS[task_key]
    n_echo = len(tok(echo, add_special_tokens=False).input_ids)
    full = tok(build_text(tok, task_key, "x"), add_special_tokens=False).input_ids
    noecho = tok(build_text(tok, task_key, "x").replace(echo, ""), add_special_tokens=False).input_ids
    tail = len(full) - len(noecho) - n_echo            # template tokens after the echo (e.g. end-of-turn markers)
    return n_echo, max(tail, 0)


def extract_features(model, tok, contents, task_key, layers, batch=4, show_every=100):
    """Mean hidden state over the echo tokens at each requested layer. Returns {layer: (n, d) float16}."""
    import torch
    n_echo, tail = echo_span(tok, task_key); tok.padding_side = "right"
    out = {L: [] for L in layers}
    for i in range(0, len(contents), batch):
        texts = [build_text(tok, task_key, _truncate(tok, c)) for c in contents[i:i + batch]]
        enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            hs = model(**enc, output_hidden_states=True).hidden_states
        lens = enc["attention_mask"].sum(1).tolist()
        for L in layers:
            h = hs[L]
            for b, ln in enumerate(lens):
                out[L].append(h[b, ln - tail - n_echo: ln - tail].float().mean(0).cpu().numpy().astype(np.float16))
        if show_every and (i // batch) % (show_every // batch) == 0: print(f"  features {min(i + batch, len(contents))}/{len(contents)}")
    return {L: np.stack(v) for L, v in out.items()}


def fit_probe(Xtr, ytr, Xva, yva, Cs=(0.01, 0.1, 1.0)):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    sc = StandardScaler().fit(Xtr.astype(np.float32)); best = None
    for C in Cs:
        clf = LogisticRegression(C=C, max_iter=3000, class_weight="balanced").fit(sc.transform(Xtr.astype(np.float32)), ytr)
        au = roc_auc_score(yva, clf.predict_proba(sc.transform(Xva.astype(np.float32)))[:, 1])
        if best is None or au > best[0]: best = (au, C, clf)
    return dict(scaler=sc, clf=best[2], C=best[1], val_auroc=best[0])


def probe_scores(P, X):
    return P["clf"].predict_proba(P["scaler"].transform(np.asarray(X, np.float32)))[:, 1]


def host_percentile(scores, host_scores):
    """Score -> share of host (benign) scores strictly below it; a scale-free rank usable across detectors."""
    hs = np.sort(np.asarray(host_scores)); return np.searchsorted(hs, np.asarray(scores), side="left") / len(hs)
