"""How strongly an instruction pushes a model along the user's instruction direction, read from every attention head at
the positions where the answer starts and over the first answer tokens. Built on task_state and head_patching, which
are unchanged; nothing in the model is changed.

Reading. Forward pre-hooks on every layer's attention output projection (o_proj) read the heads' outputs (the
projection's input) over a window of W positions at the end of each row: the K template positions where the answer
starts, then the answer tokens appended after them (teacher forcing, the same tokens for every prompt of an item). One
forward pass of the decoder per batch, with position ids taken from the attention mask as generation computes them,
and no language-model head. For every row the hooks keep:
  sums  the running sum of the window per group of rows (the caller names a group for every row), [L, W, nh*dh] float32;
  proj  when reference directions are set, the row's dot product with each reference, layer by layer and separately
        for the template part and the answer part of the window: [rows, L, R, 2];
  pairs for pairs of differences between rows of the same batch, (a - c, b - d), the dot product <a - c, b - d> and the
        two squared sizes, layer by layer and per part: [pairs, L, 3, 2]. This is how the same sentence in two places is
        compared item by item.

Drive. With u a reference direction (in the base model, the fold mean of an instruction in the user turn minus an
ordinary sentence of the same length in the same place), the drive of a prompt pair (a, b) on an item is
<x_a - x_b, u> / <u, u> over the window, with u taken from the other fold of items (cross-fitting, so an item's own
noise never sits in its own reference). 1.0 is the push a user instruction gives in the base model; 0 is none.
"""
from __future__ import annotations
import numpy as np
from task_state import decoder, decoder_layers
from head_patching import head_dims


def encode_convs(tok, convs, sfx, ans_ids=None, max_length=4096):
    """Left-padded batch of conversations (message lists), rendered by the tokenizer's own chat template with the
    generation prompt and tokenized without adding special tokens again (the template already carries them), as the
    project's generation calls do. Every row must end with the template suffix sfx; ans_ids (one list per row, all the
    same length) are appended after it. Returns (input_ids, attention_mask) on the CPU."""
    import torch
    rows = []
    for c in convs:
        r = list(tok(tok.apply_chat_template(c, tokenize=False, add_generation_prompt=True), add_special_tokens=False)["input_ids"])
        assert r[-len(sfx):] == list(sfx), "a prompt does not end with the template suffix"
        rows.append(r)
    if ans_ids is not None:
        assert len(ans_ids) == len(rows) and len({len(a) for a in ans_ids}) == 1, "answer tokens: one list per row, all the same length"
        rows = [r + list(a) for r, a in zip(rows, ans_ids)]
    T = max(len(r) for r in rows); assert T <= max_length, f"a prompt has {T} tokens"
    ids = torch.full((len(rows), T), int(tok.pad_token_id), dtype=torch.long); am = torch.zeros((len(rows), T), dtype=torch.long)
    for j, r in enumerate(rows):
        ids[j, T - len(r):] = torch.tensor(r, dtype=torch.long); am[j, T - len(r):] = 1
    return ids, am


class DriveHooks:
    def __init__(self, model, W, K):
        self.layers = decoder_layers(model); self.L = len(self.layers); self.nh, self.dh = head_dims(model); self.D = self.nh * self.dh
        self.W, self.K = int(W), int(K); assert self.W >= self.K >= 1
        self.active = False; self.group = None; self.sums = {}; self.refs = None; self.proj = None; self.raw = None; self.passes = 0
        self.pidx = None; self.pd = None                    # local row indices of the batch's pairs [4, P] and their output [P, L, 3, 2]
        self.handles = [l.self_attn.o_proj.register_forward_pre_hook(self._make(i)) for i, l in enumerate(self.layers)]

    def set_refs(self, refs):
        """refs: [R, L, W, D] float32 (or None). Kept on the model's device."""
        import torch
        dev = self.layers[0].self_attn.o_proj.weight.device
        self.refs = None if refs is None else torch.as_tensor(refs, dtype=torch.float32).to(dev)
        if self.refs is not None: assert tuple(self.refs.shape[1:]) == (self.L, self.W, self.D), (tuple(self.refs.shape), (self.L, self.W, self.D))

    def _make(self, i):
        def hook(module, args):
            import torch
            if not self.active: return None
            x = args[0]
            if not isinstance(x, torch.Tensor) or x.dim() != 3 or x.shape[1] < self.W: return None
            if i == 0: self.passes += 1
            t = x[:, -self.W:, :].float()                                           # [B, W, D]
            for g, rows in self.group.items():
                s = self.sums.get(g)
                if s is None: s = self.sums[g] = torch.zeros(self.L, self.W, self.D, dtype=torch.float32, device=x.device)
                s[i] += t[rows].sum(0)
            if self.refs is not None:
                r = self.refs[:, i]                                                 # [R, W, D]
                self.proj[:, i, :, 0] = torch.einsum('bkd,rkd->br', t[:, :self.K], r[:, :self.K])
                if self.W > self.K: self.proj[:, i, :, 1] = torch.einsum('bkd,rkd->br', t[:, self.K:], r[:, self.K:])
            if self.pidx is not None:
                a = t[self.pidx[0]] - t[self.pidx[2]]; b = t[self.pidx[1]] - t[self.pidx[3]]                # [P, W, D]
                for part, sl in ((0, slice(0, self.K)), (1, slice(self.K, self.W))):
                    if sl.stop <= sl.start: continue
                    aa, bb = a[:, sl], b[:, sl]
                    self.pd[:, i, 0, part] = (aa * bb).sum((1, 2)); self.pd[:, i, 1, part] = (aa * aa).sum((1, 2)); self.pd[:, i, 2, part] = (bb * bb).sum((1, 2))
            if self.raw is not None: self.raw[i] = t.detach().cpu()
            return None
        return hook

    def close(self):
        for h in self.handles: h.remove()
        self.handles = []


