"""One direction removed from chosen heads at every position after the document, and the means needed to find it.
Built on task_state and head_patching, which are unchanged.

A query head's output is its slice of the input to the attention output projection (o_proj). Two things are done to
those slices, through forward pre-hooks on o_proj, at the K template positions of the prompt pass and at every decode
step (sequence length one), never at document positions.

Recording. Running means of every head's output, kept apart for the template positions (one mean per position) and
for the decode steps (one mean over all steps of all live rows; a row stops counting once it has produced an end
token). Means over a set of runs are the sums divided by the counts; the sums are per layer, so memory is one tensor
of [L, K + 1, nh, dh] per condition however many runs are recorded.

Ablation. For each chosen head h with a unit direction d_h and an anchor a_h (the clean runs' mean projection on d_h),
the head's output x is replaced by x - ((x . d_h) - a_h) d_h: its component along d_h is set to the clean level and
every other component is left as it is. Template positions and decode steps carry their own direction and anchors,
because the heads need not represent the same thing before and during the answer; the template anchor is one value
per position, since the clean level differs from one template token to the next. kinds: 'template' patches the K
template positions only; 'all' patches the decode steps too.

Decoding is plain greedy decoding (the generation call and settings of targets.generate_batch) with the hooks in
place; nothing else about the batch changes, so the undefended answer is the same call with no heads chosen.
"""
from __future__ import annotations
from task_state import encode, decoder_layers
from head_patching import head_dims


class SteerHooks:
    def __init__(self, model, K):
        self.layers = decoder_layers(model); self.K = K; self.nh, self.dh = head_dims(model); self.L = len(self.layers)
        self.mode = None            # None | 'record' | 'ablate'
        self.live = None            # [B] bool, rows still producing answer tokens (set by the generation wrapper)
        self.sum = None; self.cnt = None
        self.spec = {}              # layer -> dict(idx [n] long, d_tpl [n, dh], a_tpl [n, K], d_ans [n, dh], a_ans [n, 1])
        self.writes = {'template': 0, 'steps': 0}
        self.handles = [l.self_attn.o_proj.register_forward_pre_hook(self._make(i)) for i, l in enumerate(self.layers)]

    def start_record(self, device):
        import torch
        self.sum = torch.zeros(self.L, self.K + 1, self.nh, self.dh, dtype=torch.float32, device=device)
        self.cnt = torch.zeros(self.L, self.K + 1, dtype=torch.float32, device=device); self.mode = 'record'

    def set_ablation(self, spec):
        """spec: {layer: dict(heads, d_tpl, a_tpl, d_ans, a_ans)}; directions [n, dh] unit rows, anchors [n, K] (template) and [n, 1] (steps)."""
        import torch
        self.spec = {}
        for l, s in spec.items():
            a_t = torch.as_tensor(s['a_tpl'], dtype=torch.float32); a_a = torch.as_tensor(s['a_ans'], dtype=torch.float32)
            if a_t.dim() == 1: a_t = a_t[:, None].expand(-1, self.K)
            if a_a.dim() == 1: a_a = a_a[:, None]
            assert a_t.shape[1] == self.K and a_a.shape[1] == 1, (a_t.shape, a_a.shape)
            self.spec[int(l)] = dict(idx=torch.as_tensor(list(s['heads']), dtype=torch.long), d_tpl=torch.as_tensor(s['d_tpl'], dtype=torch.float32), a_tpl=a_t,
                                     d_ans=torch.as_tensor(s['d_ans'], dtype=torch.float32), a_ans=a_a)
        self.mode = 'ablate'; self.writes = {'template': 0, 'steps': 0}

    def _make(self, i):
        def hook(module, args):
            import torch
            if self.mode is None: return None
            x = args[0]
            if not isinstance(x, torch.Tensor) or x.dim() != 3: return None
            B, T = x.shape[0], x.shape[1]
            if T > 1: sl, n = slice(T - self.K, T), self.K
            else: sl, n = slice(0, 1), 1
            if self.mode == 'record':
                v = x[:, sl, :].reshape(B, n, self.nh, self.dh).float()
                w = (self.live.to(x.device).float() if (T == 1 and self.live is not None) else torch.ones(B, device=x.device))
                if T > 1: self.sum[i, :self.K] += (v * w[:, None, None, None]).sum(0); self.cnt[i, :self.K] += w.sum()
                else: self.sum[i, self.K] += (v[:, 0] * w[:, None, None]).sum(0); self.cnt[i, self.K] += w.sum()
                return None
            s = self.spec.get(i)
            if s is None: return None
            if T > 1: d, a = s['d_tpl'], s['a_tpl']
            elif self.steps_too: d, a = s['d_ans'], s['a_ans']
            else: return None
            idx = s['idx'].to(x.device); d = d.to(x.device); a = a.to(x.device)
            x = x.clone(); sub = x[:, sl, :].reshape(B, n, self.nh, self.dh)
            h = sub[:, :, idx, :].float()                                       # [B, n, m, dh]
            proj = (h * d[None, None]).sum(-1)                                   # [B, n, m]
            h = h - ((proj - a.T[None]).unsqueeze(-1) * d[None, None])          # a.T: [n, m], one anchor per position and head
            sub = sub.clone(); sub[:, :, idx, :] = h.to(sub.dtype)
            x[:, sl, :] = sub.reshape(B, n, self.nh * self.dh)
            self.writes['template' if T > 1 else 'steps'] += 1
            return (x,) + tuple(args[1:])
        return hook

    steps_too = True

    def close(self):
        for h in self.handles: h.remove()
        self.handles = []


