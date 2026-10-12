"""Per-head patching at the template positions, for the carrier-heads notebooks. Built on task_state, which is unchanged.

A query head's output is the slice of the input to its layer's attention output projection (o_proj) that belongs to that
head. These hooks sit on o_proj as forward pre-hooks, so they see that input before the projection mixes the heads, and
can record or replace any subset of head slices at the K template positions of a prompt pass. Document positions are
never touched and decode steps (sequence length one) pass through.

spec: {layer: dict(kind, heads, src)}
  kind 'set'    the listed heads' slices <- src
  kind 'zero'   the listed heads' slices <- 0
  src  [B, K, nh*dh] (per row), [K, nh*dh] (shared over rows) or [nh*dh] (shared over rows and positions); only the
       listed heads' slices are read from it, so a full recorded tensor can be passed and the heads chosen per call.

offset: 0, or the number of tokens appended after the template (16 when answer tokens are appended for the margin).

Recordings are kept in rec_dtype: float16 on a float16 model, float32 otherwise, so writing a recording back is an exact
copy on bfloat16 models too.
"""
from __future__ import annotations
import numpy as np
from task_state import encode, _generate, decoder_layers


def rec_dtype(dtype):
    """The precision a recording is kept in: float16 for a float16 model (as in notebooks 56 to 57g, so those runs are
    unchanged), float32 for anything else. A bfloat16 value smaller than about 8e-6 in size loses bits in float16 (and
    one above 65504 does not fit), so writing a float16 recording back into a bfloat16 model (Llama) is not an exact
    copy; float32 holds every bfloat16 value exactly."""
    import torch
    return torch.float16 if dtype == torch.float16 else torch.float32


def head_dims(model):
    """(number of query heads, head dimension) read from o_proj, so grouped-query attention is handled."""
    m = model.get_base_model() if hasattr(model, "get_base_model") else model
    nh = int(m.config.num_attention_heads); din = int(decoder_layers(model)[0].self_attn.o_proj.in_features)
    assert din % nh == 0, (din, nh)
    return nh, din // nh


class HeadHooks:
    def __init__(self, model, K):
        self.layers = decoder_layers(model); self.K = K; self.offset = 0
        self.nh, self.dh = head_dims(model)
        self.record = False; self.rec = {}; self.spec = {}; self.prompt_passes = 0
        self.handles = [l.self_attn.o_proj.register_forward_pre_hook(self._make(i)) for i, l in enumerate(self.layers)]

    def n_heads(self):
        return len(self.layers) * self.nh

    def _slice(self):
        return slice(-self.K - self.offset, None if self.offset == 0 else -self.offset)

    def _make(self, i):
        def hook(module, args):
            import torch
            x = args[0]
            if not isinstance(x, torch.Tensor) or x.dim() != 3 or x.shape[1] <= 1: return None
            if i == 0: self.prompt_passes += 1
            sl = self._slice()
            if self.record: self.rec[i] = x[:, sl, :].detach().to(rec_dtype(x.dtype)).cpu().clone()
            s = self.spec.get(i)
            if s is None: return None
            B = x.shape[0]; x = x.clone()
            cur = x[:, sl, :].reshape(B, self.K, self.nh, self.dh); new = cur.clone()
            idx = torch.as_tensor(list(s["heads"]), device=x.device, dtype=torch.long)
            if s["kind"] == "zero":
                new[:, :, idx, :] = 0
            elif s["kind"] == "set":
                v = s["src"].to(x.device, x.dtype)
                if v.dim() == 1: v = v.view(1, 1, self.nh, self.dh).expand(B, self.K, -1, -1)
                elif v.dim() == 2: v = v.reshape(1, self.K, self.nh, self.dh).expand(B, -1, -1, -1)
                elif v.dim() == 3: v = v.reshape(v.shape[0], self.K, self.nh, self.dh)
                else: raise ValueError(f"src has {v.dim()} dimensions")
                new[:, :, idx, :] = v[:, :, idx, :]
            else: raise ValueError(s["kind"])
            x[:, sl, :] = new.reshape(B, self.K, self.nh * self.dh)
            return (x,) + tuple(args[1:])
        return hook

    def close(self):
        for h in self.handles: h.remove()
        self.handles = []


def head_spec(layer, heads, src=None, kind="set"):
    """One spec entry. src is a stacked recording [B, L, K, nh*dh]; its layer slice is taken here."""
    e = dict(kind=kind, heads=list(heads))
    if kind != "zero":
        assert src is not None, "kind 'set' needs a source"
        e["src"] = src[:, int(layer)] if src.dim() == 4 else src
    return {int(layer): e}