def read(model, hooks, tok, convs, groups, sfx, ans_ids=None, batch=16, order=None, keep_raw=False, batches=None, pairs=None):
    """One decoder pass per batch. groups: a group name per conversation (sums are kept per group in hooks.sums).
    batches: explicit lists of row indices, one per forward pass (default: consecutive chunks of order). pairs: tuples of
    rows (a, b, c, d); every pair must sit inside one batch. Returns (proj [n, L, R, 2] or None without references,
    counts per group, raw window per row or None, pair results [len(pairs), L, 3, 2] or None)."""
    import torch
    n = len(convs); idx = list(order) if order is not None else list(range(n)); assert sorted(idx) == list(range(n))
    if batches is None: batches = [idx[s: s + batch] for s in range(0, n, batch)]
    assert sorted(r for b in batches for r in b) == list(range(n)), "the batches must hold every row once"
    R = 0 if hooks.refs is None else int(hooks.refs.shape[0])
    out = np.zeros((n, hooks.L, R, 2), np.float32) if R else None; cnt = {}; raws = {} if keep_raw else None
    pout = None if pairs is None else np.full((len(pairs), hooks.L, 3, 2), np.nan, np.float32)
    bof = {r: k for k, b in enumerate(batches) for r in b}; pin = {}
    for q, pr in enumerate(pairs or []):
        ks = {bof[r] for r in pr}; assert len(ks) == 1, f"pair {q} spans more than one batch"; pin.setdefault(ks.pop(), []).append(q)
    dec = decoder(model); dev = hooks.layers[0].self_attn.o_proj.weight.device
    hooks.active = True
    try:
        for k, ch in enumerate(batches):
            ch = list(ch)
            ids, am = encode_convs(tok, [convs[i] for i in ch], sfx, None if ans_ids is None else [ans_ids[i] for i in ch])
            assert ids.shape[1] >= hooks.W, "a row is shorter than the window"
            emb_dev = dec.embed_tokens.weight.device; ids, am = ids.to(emb_dev), am.to(emb_dev)
            pos = (am.cumsum(-1) - 1).clamp_min(0)                                 # as generation computes them for left padding
            gm = {}
            for j, i in enumerate(ch): gm.setdefault(groups[i], []).append(j)
            hooks.group = {g: torch.tensor(r, dtype=torch.long, device=dev) for g, r in gm.items()}
            for g, r in gm.items(): cnt[g] = cnt.get(g, 0) + len(r)
            if R: hooks.proj = torch.zeros(len(ch), hooks.L, R, 2, dtype=torch.float32, device=dev)
            if keep_raw: hooks.raw = [None] * hooks.L
            qs = pin.get(k, [])
            if qs:
                loc = {r: j for j, r in enumerate(ch)}
                hooks.pidx = torch.tensor([[loc[pairs[q][z]] for q in qs] for z in range(4)], dtype=torch.long, device=dev)
                hooks.pd = torch.zeros(len(qs), hooks.L, 3, 2, dtype=torch.float32, device=dev)
            else: hooks.pidx = None; hooks.pd = None
            before = hooks.passes
            with torch.no_grad(): dec(input_ids=ids, attention_mask=am, position_ids=pos, use_cache=False)
            assert hooks.passes == before + 1, "the hooks did not see this forward pass"
            if R: out[ch] = hooks.proj.cpu().numpy()
            if qs: pout[qs] = hooks.pd.cpu().numpy()
            if keep_raw:
                for j, i in enumerate(ch): raws[i] = torch.stack([hooks.raw[l][j] for l in range(hooks.L)])     # [L, W, D]
    finally:
        hooks.active = False; hooks.group = None; hooks.proj = None; hooks.raw = None; hooks.pidx = None; hooks.pd = None
    if pout is not None: assert not np.isnan(pout).any(), "a pair was not computed"
    return out, cnt, raws, pout


