"""Task state: the residual stream at the positions where the model starts its answer, read and patched.

The task state of a prompt is the residual stream after every decoder layer at the last K prompt positions, the chat
template's tokens that follow the user's content (for Qwen 2.5: <|im_end|>, newline, <|im_start|>, assistant, newline).
These tokens are the same in every prompt, so the states of an attacked prompt and of its clean twin (the same document
without the injected sentence) line up position by position, whatever the documents' lengths.

Three operations, all on one batch at a time so the caller fixes the batch composition and every condition sees the
same padding:
  capture   the task state of each prompt: the prompt pass of the same generate() call the model answers with,
            stopped after one token, so the states are exactly those of the answering run;
  generate  greedy answers (the call and settings of targets.generate_batch) while the task state is replaced ('set')
            or shifted ('add') at chosen layers during the prompt pass; decode steps are never touched;
  force     greedy answers whose first token is fixed in advance, with no state changed.

The instruction direction of a layer is the mean shift a user-issued instruction causes: the state with an extra
instruction in the user turn minus the state without it, averaged over held-out structural pairs. Shifts of attacked
prompts are read as a fraction of it: <attacked - clean, d> / <d, d>.

Statistics: a category-stratified AUROC (only pairs of a success and a failure of the same category are compared) with
a cluster bootstrap over injections within categories; token F1 between two outputs; a degenerate-output check."""
from __future__ import annotations
import re
from collections import Counter
import numpy as np

SENTINEL = "@@TASK_STATE_CONTENT@@"


def chat(tok, system, user):
    """The text targets.generate_batch feeds the model (system turn, user turn, generation prompt)."""
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": str(user)}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def suffix_ids(tok, system):
    """Token ids of the template text after the user's content. Must tokenize the same alone and inside a prompt."""
    t = chat(tok, system, SENTINEL); s = t[t.rindex(SENTINEL) + len(SENTINEL):]
    ids = tok(s, add_special_tokens=False).input_ids
    full = tok(chat(tok, system, "Some content."), add_special_tokens=False).input_ids
    assert len(ids) >= 2 and full[-len(ids):] == ids, f"template suffix does not tokenize stably: {s!r}"
    return ids


def decoder(model):
    """The decoder stack (embeddings, layers, final norm), with any LoRA adapter active."""
    m = model.get_base_model() if hasattr(model, "get_base_model") else model
    return m.model


def decoder_layers(model):
    return decoder(model).layers


class LayerHooks:
    """Forward hooks on every decoder layer. On a prompt pass (sequence length above one) a hook can record the residual
    stream at the last K positions and replace ('set') or shift ('add') it there; decode steps pass through untouched.
    spec: {layer: (kind, tensor [B, K, H])}. Recorded states go to rec[layer], float16 on the CPU, before any change."""

    def __init__(self, model, K):
        self.layers = decoder_layers(model); self.K = K; self.record = False; self.rec = {}; self.spec = {}; self.prompt_passes = 0
        self.handles = [layer.register_forward_hook(self._make(i)) for i, layer in enumerate(self.layers)]

    def _make(self, i):
        def hook(module, args, out):
            h = out[0] if isinstance(out, tuple) else out
            if h.dim() != 3 or h.shape[1] <= 1: return None
            if i == 0: self.prompt_passes += 1
            if self.record: self.rec[i] = h[:, -self.K:, :].detach().half().cpu().clone()
            s = self.spec.get(i)
            if s is None: return None
            kind, v = s; v = v.to(h.device, h.dtype); h = h.clone()
            if kind == "set": h[:, -self.K:, :] = v
            elif kind == "add": h[:, -self.K:, :] = h[:, -self.K:, :] + v
            else: raise ValueError(kind)
            return (h,) + tuple(out[1:]) if isinstance(out, tuple) else h
        return hook

    def close(self):
        for h in self.handles: h.remove()
        self.handles = []


def encode(tok, prompts, system, sfx):
    """Left-padded batch exactly as targets.generate_batch builds it; every row must end with the template suffix."""
    import torch
    tok.padding_side = "left"
    enc = tok([chat(tok, system, p) for p in prompts], return_tensors="pt", padding=True, truncation=True, max_length=2048)
    tail = enc["input_ids"][:, -len(sfx):]
    assert bool((tail == torch.tensor(sfx)[None, :]).all()), "a prompt was truncated or the template suffix differs"
    return enc


def _generate(model, tok, enc, max_new_tokens):
    """The generation call of targets.generate_batch (greedy; the model's own generation config otherwise)."""
    import torch
    with torch.no_grad():
        return model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, temperature=None, top_p=None, pad_token_id=tok.pad_token_id)


def capture(model, hooks, tok, prompts, system, sfx):
    """Task state of one batch: float16 tensor [B, L, K, H], from the prompt pass of the answering call."""
    import torch
    enc = encode(tok, prompts, system, sfx).to(model.device)
    hooks.rec = {}; hooks.spec = {}; hooks.record = True
    try: _generate(model, tok, enc, 1)
    finally: hooks.record = False
    st = torch.stack([hooks.rec[i] for i in range(len(hooks.layers))], 1); hooks.rec = {}
    return st


