"""
data_loaders.py — Gate 1 data spine
====================================
Harmonise prompt-injection datasets to ONE schema so the transport / dedup
code never has to know dataset-specific quirks.

Common schema (pandas DataFrame):
    text       : str   the input to the detector
    label      : int   1 = attack, 0 = benign
    source     : str   dataset tag ('deepset', 'notinject', 'bipia', ...)
    unit_type  : str   'standalone_prompt'  | 'instruction_in_document'
                       (the detection-unit call: is the attack a free-standing
                        prompt, or an instruction buried in a document/email?)

Verified loaders (load cleanly via HF `datasets`):
    - load_deepset()    direct injection + benign      (deepset/prompt-injections)
    - load_notinject()  benign hard-negatives          (leolee99/NotInject)
Best-effort loader (clones GitHub; prints diagnostics if layout differs):
    - load_bipia()      indirect injection             (microsoft/BIPIA)

Note on sources for the Gate-1 PROBE: the concept note commits Open-Prompt-
Injection as the direct primary with deepset as backup. For the cheap go/no-go
we use deepset because it loads in one line; swap to OPI when scaling up.
"""

import os
import subprocess
import glob
import json
import pandas as pd


def _schema(texts, labels, source, unit_type, meta=None):
    df = pd.DataFrame({"text": [str(t) for t in texts], "label": [int(x) for x in labels]})
    df["source"] = source
    df["unit_type"] = unit_type
    if meta is not None:
        df["meta"] = meta
    # drop empties / dedupe exact repeats within a source
    df = df[df["text"].str.strip().str.len() > 0]
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)
    return df


# --------------------------------------------------------------------------- #
# VERIFIED: direct injection + benign
# --------------------------------------------------------------------------- #
def load_deepset():
    """deepset/prompt-injections — columns: text, label (1=injection, 0=benign).
    Standalone prompts."""
    from datasets import load_dataset
    ds = load_dataset("deepset/prompt-injections")
    frames = [ds[sp].to_pandas() for sp in ds.keys()]
    d = pd.concat(frames, ignore_index=True)
    return _schema(d["text"].tolist(), d["label"].astype(int).tolist(),
                   "deepset", "standalone_prompt")


# --------------------------------------------------------------------------- #
# VERIFIED: benign hard-negatives (over-defense anchor) — all label 0
# --------------------------------------------------------------------------- #
def load_notinject():
    """leolee99/NotInject — 339 benign prompts laced with trigger words.
    Column 'prompt'; all benign. Standalone prompts. (cite InjecGuard 2410.22770)"""
    from datasets import load_dataset
    ds = load_dataset("leolee99/NotInject")
    frames = []
    for sp in ds.keys():
        d = ds[sp].to_pandas()
        col = "prompt" if "prompt" in d.columns else d.columns[0]
        frames.append(d.rename(columns={col: "prompt"})[["prompt"]])
    d = pd.concat(frames, ignore_index=True)
    return _schema(d["prompt"].tolist(), [0] * len(d),
                   "notinject", "standalone_prompt")


# --------------------------------------------------------------------------- #
# BEST-EFFORT: indirect injection (instruction-in-document)
# --------------------------------------------------------------------------- #
def load_bipia(workdir="/content/_bipia"):
    """Clone microsoft/BIPIA and pull its text-attack instructions as the
    indirect-injection ATTACK payloads (unit_type = instruction_in_document).

    This loader is defensive: it clones the repo and searches for the attack
    files rather than hard-coding paths (the layout can change). If it can't
    find them it prints what it DID find so you can wire it up in one edit.
    Returns an attack-only frame (label=1); pair with benign contexts later.
    """
    if not os.path.exists(workdir):
        print("Cloning microsoft/BIPIA ...")
        subprocess.run(["git", "clone", "--depth", "1",
                        "https://github.com/microsoft/BIPIA.git", workdir],
                       check=False)
    # search for attack definition files (json/jsonl/csv mentioning 'attack')
    candidates = []
    for ext in ("json", "jsonl", "csv", "txt"):
        candidates += glob.glob(os.path.join(workdir, "**", f"*attack*.{ext}"),
                                recursive=True)
    print(f"BIPIA: found {len(candidates)} candidate attack files.")
    for c in candidates[:20]:
        print("  ", c.replace(workdir, "BIPIA"))

    texts = []
    for c in candidates:
        try:
            if c.endswith(".jsonl"):
                with open(c) as f:
                    for line in f:
                        obj = json.loads(line)
                        texts += _strings_from(obj)
            elif c.endswith(".json"):
                obj = json.load(open(c))
                texts += _strings_from(obj)
            elif c.endswith(".csv"):
                d = pd.read_csv(c)
                for col in d.columns:
                    if d[col].dtype == object:
                        texts += d[col].dropna().astype(str).tolist()
            elif c.endswith(".txt"):
                texts += [l.strip() for l in open(c) if l.strip()]
        except Exception as e:  # noqa
            print(f"  (skipped {c}: {e})")

    texts = [t for t in dict.fromkeys(texts) if 3 < len(t) < 2000]
    if not texts:
        raise RuntimeError(
            "BIPIA: no attack texts parsed. Inspect the printed file list and "
            "point this loader at the right file, or use LLMail-Inject instead.")
    print(f"BIPIA: parsed {len(texts)} attack instruction strings.")
    return _schema(texts, [1] * len(texts), "bipia", "instruction_in_document")


