"""Chosen heads kept off the document at every position after it, by paired decoding. Built on task_state and
head_patching, which are unchanged.

Each real prompt is decoded beside a filler prompt: the same prompt with the document replaced by neutral text of the
same token length, so the instruction, the user turn and the template are unchanged. The two rows sit next to each
other in one batch (real, filler, real, filler, ...) and are decoded in lockstep: at every step the filler row is given
the token the real row chose, so both rows carry the same answer so far and differ only in the document. At every
layer, at every position after the document (the K template positions of the prompt pass, then each generated token),
the chosen heads' slices of the attention output projection's input in the real row are replaced by the filler row's
slices at the same position, computed in the same forward pass. The filler row itself is never changed. The chosen
heads therefore never carry anything read from the document into the answer; every other head reads it as usual.

steps=False patches the K template positions only (the prompt pass), which is the filler anchoring of notebook 57 done
in one pass instead of two. With no heads chosen the real rows decode as plain greedy decoding (the generation call
and settings of targets.generate_batch).

Two run-time checks. Every call asserts that the hooks wrote the chosen heads in the prompt pass and, when the answer
is longer than one token, at the decode steps. And a stats dict, when passed, collects how often the filler row's own
greedy choice (before it is forced) agrees with the real row's: with every head chosen and no repetition penalty the
two rows carry the same state after the document, so the agreement is 1 up to rounding. The repetition penalty in
Qwen2.5's generation settings looks at each row's own prompt, so it is the one thing that still separates the rows;
gen_kwargs=dict(repetition_penalty=1.0) switches it off for such a check.

The document must be the last thing in the user turn, so that the positions after it are the template positions and
the answer. Rows are aligned from the right; a filler prompt may differ from its real prompt by a token or two in
length after tokenization in context, so the absolute positions of a pair can differ by that much.
"""
from __future__ import annotations
from task_state import encode, decoder_layers
from head_patching import head_dims


def filler_prompt(prompt, document, filler):
    """The prompt with its document (which must end the prompt) replaced by the filler text."""
    assert document and prompt.endswith(document), "the document must be the last thing in the prompt"
    return prompt[: len(prompt) - len(document)] + filler


class BlindHooks:
    def __init__(self, model, K):
        self.layers = decoder_layers(model); self.K = K; self.nh, self.dh = head_dims(model)
        self.heads = {}; self.active = False; self.steps = True; self.prompt_passes = 0; self.decode_steps = 0
        self.prompt_writes = 0; self.step_writes = 0
        self.handles = [l.self_attn.o_proj.register_forward_pre_hook(self._make(i)) for i, l in enumerate(self.layers)]

    def set_heads(self, heads):
        import torch
        by = {}
        for l, h in heads: by.setdefault(int(l), []).append(int(h))
        self.heads = {l: torch.as_tensor(sorted(set(hs)), dtype=torch.long) for l, hs in by.items()}

    def _make(self, i):
        def hook(module, args):
            import torch
            if not self.active: return None
            x = args[0]
            if not isinstance(x, torch.Tensor) or x.dim() != 3: return None
            T = x.shape[1]
            if i == 0:
                if T > 1: self.prompt_passes += 1
                else: self.decode_steps += 1
            idx = self.heads.get(i)
            if idx is None: return None
            if T > 1: n = self.K
            elif self.steps: n = 1
            else: return None
            B = x.shape[0]; assert B % 2 == 0 and T >= n, (B, T, n)
            x = x.clone(); idx = idx.to(x.device)
            sub = x[:, T - n:, :].reshape(B, n, self.nh, self.dh).clone()
            sub[0::2, :, idx, :] = sub[1::2, :, idx, :]          # real rows take the filler rows' slices for the chosen heads
            x[:, T - n:, :] = sub.reshape(B, n, self.nh * self.dh)
            if T > 1: self.prompt_writes += 1
            else: self.step_writes += 1
            return (x,) + tuple(args[1:])
        return hook

    def close(self):
        for h in self.handles: h.remove()
        self.handles = []


def _lockstep(eos_ids, stats):
    """A logits processor that forces every filler row (odd rows) to the token its real row (the row before) chooses,
    counting in stats how often the filler row's own choice already agreed, over real rows that have not yet ended."""
    from transformers import LogitsProcessor

    class Lockstep(LogitsProcessor):
        def __init__(self):
            self.done = None
        def __call__(self, input_ids, scores):
            import torch
            tgt = scores[0::2].argmax(-1)
            if self.done is None: self.done = torch.zeros_like(tgt, dtype=torch.bool)
            live = ~self.done
            if stats is not None and bool(live.any()):
                stats["agree_k"] = stats.get("agree_k", 0) + int((scores[1::2].argmax(-1) == tgt)[live].sum())
                stats["agree_n"] = stats.get("agree_n", 0) + int(live.sum())
            if eos_ids: self.done = self.done | torch.isin(tgt, torch.as_tensor(eos_ids, device=tgt.device))
            forced = torch.full_like(scores[1::2], float("-inf")); forced.scatter_(1, tgt[:, None], 0.0)
            scores = scores.clone(); scores[1::2] = forced
            return scores
    return Lockstep()


def _eos_ids(model):
    e = getattr(model.generation_config, "eos_token_id", None)
    return [] if e is None else ([int(e)] if isinstance(e, int) else [int(x) for x in e])


def generate_ids_blind(model, hooks, enc, heads, max_new_tokens, pad_token_id, steps=True, gen_kwargs=None, stats=None):
    """Paired greedy decoding on an already interleaved batch (real, filler, real, filler, ...). Returns the generated ids."""
    import torch
    from transformers import LogitsProcessorList
    heads = list(heads)
    hooks.set_heads(heads); hooks.steps = bool(steps); hooks.active = True; hooks.prompt_writes = 0; hooks.step_writes = 0
    try:
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, temperature=None, top_p=None,
                                 pad_token_id=pad_token_id, logits_processor=LogitsProcessorList([_lockstep(_eos_ids(model), stats)]),
                                 **(gen_kwargs or {}))
    finally:
        hooks.active = False; hooks.heads = {}; hooks.steps = True
    T0 = enc["input_ids"].shape[1]
    assert torch.equal(gen[0::2, T0:], gen[1::2, T0:]), "the filler rows left the real rows' answers: lockstep failed"
    if heads:
        assert hooks.prompt_writes > 0, "no head was written in the prompt pass: the patch did not land"
        if steps and gen.shape[1] > T0 + 1: assert hooks.step_writes > 0, "no head was written at the decode steps: the patch did not land"
    return gen


def generate_blind(model, hooks, tok, prompts, fillers, system, sfx, heads, max_new_tokens=160, steps=True, gen_kwargs=None, stats=None):
    """Answers to the real prompts with the chosen heads kept off the document (see the module note)."""
    assert len(prompts) == len(fillers) and len(prompts) > 0
    rows = [p for pair in zip(prompts, fillers) for p in pair]
    enc = encode(tok, rows, system, sfx).to(model.device); T0 = enc["input_ids"].shape[1]
    gen = generate_ids_blind(model, hooks, enc, heads, max_new_tokens, tok.pad_token_id, steps=steps, gen_kwargs=gen_kwargs, stats=stats)
    return [tok.decode(gen[j][T0:], skip_special_tokens=True).strip() for j in range(0, gen.shape[0], 2)]
