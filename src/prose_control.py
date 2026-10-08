"""Prose-host control for the AgentDojo result (Section 7.5): the benchmark's own attack strings placed inside prose
documents of the kind the structural detector was trained on, scored against those documents alone.

The attack strings are recovered from the cached AgentDojo set (data/agentdojo/set.json), so they are exactly the strings
the tool-output evaluation used, whatever version of the agentdojo package is installed now. Every attacked record of a
slot is the same rendered record with the slot filled by one attack string, so all attacked records of a slot share the
text before the slot (its length is the record's inj_offset) and the text after it (their longest common suffix). The
string is what lies between.

Hosts are the host_only documents of the structural detector's held-out test split (SQuAD and AG News paragraphs it never
saw in training). Each attack string goes into `per_string` distinct hosts, once at the start, once in the middle and
once at the end, separated by a blank line, with structural_data.embed. The benign set is the same hosts unchanged, so
the two sets differ only by the inserted string.
"""
from __future__ import annotations
import collections
import random
import numpy as np


def _common_suffix_len(texts):
    if not texts: return 0
    s = min(len(t) for t in texts); k = 0
    while k < s and len({t[len(t) - 1 - k] for t in texts}) == 1: k += 1
    return k


def extract_attack_strings(records):
    """{(suite, attack, injection_task): string} recovered from the cached set, with a consistency report."""
    by_slot, benign = collections.defaultdict(list), {}
    for r in records:
        if r.get("label") == 1 and r.get("inj_offset", -1) >= 0: by_slot[(r["suite"], r["slot"])].append(r)
        elif r.get("form") == "slot_benign": benign[(r["suite"], r["slot"])] = r["text"]
    cand = collections.defaultdict(list)
    for (suite, slot), rs in by_slot.items():
        if len({r["attack"] + "|" + r["injection_task"] for r in rs}) < 2: continue   # the suffix needs two different strings
        suf = _common_suffix_len([r["text"] for r in rs])
        if (suite, slot) in benign: suf = min(suf, _common_suffix_len([rs[0]["text"], benign[(suite, slot)]]))   # both bound the true suffix from above
        for r in rs:
            s = r["text"][r["inj_offset"]: len(r["text"]) - suf]
            if s.strip(): cand[(suite, r["attack"], r["injection_task"])].append(s)
    out, agree = {}, []
    for key, ss in cand.items():
        s, c = collections.Counter(ss).most_common(1)[0]; out[key] = s; agree.append(c / len(ss))
    return out, dict(strings=len(out), slots=len(by_slot), mean_agreement_across_slots=float(np.mean(agree)) if agree else float("nan"),
                     min_agreement_across_slots=float(np.min(agree)) if agree else float("nan"))


def build_prose_set(strings, hosts, embed_fn, per_string=3, seed=48, delim="\n\n"):
    """strings: {(suite, attack, task): text}; hosts: list of host texts. Returns (records, benign_hosts)."""
    keys = sorted(strings); need = len(keys) * per_string
    assert len(hosts) >= need, f"need {need} distinct hosts, have {len(hosts)}"
    rng = np.random.default_rng(seed); order = rng.permutation(len(hosts))[:need]; prng = random.Random(seed)
    positions = ["start", "middle", "end"]
    recs, used = [], []
    for j, key in enumerate(keys):
        for m in range(per_string):
            h = hosts[int(order[j * per_string + m])]; pos = positions[m % 3]
            recs.append(dict(text=embed_fn(h, strings[key], pos, delim, prng), label=1, suite=key[0], attack=key[1], injection_task=key[2],
                             string_id=j, position=pos, host=h))
            used.append(h)
    ben = [dict(text=h, label=0, suite="", attack="", injection_task="", string_id=-1, position="", host=h) for h in used]
    return recs, ben


def cluster_boot(fn, groups_atk, idx_ben, B=1000, seed=0):
    """Bootstrap resampling attack strings (all their documents together) and benign hosts."""
    rng = np.random.default_rng(seed); g = list(groups_atk.values()); vals = []
    for _ in range(B):
        pick = rng.integers(0, len(g), len(g)); ai = np.concatenate([g[k] for k in pick]); bi = rng.choice(idx_ben, len(idx_ben), replace=True)
        try: vals.append(fn(ai, bi))
        except Exception: pass
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))