def generate(model, hooks, tok, prompts, system, sfx, spec=None, force_first=None, max_new_tokens=160, record=False):
    """Greedy answers for one batch with the task state changed as spec says. force_first: one token id per row that
    is appended to the prompt and kept as the answer's first token (no state is changed then). With record=True the
    unchanged prompt-pass states come back too. Returns (outputs, first generated token ids, states or None)."""
    import torch
    enc = encode(tok, prompts, system, sfx).to(model.device); T0 = enc["input_ids"].shape[1]
    if force_first is not None:
        assert not spec, "force_first changes no state"
        f = torch.tensor(force_first, device=enc["input_ids"].device)[:, None]
        enc = dict(input_ids=torch.cat([enc["input_ids"], f], 1), attention_mask=torch.cat([enc["attention_mask"], torch.ones_like(f)], 1))
    hooks.rec = {}; hooks.spec = dict(spec or {}); hooks.record = record
    try: gen = _generate(model, tok, enc, max_new_tokens)
    finally: hooks.spec = {}; hooks.record = False
    outs = [tok.decode(gen[j][T0:], skip_special_tokens=True).strip() for j in range(gen.shape[0])]
    first = [int(gen[j][T0]) for j in range(gen.shape[0])]
    st = torch.stack([hooks.rec[i] for i in range(len(hooks.layers))], 1) if record else None; hooks.rec = {}
    return outs, first, st


def equal_norm_noise(ref, seeds):
    """Gaussian directions with the norm of ref along the last axis. ref [B, ...]; one seed per row, so a row's noise
    does not depend on the batch it falls in."""
    import torch
    out = []
    for b, s in enumerate(seeds):
        g = torch.Generator().manual_seed(int(s) % (2 ** 63)); r = torch.randn(ref[b].shape, generator=g, dtype=torch.float32)
        out.append(r / r.norm(dim=-1, keepdim=True) * ref[b].float().norm(dim=-1, keepdim=True))
    return torch.stack(out).to(ref.dtype)


def seed_of(key):
    return int(key[:15], 16)


def proj_fraction(delta, d):
    """<delta, d> / <d, d> along the last axis (float32). delta [..., H], d [H] or broadcastable."""
    delta = np.asarray(delta, np.float32); d = np.asarray(d, np.float32)
    return (delta * d).sum(-1) / (d * d).sum(-1)


def cosine(a, b):
    a = np.asarray(a, np.float32); b = np.asarray(b, np.float32)
    return (a * b).sum(-1) / (np.linalg.norm(a, axis=-1) * np.linalg.norm(b, axis=-1) + 1e-12)


def _cmp(sp, sn):
    return (sp[:, None] > sn[None, :]).astype(np.float64) + 0.5 * (sp[:, None] == sn[None, :])


def strat_auroc(score, label, stratum):
    """AUROC over pairs of a success and a failure from the same stratum, pooled over strata."""
    s = np.asarray(score, float); y = np.asarray(label, bool); g = np.asarray(stratum); num = den = 0.0
    for c in np.unique(g):
        p = (g == c) & y; q = (g == c) & ~y
        if p.any() and q.any(): num += _cmp(s[p], s[q]).sum(); den += p.sum() * q.sum()
    return float(num / den) if den else float("nan")


def strat_auroc_boot(score, label, stratum, cluster, B=2000, seed=0):
    """95 percent interval of strat_auroc by a cluster bootstrap: clusters (injections) resampled within each stratum."""
    s = np.asarray(score, float); y = np.asarray(label, bool); g = np.asarray(stratum); cl = np.asarray(cluster); pre = []
    for c in np.unique(g):
        m = g == c; p = m & y; q = m & ~y
        if not (p.any() and q.any()): continue
        ids = np.unique(cl[m]); pos = {v: k for k, v in enumerate(ids)}
        pre.append((len(ids), np.array([pos[v] for v in cl[p]]), np.array([pos[v] for v in cl[q]]), _cmp(s[p], s[q])))
    if not pre: return float("nan"), float("nan")
    rng = np.random.default_rng(seed); vals = []
    for _ in range(B):
        num = den = 0.0
        for n_ids, ip, iq, C in pre:
            w = np.bincount(rng.integers(0, n_ids, n_ids), minlength=n_ids).astype(float); wp, wq = w[ip], w[iq]
            num += wp @ C @ wq; den += wp.sum() * wq.sum()
        if den: vals.append(num / den)
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def words(text):
    return re.findall(r"\w+", (text or "").lower())


def token_f1(a, b):
    ta, tb = words(a), words(b)
    if not ta or not tb: return 0.0
    common = sum((Counter(ta) & Counter(tb)).values())
    if not common: return 0.0
    p, r = common / len(ta), common / len(tb); return 2 * p * r / (p + r)


def degenerate(output):
    """Empty or near-empty, or 20 words or more of which under 30 percent are distinct."""
    w = words(output)
    return len((output or "").strip()) < 20 or (len(w) >= 20 and len(set(w)) / len(w) < 0.3)
