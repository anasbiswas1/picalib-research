"""State patching at the template positions, for notebook 53 (exploration). Built on task_state, which stays exactly as
notebook 51 used it.

The task state of a prompt is its residual stream at the K template tokens that follow the user's content (task_state).
A write changes that state during the prompt pass of the answering call; decode steps are untouched.

spec: {layer: dict(kind, src, alpha, pos)}
  kind 'mix'   state <- (1 - alpha) * state + alpha * src        (alpha 1 is a plain replacement by src)
  kind 'add'   state <- state + alpha * src
  src  tensor [B, K, H] for that layer; pos: None (all K positions) or a list of K booleans (only those positions)

When a first answer token is appended to the prompt (force_first), the template positions sit one place before the end,
so the hooks take an offset of 1. Sampling (the robustness screen) uses the model's generate with do_sample, a fixed seed
set before each call, temperature and top_p as given."""
from __future__ import annotations
import hashlib
import numpy as np
from task_state import chat, encode, _generate, decoder_layers, equal_norm_noise

FILLER = "This is a plain passage of ordinary text that says nothing in particular and carries no request of any kind. "


class PatchHooks:
    """Forward hooks on every decoder layer. On a prompt pass (sequence length above one) a hook can record the state at
    the K template positions and change it as spec says. offset: 0, or 1 when a token was appended after the template."""

    def __init__(self, model, K):
        self.layers = decoder_layers(model); self.K = K; self.offset = 0; self.record = False; self.rec = {}; self.spec = {}; self.prompt_passes = 0
        self.handles = [layer.register_forward_hook(self._make(i)) for i, layer in enumerate(self.layers)]

    def _slice(self):
        return slice(-self.K - self.offset, None if self.offset == 0 else -self.offset)

    def _make(self, i):
        def hook(module, args, out):
            h = out[0] if isinstance(out, tuple) else out
            if h.dim() != 3 or h.shape[1] <= 1: return None
            if i == 0: self.prompt_passes += 1
            sl = self._slice()
            if self.record: self.rec[i] = h[:, sl, :].detach().half().cpu().clone()
            s = self.spec.get(i)
            if s is None: return None
            src = s["src"].to(h.device, h.dtype); alpha = float(s.get("alpha", 1.0)); pos = s.get("pos")
            h = h.clone(); cur = h[:, sl, :]
            new = cur + alpha * src if s["kind"] == "add" else (1.0 - alpha) * cur + alpha * src
            if pos is not None:
                import torch
                m = torch.tensor(pos, device=h.device, dtype=torch.bool); new = torch.where(m[None, :, None], new, cur)
            h[:, sl, :] = new
            return (h,) + tuple(out[1:]) if isinstance(out, tuple) else h
        return hook

    def close(self):
        for h in self.handles: h.remove()
        self.handles = []


def layer_spec(layers, kind, src, alpha=1.0, pos=None):
    """One spec entry per layer in `layers`, from a stacked source [B, L, K, H]."""
    return {int(l): dict(kind=kind, src=src[:, int(l)], alpha=alpha, pos=pos) for l in layers}


def generate_patched(model, hooks, tok, prompts, system, sfx, spec=None, force_first=None, max_new_tokens=160, sample=None):
    """Greedy answers (or sampled ones: sample = dict(temperature, top_p, seed)) with the task state changed as spec says.
    force_first: one token id per row appended to the prompt and kept as the answer's first token; the write then lands
    on the template positions, one place before the end. Returns (answers, first generated token ids)."""
    import torch
    enc = encode(tok, prompts, system, sfx).to(model.device); T0 = enc["input_ids"].shape[1]; hooks.offset = 0
    if force_first is not None:
        f = torch.tensor(force_first, device=enc["input_ids"].device)[:, None]
        enc = dict(input_ids=torch.cat([enc["input_ids"], f], 1), attention_mask=torch.cat([enc["attention_mask"], torch.ones_like(f)], 1)); hooks.offset = 1
    hooks.rec = {}; hooks.spec = dict(spec or {}); hooks.record = False
    try:
        if sample is None: gen = _generate(model, tok, enc, max_new_tokens)
        else:
            torch.manual_seed(int(sample["seed"]))
            with torch.no_grad():
                gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=True, temperature=float(sample["temperature"]), top_p=float(sample.get("top_p", 0.9)), pad_token_id=tok.pad_token_id)
    finally: hooks.spec = {}; hooks.offset = 0
    outs = [tok.decode(gen[j][T0:], skip_special_tokens=True).strip() for j in range(gen.shape[0])]
    return outs, [int(gen[j][T0]) for j in range(gen.shape[0])]


def capture_states(model, hooks, tok, prompts, system, sfx):
    """Task state of one batch, float16 [B, L, K, H], from the prompt pass of the answering call (no change made)."""
    import torch
    enc = encode(tok, prompts, system, sfx).to(model.device)
    hooks.rec = {}; hooks.spec = {}; hooks.offset = 0; hooks.record = True
    try: _generate(model, tok, enc, 1)
    finally: hooks.record = False
    st = torch.stack([hooks.rec[i] for i in range(len(hooks.layers))], 1); hooks.rec = {}
    return st


def seed53(key):
    """Fresh seeds for this notebook, independent of notebook 51's seed_of(key)."""
    return int(hashlib.sha1(("nb53\x00" + key).encode()).hexdigest()[:15], 16)


def fresh_noise(ref, keys):
    """Gaussian directions with the norm of ref at every layer and position, seeded per item with seed53."""
    return equal_norm_noise(ref, [seed53(k) for k in keys])


def neutral_filler(tok, document):
    """Ordinary text with the same number of tokens as the document (both tokenized on their own)."""
    n = len(tok(document, add_special_tokens=False)["input_ids"]); ids = tok(FILLER, add_special_tokens=False)["input_ids"]
    reps = (n + len(ids) - 1) // len(ids); return tok.decode((ids * reps)[:n]).strip()


def screen_label(greedy_ok, sample_oks, need=4):
    """robust success: greedy succeeds and at least `need` of the samples; robust failure: greedy and every sample fail;
    otherwise fragile (fragile success when the greedy answer succeeds, fragile failure when it does not)."""
    k = int(sum(bool(x) for x in sample_oks)); n = len(sample_oks)
    if greedy_ok: return "robust success" if k >= need else "fragile success"
    return "robust failure" if k == 0 else "fragile failure"
