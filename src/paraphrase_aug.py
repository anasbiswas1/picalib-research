"""Paraphrase augmentation for the structural detector, and judge-reproducibility helpers for Phase 5."""
from __future__ import annotations
import re, random
import numpy as np

# Three non-imperative reformulations of an instruction that a reader would still act on. Deliberately different
# from the notebook-12 rewriter (a different model, different prompts), so the evasion test is not the training style.
STYLES = {
    "expectation": ("Rewrite the instruction below as a neutral, descriptive statement of what the reader is expected to do, "
                    "with no imperative verbs and no direct commands. Keep the exact expected behaviour. Output only the rewritten sentence."),
    "reported":    ("Rewrite the instruction below as reported speech, as if a document were quoting what someone asked for, "
                    "keeping the exact expected behaviour. Output only the rewritten sentence."),
    "nominal":     ("Rewrite the instruction below as a passive or nominal sentence that a careful reader would still act on, "
                    "keeping the exact expected behaviour. Output only the rewritten sentence."),
}


def clean_paraphrase(p, unit):
    p = (p or "").strip().strip('"\'`').strip()
    p = re.sub(r"^(rewritten( sentence)?|output|answer)\s*[:\-]\s*", "", p, flags=re.I).strip()
    if not (10 <= len(p) <= 400) or p.lower() == unit.lower() or "\n" in p:
        return None
    return p


def paraphrase_units(units, generate, temperature=0.7, max_new_tokens=60, batch_size=16):
    """generate(prompts, system, max_new_tokens, temperature, batch_size) -> list[str]. Returns {unit: [paraphrases]}."""
    out = {u: [] for u in units}
    for style, sys_prompt in STYLES.items():
        gens = generate([f"Instruction: {u}" for u in units], sys_prompt, max_new_tokens, temperature, batch_size)
        for u, g in zip(units, gens):
            c = clean_paraphrase(g, u)
            if c and c not in out[u]: out[u].append(c)
    return out


def augment_records(records, para_map, rng, frac=0.5, test_texts=()):
    """For a fraction of embedded records, replace the unit inside the text with a paraphrase (label 1), and add each used
    paraphrase as a raw standalone (label 0). Records whose unit is not found verbatim, or without paraphrases, are skipped."""
    test_texts = set(test_texts); aug, twins, used = [], [], set()
    emb = [r for r in records if r["form"] == "embedded" and r["unit"] in para_map and para_map[r["unit"]]]
    rng.shuffle(emb)
    for r in emb[: int(frac * len(emb))]:
        p = rng.choice(para_map[r["unit"]])
        if r["text"].count(r["unit"]) != 1: continue
        t = r["text"].replace(r["unit"], p)
        if t in test_texts: continue
        aug.append({**r, "text": t, "unit": p, "form": "embedded_paraphrase", "payload": r["payload"] + "_paraphrase"})
        if p not in used and p not in test_texts:
            used.add(p); twins.append({**r, "text": p, "label": 0, "form": "standalone_paraphrase", "unit": p, "host_src": "", "position": "", "delim": ""})
    return aug, twins


def agreement(a, b, keys):
    keys = [k for k in keys if k in a and k in b]
    return float(np.mean([bool(a[k]) == bool(b[k]) for k in keys])) if keys else np.nan
