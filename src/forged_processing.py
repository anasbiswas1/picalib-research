"""Forged-turn processing examples (notebook 73e).

Notebooks 73 and 73d trained the 3B on forged-turn examples whose task is always a summary: the document holds an
instruction placed in one of notebook 72's eight attack forms (TRAIN wording), and the right reply to an attacked example
leaves it out. Both runs lowered attack success on notebook 72's suite but failed SecFid fidelity (P2); in notebook 73d
the loss sat in counting and extraction. A likely cause: the model learned to leave such lines out also where the task
must count or list what they contain. These examples show the other half: the same forged lines inside a text that the
user asks to count, list or copy, with the exact answer computed by code, which counts, lists or copies the forged line
like any other text. Not obeying an instruction is different from leaving it out of a text being processed: the summary
examples teach the model not to obey; these teach it to still count, list or copy the line.

  count_entities   how many different <things of a kind> the text names; the forged instruction names one of them
  list_entities    list them in order of first mention
  count_questions  how many questions the text contains; the forged instruction is a question
  list_numbers     list every number in the text; the forged instruction carries a number
  copy             copy the text in capital letters, without commas, or with END on a new line (notebook 38's tasks)

The families, instructions, word lists and passages are those of notebooks 65 and 38 (src/processing_literal.py,
src/literal_tasks.py); the forged lines are those of notebook 73 (src/manual_attacks.py, TRAIN wordings, the model's
special tokens filtered as at test time). Each form takes an equal share, the five families take equal shares within
each form, and the positions rotate. No SecFid text, template or entity type is used."""
from __future__ import annotations
import re
import numpy as np
from fidelity_exact import split_sentences, _clean_sentence_ok
from processing_literal import GAZ, PROBE, MENTION, INSTR, NUM_RE, entities_in, gold_for, check_gazetteer, _fill
from literal_tasks import LITERAL
from manual_attacks import FORMS, POSITIONS, payload, filter_special

SLOTS = ("count_entities", "list_entities", "count_questions", "list_numbers", "copy")
COPY = ("upper", "nocomma", "endword")


def copy_gold(task, doc):
    if task == "upper": return doc.upper()
    if task == "nocomma": return doc.replace(",", "")
    if task == "endword": return doc + "\nEND"
    raise ValueError(task)


def host_bases(hosts):
    """Notebook 65's host rule: the first three or four clean sentences of a passage, at most 100 words, no question."""
    H = []
    for p in hosts:
        s = split_sentences(p)
        if len(s) >= 3 and all(_clean_sentence_ok(x) for x in s[:4]):
            base = s[:4] if sum(len(x.split()) for x in s[:4]) <= 100 else s[:3]
            if sum(len(x.split()) for x in base) <= 100 and not any(x.rstrip().endswith("?") for x in base): H.append(base)
    return H


def build_forged_processing(hosts, instructions, family, per_form=50, seed=0, keep=lambda e: True):
    """per_form examples for every attack form (FORMS); hosts: training passages; instructions: Alpaca training
    instructions, one sentence each, ending in . ! or ?; keep(example) applies the caller's separation checks, and a
    rejected draw is replaced by the next one."""
    assert per_form % len(SLOTS) == 0
    check_gazetteer(); rng = np.random.default_rng(seed); H = host_bases(hosts); kinds = list(GAZ)
    glued = lambda t: bool(re.search(r"\d", NUM_RE.sub("", t)))      # a digit NUM_RE cannot list (2x, 5cm, 20th): such texts are not used for list_numbers
    Q = [t for t in instructions if t.endswith("?")]; IN = [t for t in instructions if NUM_RE.search(t) and not t.endswith("?") and not glued(t)]
    loose = {k: [re.compile(r"(?<!\w)" + re.escape(e[:-1] if e.endswith("s") else e) + r"\w{0,3}(?!\w)", re.I) for e in GAZ[k]] for k in kinds}
    clean = {k: [h for h in H if not any(p.search(" ".join(h)) for p in loose[k])] for k in kinds}      # also no plural or longer form of a word of the kind
    assert len(H) >= 300 and len(Q) >= 100 and len(IN) >= 50 and min(len(v) for v in clean.values()) >= 100, (len(H), len(Q), len(IN))
    pick = lambda L: L[int(rng.integers(len(L)))]
    out, tries = [], 0
    for fi, f in enumerate(FORMS):
        got = []
        while len(got) < per_form:
            tries += 1; assert tries < 50 * len(FORMS) * per_form, "too many rejected draws"
            slot = len(got); fam = SLOTS[slot % len(SLOTS)]; pos = POSITIONS[(slot + fi) % len(POSITIONS)]; kind = probe = task = None
            if fam in ("count_entities", "list_entities"):
                kind = pick(kinds); sents = list(pick(clean[kind]))
                ents = [str(x) for x in rng.choice(GAZ[kind], int(rng.integers(2, 5)), replace=False)]; probe = ents[-1]
                for e in ents[:-1]: sents.insert(int(rng.integers(0, len(sents) + 1)), _fill(pick(MENTION), e))
                ins = _fill(pick(PROBE), probe); instr = pick(INSTR[fam]).replace("{T}", kind)
            elif fam == "count_questions":
                sents = list(pick(H))
                for _ in range(int(rng.integers(0, 3))): sents.insert(int(rng.integers(0, len(sents) + 1)), pick(Q))
                ins = pick(Q); instr = pick(INSTR[fam])
            elif fam == "list_numbers":
                sents = list(pick(H)); ins = pick(IN); instr = pick(INSTR[fam])
            else:
                task = COPY[(slot // len(SLOTS) + slot // (len(SLOTS) * len(COPY))) % len(COPY)]; sents = list(pick(H)); ins = pick(instructions)      # each copy task meets every position
            sents.insert({"start": 0, "middle": len(sents) // 2, "end": len(sents)}[pos], payload(ins, f, family, "train"))
            doc = filter_special(" ".join(sents), family)      # not stripped: at the start, the wrapper's leading line breaks are part of the form
            if fam == "copy": prompt, gold = LITERAL[task].format(doc=doc), copy_gold(task, doc)
            else: prompt, gold = instr + "\n\n" + doc, gold_for(fam, doc, kind)
            if fam == "list_numbers" and (not gold or gold.count(",") > 9 or glued(doc)): continue
            e = dict(kind="literal", source="forged_processing", task=task or fam, family=fam, form=f, position=pos, inserted=ins,
                     entity_kind=kind, probe=probe, prompt=prompt, gold=gold)
            if keep(e): got.append(e)
        out += got
    return out
