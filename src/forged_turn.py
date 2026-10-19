"""Forged-turn examples (notebook 73).

Notebook 72 ran the standard manual attacks of the StruQ, SecAlign and Meta-SecAlign evaluations. The defended models resist the
classic forms (the injection as it is, an order to ignore the earlier instructions, escape characters, a fake completion in
plain-text markers) and fail where the document pretends to be the user: a fake chat turn, a "User:" line, a claim that the user
changed the task. The likely reason is the twins: they teach the model to follow an instruction that comes from the user, and a
line dressed as a user turn inside the document borrows that. This module builds both sides for all eight attack forms, with the TRAIN wordings of
src/manual_attacks.py; notebook 72 tests on the TEST wordings, which differ.

  attacked  a summary request on a training passage; inside the passage, an Alpaca training instruction wrapped in one attack
            form (TRAIN wording) at the start, the middle or the end, with the model family's special tokens removed from the
            passage, as at test time. The teacher, the model with the adapter off, summarises the clean passage (twin
            distillation's target).
  twin      paired with an attacked example: the same instruction on the same passage, made by the real user in the user's own
            turn next to the summary request, on the clean passage; the teacher sees that very prompt, so the model keeps doing
            what its user asks. For the three forms worded
            as speech (ignore, fake_user, authority) half the twins keep that wording: where the words stand decides, not how
            they are put.

The eight forms take equal shares and the positions rotate. test_markers() gives the TEST wordings as they appear in a filtered
document, so the caller can assert that no training example contains one."""
from __future__ import annotations
import numpy as np
from manual_attacks import FORMS, POSITIONS, payload, place, filter_special

SPOKEN = ("ignore", "fake_user", "authority")
_MARK = "\x00"


def wrapper(form, family, wordings="train"):
    """The text an attack form puts before the injection, special tokens filtered (as the model sees it)."""
    return filter_special(payload(_MARK, form, family, wordings), family).split(_MARK)[0]


def test_markers(family):
    """The TEST wording of every form but naive, as it appears in a filtered document (a whitespace-only wording kept whole)."""
    out = []
    for f in FORMS:
        if f != "naive":
            w = wrapper(f, family, "test"); out.append(w.strip() or w)
    return out


def forged_attacked(host, instruction, form, family, position, task_user):
    doc = filter_special(place(host, payload(instruction, form, family, "train"), position), family)
    return dict(kind="attacked", source="forged_turn", form=form, position=position, inserted=instruction,
                student=task_user.format(doc=doc), teacher=task_user.format(doc=host))


def forged_twin(host, instruction, form, family, keep_wording, task_user_with):
    """On one line, so a two-role split keeps all of it in the user turn."""
    said = " ".join(((wrapper(form, family) if keep_wording and form in SPOKEN else "") + instruction).split())
    t = task_user_with.format(instr=said, doc=host)
    return dict(kind="twin", source="forged_turn", form=form, inserted=instruction, said=said, student=t, teacher=t)


def build_forged(hosts, instructions, family, task_user, task_user_with, per_form_attacked, per_form_twin, keep, seed=0):
    """per_form_attacked attacked examples for every form, drawn in a fixed order, and a twin for each of the first
    per_form_twin of them (the same passage and instruction); keep(example) applies the caller's separation checks, and a
    rejected draw is replaced by the next one."""
    assert per_form_twin <= per_form_attacked
    rng = np.random.default_rng(seed); out = []; tries = 0
    for f in FORMS:
        att = []
        while len(att) < per_form_attacked:
            tries += 1; assert tries < 50 * len(FORMS) * per_form_attacked, "too many rejected draws"
            host = hosts[int(rng.integers(len(hosts)))]; ins = instructions[int(rng.integers(len(instructions)))]
            e = forged_attacked(host, ins, f, family, POSITIONS[len(att) % len(POSITIONS)], task_user)
            if keep(e): e["pair"] = f"{f}-{len(att)}"; e["host"] = host; att.append(e)
        tw = []
        for e in att:
            if len(tw) == per_form_twin: break
            t_ = forged_twin(e["host"], e["inserted"], f, family, len(tw) % 2 == 0, task_user_with)
            if keep(t_): t_["pair"] = e["pair"]; t_["host"] = e["host"]; tw.append(t_)
        assert len(tw) == per_form_twin, f"only {len(tw)} twins pass the checks for {f}"
        out += att + tw
    return out
