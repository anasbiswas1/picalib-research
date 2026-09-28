"""Matched guard-level evaluation set from AgentDojo: the benchmark's own tool outputs (emails, calendar entries, drive
files, Slack messages, bills, transactions, hotel and restaurant reviews) with each injection slot filled either by its
benign default or by one of AgentDojo's attack strings for one of its injection tasks. Rendering uses AgentDojo's own
environment loader and attack classes, so the injected texts are exactly what the benchmark's agents would read.
"""
from __future__ import annotations
import re, json
import numpy as np

ATTACKS = ("important_instructions", "ignore_previous", "injecagent", "tool_knowledge", "direct", "system_message")
SUITES = ("workspace", "slack", "banking", "travel")


class _DummyPipe:
    name = "gpt-4o-2024-05-13"


def _flatten(obj, path=()):
    """Yield (path, value) for every leaf of a nested dict/list structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten(v, path + (i,))
    else:
        yield path, obj


def _get(obj, path):
    for p in path: obj = obj[p]
    return obj


def _parent_record(dump, leaf_path):
    """The innermost dict containing the leaf, rendered as 'field: value' lines over its scalar fields."""
    for k in range(len(leaf_path) - 1, -1, -1):
        node = _get(dump, leaf_path[:k])
        if isinstance(node, dict):
            lines = []
            for f, v in node.items():
                if isinstance(v, (str, int, float)) and str(v).strip():
                    lines.append(f"{f}: {v}")
                elif isinstance(v, list) and v and all(isinstance(x, (str, int, float)) for x in v):
                    lines.append(f"{f}: {', '.join(str(x) for x in v)}")
            return leaf_path[:k], "\n".join(lines)
    return (), str(_get(dump, leaf_path))


def attack_texts(suite, attacks=ATTACKS):
    """{(attack, injection_task_id): text} using AgentDojo's attack classes."""
    from agentdojo.attacks.attack_registry import load_attack
    out = {}
    for a in attacks:
        try: atk = load_attack(a, suite, _DummyPipe())
        except Exception: continue
        for tid, it in suite.injection_tasks.items():
            txt = None
            for ut in suite.user_tasks.values():
                try: d = atk.attack(ut, it)
                except Exception: d = {}
                if d: txt = next(iter(d.values())); break
            if txt: out[(a, tid)] = txt
    return out


def build_agentdojo_set(suites=SUITES, attacks=ATTACKS, min_chars=40, max_per_slot=None, seed=0):
    from agentdojo.task_suite.load_suites import get_suites
    S = get_suites("v1"); rng = np.random.default_rng(seed); recs = []
    for sname in suites:
        suite = S[sname]
        defaults = suite.get_injection_vector_defaults(); slots = list(defaults)
        # sentinel environment: locate each slot's leaf and parent record
        sent = {v: f"<<SLOT:{v}>>" for v in slots}
        dump_s = suite.load_and_inject_default_environment(sent).model_dump()
        dump_b = suite.load_and_inject_default_environment({}).model_dump()
        slot_parent = {}
        for path, val in _flatten(dump_s):
            if isinstance(val, str):
                for v in slots:
                    if sent[v] in val:
                        ppath, rendered = _parent_record(dump_s, path); slot_parent[v] = (ppath, rendered)
        texts = attack_texts(suite, attacks)
        kinds = {}
        for v, (ppath, rendered_s) in slot_parent.items():
            kind = ".".join(p for p in ppath if isinstance(p, str) and not p.isdigit()) or "root"
            benign = rendered_s.replace(sent[v], str(defaults[v]))
            for w in slots:                                        # other slots in the same record get their defaults
                benign = benign.replace(sent[w], str(defaults[w]))
            if len(benign) >= min_chars:
                recs.append(dict(text=benign, label=0, suite=sname, kind=kind, slot=v, attack="", injection_task="", form="slot_benign", inj_offset=-1))
            items = list(texts.items())
            if max_per_slot and len(items) > max_per_slot:
                items = [items[i] for i in rng.choice(len(items), max_per_slot, replace=False)]
            for (a, tid), txt in items:
                att = rendered_s.replace(sent[v], txt)
                for w in slots: att = att.replace(sent[w], str(defaults[w]))
                recs.append(dict(text=att, label=1, suite=sname, kind=kind, slot=v, attack=a, injection_task=tid, form="slot_attacked", inj_offset=int(att.find(txt))))
        # extra benign records: every other record with a long scalar field, from the benign environment
        seen = {r["text"] for r in recs}
        for path, val in _flatten(dump_b):
            if isinstance(val, str) and len(val) >= min_chars:
                ppath, rendered = _parent_record(dump_b, path)
                if rendered in seen or len(rendered) < min_chars: continue
                seen.add(rendered); kind = ".".join(p for p in ppath if isinstance(p, str) and not p.isdigit()) or "root"
                recs.append(dict(text=rendered, label=0, suite=sname, kind=kind, slot="", attack="", injection_task="", form="benign_record", inj_offset=-1))
    return recs
