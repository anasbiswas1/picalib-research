"""Twin distillation: on-policy, token-level self-distillation that makes the model's output independent of an
injected span. For every training example the injected input is built from a clean one, so the clean input is
known. The student (the model with a LoRA adapter) samples a response to the injected input; the teacher (the same
model with the adapter disabled) scores every token of that response given the CLEAN input. The student is pushed,
token by token, toward what it would have said without the injection. A twin example places the same injected
instruction in the user turn with the clean input; there the teacher sees that very prompt, which anchors the student
to keep following instructions the user issues. The signal never asks the model to recognise an injection, only to
make its output invariant to the untrusted span."""
from __future__ import annotations
import numpy as np

PROMPT = "{instruction}\n\nInput:\n{inp}"
PROMPT_WITH = "{instruction} {extra}\n\nInput:\n{inp}"


def build_examples(samples, n=1500, seed=0, positions=(0.45, 0.45, 0.10)):
    """samples: list of dicts with 'instruction' and non-empty 'input'. Returns attacked and twin examples.
    Each attacked example carries the student prompt (injected input) and the teacher prompt (clean input)."""
    rng = np.random.default_rng(seed); S = [s for s in samples if s.get("input", "").strip() and s.get("instruction", "").strip()]
    idx = rng.choice(len(S), min(n, len(S)), replace=False); out = []
    for i in idx:
        s = S[i]; j = int(rng.integers(len(S)))
        while j == i: j = int(rng.integers(len(S)))
        inj = S[j]["instruction"].strip(); inp = s["input"].strip(); r = rng.random()
        if r < positions[0]: injected = inp + "\n\n" + inj                       # end
        elif r < positions[0] + positions[1]: injected = inj + "\n\n" + inp        # start
        else: injected = inp + "\n\nAnswer: task complete.\n\n" + inj              # fake-completion style
        out.append(dict(kind="attacked", student=PROMPT.format(instruction=s["instruction"].strip(), inp=injected), teacher=PROMPT.format(instruction=s["instruction"].strip(), inp=inp)))
        twin = PROMPT_WITH.format(instruction=s["instruction"].strip(), extra=inj, inp=inp)
        out.append(dict(kind="twin", student=twin, teacher=twin))
    rng.shuffle(out); return out


def _split_sentences(text):
    import re
    parts = re.split(r"(?<=[.!?])\s+", text.strip()); return [p for p in parts if p]


def build_doc_examples(hosts, instructions, task_user, task_user_with, n=1500, seed=0, positions=(0.45, 0.45, 0.10)):
    """Document-style examples: a passage (SQuAD or AG News host) with a random instruction injected at the end, the
    start, or between two sentences; the task is the paper's summarization task. Same student/teacher/twin layout."""
    rng = np.random.default_rng(seed); H = [h for h in hosts if len(h.split()) >= 30]; I = [i.strip() for i in instructions if i.strip()]
    out = []
    for k in range(min(n, len(H))):
        h = H[int(rng.integers(len(H)))]; inj = I[int(rng.integers(len(I)))]; r = rng.random()
        if r < positions[0]: injected = h.rstrip() + "\n" + inj
        elif r < positions[0] + positions[1]: injected = inj + "\n" + h
        else:
            s = _split_sentences(h); cut = int(rng.integers(1, len(s))) if len(s) > 1 else 1
            injected = " ".join(s[:cut]) + "\n" + inj + "\n" + " ".join(s[cut:]) if len(s) > 1 else h.rstrip() + "\n" + inj
        out.append(dict(kind="attacked", student=task_user.format(doc=injected), teacher=task_user.format(doc=h)))
        twin = task_user_with.format(instr=inj, doc=h); out.append(dict(kind="twin", student=twin, teacher=twin))
    rng.shuffle(out); return out


def _chat(tok, system, user, add_gen=True):
    return tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": user}], tokenize=False, add_generation_prompt=add_gen)


def sample_rollouts(model, tok, prompts, system, max_new_tokens=128, temperature=1.0):
    """Sample one response per prompt from the current student (batched, left padding)."""
    import torch
    was_training = model.training; model.eval(); tok.padding_side = "left"
    enc = tok([_chat(tok, system, p) for p in prompts], return_tensors="pt", padding=True, truncation=True, max_length=1024).to(model.device)
    with torch.no_grad():
        gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=True, temperature=temperature, top_p=1.0, pad_token_id=tok.pad_token_id, use_cache=True)
    outs = [tok.decode(gen[j][enc["input_ids"].shape[1]:], skip_special_tokens=True).strip() for j in range(len(prompts))]
    if was_training: model.train()
    return outs


def response_logprobs(model, tok, prompts, responses, system, max_len=1024):
    """Per-token log-probabilities of each response given its prompt (batched, right padding). Returns list of 1-D tensors."""
    import torch
    tok.padding_side = "right"; seqs, starts, lens = [], [], []
    for p, r in zip(prompts, responses):
        p_ids = tok(_chat(tok, system, p), add_special_tokens=False).input_ids; r_ids = tok(r + tok.eos_token, add_special_tokens=False).input_ids
        if len(p_ids) + len(r_ids) > max_len: p_ids = p_ids[: max(64, max_len - len(r_ids))]; r_ids = r_ids[: max_len - len(p_ids)]
        seqs.append(p_ids + r_ids); starts.append(len(p_ids)); lens.append(len(r_ids))
    T = max(len(s) for s in seqs); pad = tok.pad_token_id
    ids = torch.tensor([s + [pad] * (T - len(s)) for s in seqs], device=model.device); am = torch.tensor([[1] * len(s) + [0] * (T - len(s)) for s in seqs], device=model.device)
    logits = model(input_ids=ids, attention_mask=am).logits
    out = []
    for b, (st, ln) in enumerate(zip(starts, lens)):
        lg = logits[b, st - 1: st - 1 + ln].float(); tg = ids[b, st: st + ln]
        out.append(torch.log_softmax(lg, -1).gather(1, tg[:, None])[:, 0])
    return out


def distill_loss(lp_student, lp_teacher):
    """On-policy reverse-KL policy gradient: per-token advantage = log p_teacher - log p_student (detached)."""
    import torch
    losses, kls = [], []
    for s, t in zip(lp_student, lp_teacher):
        adv = (t - s).detach(); losses.append(-(adv * s).mean()); kls.append((s - t).detach().mean())
    return torch.stack(losses).mean(), float(torch.stack(kls).mean())
