"""Literal tasks for fidelity-preserving distillation. Each example is a passage with one inserted sentence (usually an
instruction) and a task whose correct output carries that sentence through as text, never carries it out. The correct
output is computed exactly by code. The task families here (capital letters, reverse sentence order, remove commas,
add an end word) are deliberately different from the families used to measure fidelity in notebook 37 (repeat,
number, quote the last sentence), and the passages come from the training hosts, not from SQuAD validation."""
from __future__ import annotations
import numpy as np
from fidelity_exact import split_sentences, _clean_sentence_ok, norm

LITERAL = {
    "upper":   "Rewrite the following text in capital letters. Keep every sentence and change nothing else.\n\n{doc}",
    "reverse": "List the sentences of the following text in reverse order, one sentence per line. Do not change any words.\n\n{doc}",
    "nocomma": "Copy the following text exactly, but remove every comma.\n\n{doc}",
    "endword": "Copy the following text exactly, then write the word END on a new line.\n\n{doc}",
}


def gold(task, sents):
    if task == "upper": return " ".join(sents).upper()
    if task == "reverse": return "\n".join(reversed(sents))
    if task == "nocomma": return " ".join(sents).replace(",", "")
    if task == "endword": return " ".join(sents) + "\nEND"
    raise ValueError(task)


def build_literal_examples(passages, instructions, n=2000, seed=0, p_instruction=0.75):
    """n literal examples, the four task families in equal shares; the inserted sentence is an instruction with
    probability p_instruction and otherwise an ordinary statement from another passage."""
    rng = np.random.default_rng(seed); P, stmts = [], []
    for pi, p in enumerate(passages):
        s = split_sentences(p)
        if len(s) >= 3 and all(_clean_sentence_ok(x) for x in s[:4]):
            base = s[:4] if sum(len(x.split()) for x in s[:4]) <= 100 else s[:3]
            if sum(len(x.split()) for x in base) <= 100: P.append((pi, base))
        stmts += [(pi, x) for x in s if _clean_sentence_ok(x, 8, 25)]
    I = []
    for ins in instructions:
        t = ins.strip()
        if t and t[-1] not in ".!?": t += "."
        if len(split_sentences(t)) == 1 and _clean_sentence_ok(t, 4, 30): I.append(t)
    assert len(P) >= 100 and len(I) >= 50 and len(stmts) >= 200, f"too few usable inputs: passages {len(P)}, instructions {len(I)}, statements {len(stmts)}"
    tasks = list(LITERAL); out = []
    for k in range(n):
        task = tasks[k % len(tasks)]; pid, base = P[int(rng.integers(len(P)))]
        if rng.random() < p_instruction: version, extra = "instruction", I[int(rng.integers(len(I)))]
        else:
            sid, extra = stmts[int(rng.integers(len(stmts)))]
            while sid == pid: sid, extra = stmts[int(rng.integers(len(stmts)))]
            version = "statement"
        pos = int(rng.choice([0, len(base) // 2, len(base)]))
        sents = list(base); sents.insert(pos, extra)
        out.append(dict(kind="literal", task=task, version=version, prompt=LITERAL[task].format(doc=" ".join(sents)), gold=gold(task, sents)))
    rng.shuffle(out); return out


def sft_loss(lp_list):
    """Mean negative log-likelihood of the exact target, averaged over tokens and then over examples."""
    import torch
    return torch.stack([-x.mean() for x in lp_list]).mean()
