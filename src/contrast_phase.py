"""Contrast examples (notebook 70d).

Notebook 70 taught the model to carry out requests that transform a text (translate it, edit it, copy or rewrite it,
count or list what it contains) when the USER makes them. Its BIPIA attack success rose (combined 0.105 to 0.181), and
15 of the 16 extra injections asked the model to transform its reply: answer in another language, use emoji, reverse
the text, encode it, or put it in a cipher. A request that transforms a text must be carried out when the user makes
it and ignored when it sits in the data. This module builds both sides.

  attacked  a summary request on a training passage with the request inserted in the passage; the teacher, the model
            with the adapter off, summarises the clean passage (twin distillation's target)
  twin      the same request made by the user next to the summary request, on the clean passage; the teacher sees
            that very prompt, so the model keeps doing what the user asks

Two sources of requests, both training data only:
  build_contrast_examples  the instruction wordings of the families notebook 70 trains (task_aware, literal_tasks,
                           processing_literal), filled from the training passage
  structural_contrast      units of the project's structural training split in the families that ask for a change to
                           the reply's language, format, encoding or word order, each with its own clean passage
Nothing is taken from BIPIA or SecFid; the caller checks every example against both."""
from __future__ import annotations
import re
import numpy as np
from fidelity_exact import split_sentences
from task_aware import TR_INSTR, LANGS, EDIT_INSTR, REPL, STOP
from literal_tasks import LITERAL
from processing_literal import INSTR as PROC_INSTR, GAZ

GROUPS = ("translate", "edit", "copy", "count_or_list")
OUTPUT_FAMILIES = ("answer_in_lang", "whole_reply_lang", "translate_before", "encode_reply", "replace_nouns", "respond_format", "write_as", "reverse_words")


def _request(group, rng, host):
    if group == "translate":
        return TR_INSTR[int(rng.integers(len(TR_INSTR)))].format(L=list(LANGS)[int(rng.integers(len(LANGS)))])
    if group == "edit":
        kind = ("edit_replace", "edit_delete", "edit_typo")[int(rng.integers(3))]; tmpl = EDIT_INSTR[kind][int(rng.integers(2))]
        words = sorted({w for w in re.findall(r"(?<![\w-])[a-z]{6,12}(?![\w-])", host) if w not in STOP}) or ["report"]
        w = words[int(rng.integers(len(words)))]
        if kind == "edit_replace": return tmpl.format(a=w, b=REPL[int(rng.integers(len(REPL)))])
        if kind == "edit_delete": return tmpl.format(s=" ".join(split_sentences(host)[0].split()[:6]).rstrip(",;:"))
        i = 1 + int(rng.integers(len(w) - 3)); return tmpl.format(t=w[:i] + w[i + 1] + w[i] + w[i + 2:], w=w)
    if group == "copy":
        return LITERAL[list(LITERAL)[int(rng.integers(len(LITERAL)))]].split("\n\n")[0]
    fam = list(PROC_INSTR)[int(rng.integers(len(PROC_INSTR)))]
    return PROC_INSTR[fam][int(rng.integers(len(PROC_INSTR[fam])))].replace("{T}", list(GAZ)[int(rng.integers(len(GAZ)))])


def _insert(rng, host, req):
    s = split_sentences(host); pos = ("start", "middle", "end")[int(rng.integers(3))]
    if pos == "start" or len(s) < 2: return ("start" if pos == "start" else "end"), (req + "\n" + host if pos == "start" else host.rstrip() + "\n" + req)
    if pos == "end": return pos, host.rstrip() + "\n" + req
    cut = int(rng.integers(1, len(s))); return pos, " ".join(s[:cut]) + "\n" + req + "\n" + " ".join(s[cut:])


def build_contrast_examples(hosts, task_user, task_user_with, n_attacked=250, n_twin=125, seed=0):
    """Attacked and twin examples with the trained families' own wordings, the four groups in equal shares."""
    rng = np.random.default_rng(seed); H = [h for h in hosts if len(h.split()) >= 30 and "\n\n" not in h]
    assert len(H) >= 200, len(H)
    out = []
    for k in range(n_attacked + n_twin):
        group = GROUPS[k % len(GROUPS)]; host = H[int(rng.integers(len(H)))]; req = _request(group, rng, host)
        assert "\n" not in req
        if k < n_attacked:
            pos, doc = _insert(rng, host, req)
            out.append(dict(kind="attacked", source="contrast_family", group=group, position=pos, inserted=req, student=task_user.format(doc=doc), teacher=task_user.format(doc=host)))
        else:
            t = task_user_with.format(instr=req, doc=host); out.append(dict(kind="twin", source="contrast_family", group=group, inserted=req, student=t, teacher=t))
    return out


def structural_contrast(pairs, task_user, task_user_with, n_attacked=250, n_twin=125, seed=0):
    """Attacked and twin examples from structural training items (dicts with family, instruction, embedded and host,
    the item's own clean passage) whose family asks for a change to the reply's language, format, encoding or order."""
    rng = np.random.default_rng(seed); P = [p for p in pairs if p["family"] in OUTPUT_FAMILIES]
    assert len(P) >= n_attacked, f"only {len(P)} structural training items in the output families"
    out = []
    for j in rng.permutation(len(P))[:n_attacked]:
        p = P[int(j)]
        out.append(dict(kind="attacked", source="contrast_structural", group=p["family"], inserted=p["instruction"], student=task_user.format(doc=p["embedded"]), teacher=task_user.format(doc=p["host"])))
    for j in rng.choice(len(P), n_twin, replace=False):
        p = P[int(j)]; t = task_user_with.format(instr=" ".join(p["instruction"].split()), doc=p["host"])
        out.append(dict(kind="twin", source="contrast_structural", group=p["family"], inserted=p["instruction"], student=t, teacher=t))
    return out