def merge_specs(*specs):
    """Specs on disjoint layers merged; two entries for one layer are joined when their kind and source match."""
    out = {}
    for s in specs:
        for l, e in s.items():
            if l not in out: out[l] = dict(e)
            else:
                assert out[l]["kind"] == e["kind"], f"two kinds on layer {l}"
                out[l]["heads"] = sorted(set(out[l]["heads"]) | set(e["heads"]))
    return out


def set_spec(heads, src=None, kind="set"):
    """A spec for a set of (layer, head) pairs."""
    by = {}
    for l, h in heads: by.setdefault(int(l), []).append(int(h))
    return merge_specs(*[head_spec(l, hs, src, kind) for l, hs in by.items()])


def capture_heads(model, hooks, tok, prompts, system, sfx):
    """Head outputs at the template positions for one batch: [B, L, K, nh*dh] in rec_dtype (float16 on a float16 model, float32 otherwise), from the answering call's prompt pass."""
    import torch
    enc = encode(tok, prompts, system, sfx).to(model.device)
    hooks.rec = {}; hooks.spec = {}; hooks.offset = 0; hooks.record = True
    try: _generate(model, tok, enc, 1)
    finally: hooks.record = False
    st = torch.stack([hooks.rec[i] for i in range(len(hooks.layers))], 1); hooks.rec = {}
    return st


def answer_logprob(model, hooks, tok, prompts, system, sfx, ans_ids, spec=None, record=False):
    """Mean log-probability of each row's answer tokens, with the head spec applied at the template positions.

    ans_ids: one list of token ids per row, all the same length. The answer tokens are appended to the prompt, so the
    template positions sit len(ans) places before the end and the hooks take that offset. record=True also returns the
    head outputs at the template positions of this very pass, before any spec is applied ([B, L, K, nh*dh] in
    rec_dtype), so a write-back can be checked against a recording of the same shape of pass."""
    import torch
    enc = encode(tok, prompts, system, sfx).to(model.device)
    A = torch.as_tensor(ans_ids, device=enc["input_ids"].device, dtype=enc["input_ids"].dtype)
    assert A.dim() == 2 and A.shape[0] == enc["input_ids"].shape[0], (A.shape, enc["input_ids"].shape)
    ids = torch.cat([enc["input_ids"], A], 1); am = torch.cat([enc["attention_mask"], torch.ones_like(A)], 1)
    nt = int(A.shape[1])
    hooks.rec = {}; hooks.spec = dict(spec or {}); hooks.record = bool(record); hooks.offset = nt
    try:
        with torch.no_grad(): lg = model(input_ids=ids, attention_mask=am).logits
    finally: hooks.spec = {}; hooks.offset = 0; hooks.record = False
    lp = torch.log_softmax(lg[:, -nt - 1:-1, :].float(), -1)
    out = lp.gather(-1, A[:, :, None].long()).squeeze(-1).mean(1).detach().cpu().numpy()
    if not record: return out
    st = torch.stack([hooks.rec[i] for i in range(len(hooks.layers))], 1); hooks.rec = {}
    return out, st


def doc_attention(model, tok, prompts, system, sfx, doc_tokens, batch=4):
    """Attention mass from the last prompt position to the document span, per head: [L, nh] averaged over rows.

    Attention Tracker ranks heads by the mass the last token sends to the injected instruction. That span is not
    recorded for rewritten documents, so the span used here is the whole document, which is the closest recoverable
    form of the rule. doc_tokens: the document's own token count per row."""
    import torch
    L = len(decoder_layers(model)); nh, _ = head_dims(model); tot = np.zeros((L, nh)); rows = 0
    for s0 in range(0, len(prompts), batch):
        ps = prompts[s0:s0 + batch]; nd = doc_tokens[s0:s0 + batch]
        enc = encode(tok, ps, system, sfx).to(model.device)
        with torch.no_grad(): att = model(**enc, output_attentions=True).attentions
        T = enc["input_ids"].shape[1]; K = len(sfx)
        for b in range(len(ps)):
            lo = max(0, T - K - int(nd[b])); hi = T - K
            if hi <= lo: continue
            for l in range(L): tot[l] += att[l][b, :, -1, lo:hi].float().sum(-1).cpu().numpy()
            rows += 1
        del att
    assert rows, "no row had a document span"
    return tot / rows