def fold_mean_diff(sums, counts, a, b):
    """sums/counts keyed by (type, fold): fold means of type a minus type b, [2, L, W, D] float32 on the CPU."""
    import torch
    return torch.stack([sums[(a, f)].cpu() / counts[(a, f)] - sums[(b, f)].cpu() / counts[(b, f)] for f in (0, 1)])


def ref_norms(refs, K):
    """Squared norm of each reference over the template part and the answer part of the window: [R, 2]."""
    r = np.asarray(refs, dtype=np.float64)
    return np.stack([(r[:, :, :K] ** 2).sum((1, 2, 3)), (r[:, :, K:] ** 2).sum((1, 2, 3))], 1)


def item_drive(proj_a, proj_b, ref_of_item, norms, part='window'):
    """Per item drive of the pair (a, b): proj_* [n, L, R, 2] for the same items in the same order; ref_of_item [n] the
    reference fold used for each item (the other fold); norms [R, 2]. part: 'window', 'template' or 'answer'.
    Returns (drive [n], per-layer contribution [n, L])."""
    d = proj_a - proj_b                                                             # [n, L, R, 2]
    rr = np.asarray(ref_of_item, dtype=int); n = d.shape[0]
    sel = d[np.arange(n), :, rr, :]                                                 # [n, L, 2]
    if part == 'template': num, den = sel[:, :, 0], norms[rr, 0]
    elif part == 'answer': num, den = sel[:, :, 1], norms[rr, 1]
    else: num, den = sel.sum(-1), norms[rr].sum(-1)
    per_layer = num / den[:, None]
    return per_layer.sum(1), per_layer


def cluster_boot(v, clusters, n_boot=5000, seed=0):
    """Mean of v with a percentile bootstrap that resamples clusters (host documents): (mean, lo, hi)."""
    v = np.asarray(v, dtype=float); cl = np.asarray(clusters); u, inv = np.unique(cl, return_inverse=True)
    sums = np.bincount(inv, weights=v, minlength=len(u)); cnts = np.bincount(inv, minlength=len(u)).astype(float)
    rng = np.random.default_rng(seed); k = len(u)
    pick = rng.integers(0, k, size=(n_boot, k))
    bs = sums[pick].sum(1) / cnts[pick].sum(1)
    return float(v.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def pair_cosine(pd_, part='window'):
    """Per pair cosine between its two differences from pair results [P, L, 3, 2]: summed over layers (and parts) before
    dividing. Returns (cosine [P], per-layer cosine [P, L])."""
    sel = pd_.sum(-1) if part == 'window' else pd_[..., 0 if part == 'template' else 1]       # [P, L, 3]
    tot = sel.sum(1)
    cos = tot[:, 0] / np.sqrt(np.maximum(tot[:, 1] * tot[:, 2], 1e-30))
    per = sel[:, :, 0] / np.sqrt(np.maximum(sel[:, :, 1] * sel[:, :, 2], 1e-30))
    return cos, per


def spearman_perm(x, y, n_perm=20000, seed=0, strata=None):
    """Spearman's rho (average ranks for ties) and the one-sided permutation p-value for rho at least as large. With
    strata (one label per point), y is shuffled only within each stratum, so a shift shared by a whole group (a model
    family) cannot make the association on its own."""
    from scipy.stats import rankdata
    x = rankdata(np.asarray(x, dtype=float)); y = rankdata(np.asarray(y, dtype=float))
    rho = lambda a, b: float(np.corrcoef(a, b)[0, 1])
    r0 = rho(x, y); rng = np.random.default_rng(seed)
    groups = [np.arange(len(y))] if strata is None else [np.flatnonzero(np.asarray(strata) == g) for g in sorted(set(strata))]
    def shuffled():
        z = y.copy()
        for g in groups: z[g] = y[rng.permutation(g)]
        return z
    perm = np.array([rho(x, shuffled()) for _ in range(n_perm)])
    return r0, float((1 + (perm >= r0 - 1e-12).sum()) / (n_perm + 1))
