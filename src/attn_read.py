"""Where the heads look: attention mass from the positions after the document to named spans of the prompt.

One forward pass per item over the chat-formatted prompt followed by the model's own answer (teacher forcing), with
eager attention so the weights are returned. For every layer and head, the attention mass sent from three groups of
query positions (the K template positions; the first 16 answer tokens; every answer token) to each named span of the
prompt (character spans of the prompt text, mapped to tokens by the tokenizer's offsets). Returns [3, L, nh, S].
"""
from __future__ import annotations
import numpy as np
from task_state import chat, decoder_layers
from head_patching import head_dims

GROUPS = ("template", "first_16", "answer")


def token_spans(tok, text, char_spans):
    """Token index ranges [lo, hi) covering each character span of text, from the tokenizer's offsets."""
    enc = tok(text, return_offsets_mapping=True, add_special_tokens=False)
    offs = enc["offset_mapping"]; out = []
    for cs, ce in char_spans:
        idx = [i for i, (a, b) in enumerate(offs) if b > cs and a < ce and b > a]
        out.append((min(idx), max(idx) + 1) if idx else (0, 0))
    return enc["input_ids"], out


def span_masses(model, tok, prompt, answer, system, sfx, spans, first=16):
    """spans: {name: (char_start, char_end) within the prompt text}. Returns (masses [3, L, nh, S], token counts per span, n_answer_tokens)."""
    import torch
    pre = chat(tok, system, prompt); base = pre.index(prompt)                 # the prompt sits once, verbatim, inside the chat text
    assert pre.count(prompt) == 1, "the prompt is not verbatim in the chat text"
    ids, tspans = token_spans(tok, pre, [(base + a, base + b) for a, b in spans.values()])     # the prompt alone, so the spans map cleanly
    ans_ids = tok(answer or "", add_special_tokens=False)["input_ids"]                           # the answer tokenised on its own, as the model produced it
    n_pre = len(ids); K = len(sfx); ids = list(ids) + list(ans_ids); T = len(ids)
    assert ids[:n_pre][-K:] == list(sfx), "the template suffix is not where the answer starts"
    n_ans = T - n_pre
    q_groups = [list(range(n_pre - K, n_pre)), list(range(n_pre, min(T, n_pre + first))), list(range(n_pre, T))]
    L = len(decoder_layers(model)); nh, _ = head_dims(model); out = np.zeros((3, L, nh, len(spans)), np.float32)
    enc = dict(input_ids=torch.tensor([ids], device=model.device), attention_mask=torch.ones(1, T, dtype=torch.long, device=model.device))
    with torch.no_grad(): att = model(**enc, output_attentions=True).attentions
    assert att is not None and att[0] is not None, "no attention weights were returned: the eager attention path is not active"
    for l in range(L):
        a = att[l][0].float()                                                  # [nh, T, T]
        for g, qs in enumerate(q_groups):
            if not qs: out[g, l] = np.nan; continue
            rows = a[:, qs, :]                                                # [nh, q, T]
            for s, (lo, hi) in enumerate(tspans):
                out[g, l, :, s] = rows[:, :, lo:hi].sum(-1).mean(-1).cpu().numpy() if hi > lo else np.nan
    del att
    return out, [hi - lo for lo, hi in tspans], n_ans
