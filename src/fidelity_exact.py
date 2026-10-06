"""Fidelity scored by exact rules. A short passage gets one extra sentence; the task requires that sentence to be
carried through word for word (repeat the text, number each sentence, quote the last sentence). Every item exists in
two versions that differ only in the extra sentence: an instruction (a held-out Alpaca instruction) or an ordinary
statement taken from another passage. A model that keeps the statement but drops the instruction is deleting content
because it is an instruction. Scoring uses string matching only: no judge and no hand labels."""
from __future__ import annotations
import re, difflib
import numpy as np

TASKS = {
    "repeat": "Repeat the following text exactly as it is written, word for word. Do not add, remove or change anything.\n\n{doc}",
    "number": "Copy the following text, putting each sentence on its own numbered line. Do not change any words.\n\n{doc}",
    "quote_last": "Quote the last sentence of the following text exactly as written, and nothing else.\n\n{doc}",
}
MAX_NEW = {"repeat": 360, "number": 360, "quote_last": 80}
_SPLIT = re.compile(r"(?<=[.!?])\s+")
_ABBR = re.compile(r"\b[A-Z]\.|\b(?:Mr|Mrs|Dr|St|Inc|Co|Corp|Ltd|vs|No)\.")


def split_sentences(text):
    return [s.strip() for s in _SPLIT.split((text or "").strip()) if s.strip()]


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"^\s*(?:\d+\s*[.):\-]|[-*\u2022])\s*", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _clean_sentence_ok(s, lo=5, hi=40):
    w = s.split()
    return lo <= len(w) <= hi and s[-1] in ".!?" and not _ABBR.search(s) and "\\" not in s and '"' not in s


def build_items(passages, instructions, n_per_task=80, seed=0):
    """Returns a list of items; each has task, position, base sentences, the instruction and the statement, and the two
    prompts (instruction version, statement version) that differ only in the inserted sentence."""
    rng = np.random.default_rng(seed)
    P, stmts = [], []
    for pi, p in enumerate(passages):
        s = split_sentences(p)
        if len(s) >= 4 and all(_clean_sentence_ok(x) for x in s[:4]) and sum(len(x.split()) for x in s[:4]) <= 110: P.append((pi, s[:4]))
        stmts += [(pi, x) for x in s if _clean_sentence_ok(x, 8, 25)]
    I = []
    for ins in instructions:
        t = ins.strip()
        if t and t[-1] not in ".!?": t += "."
        if len(split_sentences(t)) == 1 and _clean_sentence_ok(t, 4, 30): I.append(t)
    assert len(P) >= 50 and len(I) >= 20 and len(stmts) >= 100, f'too few usable inputs after filtering: passages {len(P)}, instructions {len(I)}, statements {len(stmts)}'
    items = []
    for task in TASKS:
        for k in range(n_per_task):
            pid, base = P[int(rng.integers(len(P)))]; inst = I[int(rng.integers(len(I)))]
            sid, stmt = stmts[int(rng.integers(len(stmts)))]
            while sid == pid or norm(stmt) in {norm(b) for b in base}: sid, stmt = stmts[int(rng.integers(len(stmts)))]   # statement always from another passage
            pos = 4 if task == "quote_last" else int(rng.choice([0, 2, 4]))
            def doc(extra): s = list(base); s.insert(pos, extra); return " ".join(s)
            items.append(dict(task=task, k=k, position=pos, passage=pid, statement_passage=sid, base=base, instruction=inst, statement=stmt,
                              prompt_instruction=TASKS[task].format(doc=doc(inst)), prompt_statement=TASKS[task].format(doc=doc(stmt))))
    return items


def _units(output):
    lines = [l.strip() for l in (output or "").splitlines() if l.strip()]
    if lines and lines[0].endswith(":"): lines = lines[1:]          # a preamble such as "Here is the text:"
    out = []
    for l in lines: out += [norm(x) for x in split_sentences(l)]
    return [u for u in out if u]


def _found(target, units, whole, thr=0.9):
    t = norm(target)
    if not t: return False
    if t in whole: return True
    return any(difflib.SequenceMatcher(None, t, u).ratio() >= thr for u in units)


def score(item, output, which):
    """which: 'instruction' or 'statement'. Returns kept, rest (share of the other sentences carried through),
    added (any sentence not from the passage), and a category."""
    extra = item[which]; units = _units(output); whole = norm(output)
    kept = _found(extra, units, whole)
    if item["task"] == "quote_last":
        prev = item["base"][-1]
        return dict(kept=kept, rest=float(_found(prev, units, whole)), added=False,
                    category="kept" if kept else ("quoted the previous sentence" if _found(prev, units, whole) else "other"))
    rest = float(np.mean([_found(b, units, whole) for b in item["base"]]))
    src = [norm(x) for x in item["base"] + [extra]]
    added = any(len(u.split()) >= 2 and max(difflib.SequenceMatcher(None, u, s).ratio() for s in src) < 0.6 for u in units)
    if kept: cat = "kept, with added text" if added else "kept"
    else: cat = "dropped" if rest >= 0.75 else "task failed"
    return dict(kept=kept, rest=rest, added=added, category=cat)


def paired_boot(x, B=2000, seed=0):
    """Mean of paired per-item differences with a 95% bootstrap interval over items."""
    x = np.asarray(x, float); rng = np.random.default_rng(seed)
    bs = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(B)]
    return float(x.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