def _live_tracker(hooks, eos_ids):
    from transformers import LogitsProcessor

    class Track(LogitsProcessor):
        def __call__(self, input_ids, scores):
            import torch
            nxt = scores.argmax(-1)
            if hooks.live is None: hooks.live = torch.ones(scores.shape[0], dtype=torch.bool, device=scores.device)
            if eos_ids: hooks.live = hooks.live & ~torch.isin(nxt, torch.as_tensor(eos_ids, device=scores.device))
            return scores
    return Track()


def _eos_ids(model):
    e = getattr(model.generation_config, "eos_token_id", None)
    return [] if e is None else ([int(e)] if isinstance(e, int) else [int(x) for x in e])


def _generate(model, hooks, tok, prompts, system, sfx, max_new_tokens):
    import torch
    from transformers import LogitsProcessorList
    enc = encode(tok, prompts, system, sfx).to(model.device); T0 = enc["input_ids"].shape[1]; hooks.live = None
    with torch.no_grad():
        gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, temperature=None, top_p=None, pad_token_id=tok.pad_token_id,
                             logits_processor=LogitsProcessorList([_live_tracker(hooks, _eos_ids(model))]))
    return [tok.decode(gen[j][T0:], skip_special_tokens=True).strip() for j in range(gen.shape[0])]


def record_means(model, hooks, tok, prompts, system, sfx, max_new_tokens=160, batch=16, order=None):
    """Greedy answers to the prompts, and the running sums and counts of every head's output at the template positions
    and the decode steps over those runs. Returns (answers, sum [L, K+1, nh, dh] on the CPU, cnt [L, K+1])."""
    import torch
    hooks.start_record(model.device); outs = [None] * len(prompts)
    idx = order if order is not None else list(range(len(prompts)))
    try:
        for s in range(0, len(idx), batch):
            ch = idx[s: s + batch]; o = _generate(model, hooks, tok, [prompts[i] for i in ch], system, sfx, max_new_tokens)
            for i, a in zip(ch, o): outs[i] = a
    finally:
        hooks.mode = None; hooks.live = None
    return outs, hooks.sum.cpu(), hooks.cnt.cpu()


def generate_ablated(model, hooks, tok, prompts, system, sfx, spec, max_new_tokens=160, steps_too=True):
    """Greedy answers with the ablation spec applied at the template positions and (steps_too) every decode step."""
    hooks.set_ablation(spec); hooks.steps_too = bool(steps_too)
    try: outs = _generate(model, hooks, tok, prompts, system, sfx, max_new_tokens)
    finally: hooks.mode = None; hooks.spec = {}; hooks.live = None; hooks.steps_too = True
    assert hooks.writes['template'] > 0 or not spec, "no head was written at the template positions: the ablation did not land"
    return outs


def directions(mean_a, mean_b, mean_ortho=None, mean_clean=None, eps=1e-6):
    """Unit directions per head from a difference of means, optionally with the component along a second difference
    removed. mean_*: [L, P, nh, dh] (P = K template positions, or 1 for the decode steps; positions are pooled).
    Returns d [L, nh, dh] unit rows (zero where the difference vanishes), the anchors a [L, nh, P] (the clean mean's
    projection at each position, 0 when mean_clean is None), the cosine between the raw difference and the removed
    direction [L, nh] (nan when nothing is removed), and the share of the raw difference's norm that survives [L, nh]."""
    import torch
    raw = (mean_a - mean_b).mean(1)                                        # [L, nh, dh]
    cos = torch.full(raw.shape[:2], float('nan'))
    if mean_ortho is not None:
        u = (mean_ortho - mean_b).mean(1); un = u / u.norm(dim=-1, keepdim=True).clamp_min(eps)
        cos = (raw * un).sum(-1) / raw.norm(dim=-1).clamp_min(eps)
        d = raw - (raw * un).sum(-1, keepdim=True) * un
    else: d = raw.clone()
    kept = d.norm(dim=-1) / raw.norm(dim=-1).clamp_min(eps)
    d = d / d.norm(dim=-1, keepdim=True).clamp_min(eps)
    a = (mean_clean * d[:, None]).sum(-1).permute(0, 2, 1) if mean_clean is not None else torch.zeros(raw.shape[0], raw.shape[1], mean_a.shape[1])
    return d, a, cos, kept


def spec_for(heads, d_tpl, a_tpl, d_ans, a_ans):
    """An ablation spec for (layer, head) pairs from per-head direction tensors [L, nh, dh] and anchor tensors [L, nh, P]."""
    by = {}
    for l, h in heads: by.setdefault(int(l), []).append(int(h))
    return {l: dict(heads=hs, d_tpl=d_tpl[l, hs], a_tpl=a_tpl[l, hs], d_ans=d_ans[l, hs], a_ans=a_ans[l, hs]) for l, hs in by.items()}