def _strings_from(obj, _key_hint=("attack", "instruction", "text", "prompt", "payload")):
    """Pull plausible attack-instruction strings out of a nested json object."""
    out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and (any(h in str(k).lower() for h in _key_hint)):
                out.append(v)
            else:
                out += _strings_from(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _strings_from(v)
    return out


# --------------------------------------------------------------------------- #
# load everything available, report what succeeded
# --------------------------------------------------------------------------- #
def load_all(include_bipia=True):
    """Try each loader; return (combined_df, report). Never hard-fails on one
    source — Gate 1 should still run on whatever loaded."""
    loaders = [("deepset", load_deepset), ("notinject", load_notinject)]
    if include_bipia:
        loaders.append(("bipia", load_bipia))
    frames, report = [], {}
    for name, fn in loaders:
        try:
            df = fn()
            frames.append(df)
            report[name] = {"ok": True, "n": len(df),
                            "n_attack": int((df.label == 1).sum()),
                            "n_benign": int((df.label == 0).sum())}
            print(f"[ok]   {name:10s} n={len(df)}")
        except Exception as e:  # noqa
            report[name] = {"ok": False, "error": str(e)}
            print(f"[skip] {name:10s} {e}")
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined, report


# --------------------------------------------------------------------------- #
# IMPROVED indirect loader: assemble REALISTIC instruction-in-document samples
# (benign BIPIA context, vs context with a text-attack instruction injected)
# --------------------------------------------------------------------------- #
def _bipia_contexts(workdir, tasks=("email", "table")):
    """Read BIPIA's shipped document contexts (email/table are clean strings;
    qa/abstract are license-gated and absent; code is a different attack type)."""
    out = []
    for task in tasks:
        for split in ("test", "train"):
            fp = os.path.join(workdir, "benchmark", task, f"{split}.jsonl")
            if not os.path.exists(fp):
                continue
            with open(fp) as f:
                for line in f:
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    ctx = o.get("context")
                    if isinstance(ctx, str) and 20 < len(ctx) < 6000:
                        out.append(ctx)
    return out


def _bipia_text_attacks(workdir):
    """Flatten BIPIA's text-attack instruction strings."""
    atks = []
    for fp in glob.glob(os.path.join(workdir, "benchmark", "text_attack_*.json")):
        try:
            obj = json.load(open(fp))
        except Exception:
            continue
        atks += _strings_from(obj)
    return [a for a in dict.fromkeys(atks) if 3 < len(a) < 1000]


def load_bipia_indirect(workdir="/content/_bipia", n_attack=400, seed=2023,
                        position="end"):
    """REALISTIC indirect injection. A real indirect sample is a benign document
    (BIPIA email/table context) with a text-attack instruction inserted at a
    position -- NOT a bare attack string. Returns both:
        label 1 = context + injected attack instruction
        label 0 = context only (indirect benign)
    unit_type = instruction_in_document.

    position in {'start','middle','end'} (BIPIA varies all three; 'end' default).
    For the final panel, BIPIA's official AutoPIABuilder gives exact position
    sampling; this controlled assembler is for the Gate re-run.
    """
    import random
    rng = random.Random(seed)
    if not os.path.exists(workdir):
        print("Cloning microsoft/BIPIA ...")
        subprocess.run(["git", "clone", "--depth", "1",
                        "https://github.com/microsoft/BIPIA.git", workdir], check=False)
    contexts = _bipia_contexts(workdir)
    attacks = _bipia_text_attacks(workdir)
    print(f"BIPIA indirect: {len(contexts)} contexts, {len(attacks)} text attacks")
    if not contexts or not attacks:
        raise RuntimeError("BIPIA indirect: missing contexts/attacks; check repo layout.")
    rng.shuffle(contexts)
    rng.shuffle(attacks)

    def inject(ctx, atk, pos):
        if pos == "start":
            return atk + "\n\n" + ctx
        if pos == "middle":
            mid = len(ctx) // 2
            return ctx[:mid] + "\n" + atk + "\n" + ctx[mid:]
        return ctx + "\n" + atk

    atk_rows = [inject(contexts[i % len(contexts)],
                       attacks[(i * 7 + 3) % len(attacks)], position)
                for i in range(n_attack)]
    ben_rows = list(dict.fromkeys(contexts))  # unique contexts as indirect benigns

    texts = atk_rows + ben_rows
    labels = [1] * len(atk_rows) + [0] * len(ben_rows)
    return _schema(texts, labels, "bipia", "instruction_in_document")
