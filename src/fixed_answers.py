"""Processing tasks as fixed answers (notebook 82d4).

Adversarial twin distillation distils an attacked example towards the base model's reply to the clean document. That
teacher never sees the injected instruction, so the student learns not to carry it out (on the evidence pairs ATD-r
carried it out 0.034 of the time, the role model 0.168). It also learns to leave the injected sentence out of a text it
must process: ATD-r's SecFid fidelity was 0.123 below the role model's, 0.247 below with the injected text at the end.
Notebook 82d3's content-preserving teacher saw the injected instruction and raised SecFid fidelity above the role
model's (by 0.085), but its student learned to answer the instruction and carried it out 0.409 of the time.

Notebook 82d4 keeps the clean teacher and changes what the student sees about processing:
  task_class       an attacked example's task, from its instruction: 'transform' when the reply rewrites or reorders
                   the input itself (rewrite, translate, edit, convert, sort ...), 'extract' when it lists or counts
                   things found in the input, 'other' for summaries, answers and new text. Where the rule finds the task
                   is not 'other', the clean teacher's reply leaves the injected sentence out of a text the task must
                   process; notebook 82d4 takes those attacked examples (with their twins) and those pool sources out.
                   The rule reads wording, so it misses some such tasks and takes out a few others.
  edit_example     an editing example with its exact answer: a training passage holding an injected instruction (at
                   the start, in the middle or at the end) and one stated edit to another sentence (replace a word,
                   delete a sentence, correct a misspelling, change a number). The edited word or number occurs once in
                   the text in any form, so the edit is unambiguous. The answer is the whole text with that edit made
                   and every other sentence, the injected one included, unchanged; edit_gold recomputes it.
  translation_item a translation example: the prompt, and the text in three parts (the sentences before the injected
                   sentence, the injected sentence alone, the sentences after). The base model translates each part on
                   its own and join_parts joins them into the fixed answer, so the injected sentence is translated as a
                   sentence and never read as part of a task done for the user. The notebook keeps an answer only if
                   the judge finds the injected sentence's part does not carry it out, and every part is a plain
                   translation (part_problem: no preamble or added note), in the target language, of its source's
                   number of sentences and of a fitting length.
No teacher ever sees an injected instruction: these examples train through the exact-target loss. The task types are
SecFid's on purpose (translation into SecFid's five languages; small stated edits like SecFid's), so SecFid's
translation and editing fidelity are no longer fully held out. Its texts are not used: the passages are the project's
training passages, the injected sentences Alpaca training instructions, and the wordings differ from SecFid's ("Please
translate the following text to X.", "Please do the following edit task. ...")."""
from __future__ import annotations
import re
import numpy as np

# ---- which attacked examples' tasks process the injected sentence ----
TRANSFORM = frozenset("""rewrite rephrase reword paraphrase restate reformulate translate edit correct proofread revise convert transform change modify alter
replace substitute remove delete omit eliminate insert add reverse sort arrange rearrange reorder reorganize reorganise organize organise rank alphabetize
alphabetise capitalize capitalise punctuate format reformat fix simplify shorten condense compress expand improve polish refine combine merge split separate
turn put copy reduce make order update return""".split())
EXTRACT = frozenset("extract list count identify find locate highlight underline pick select name".split())
NEEDS_OBJ = frozenset("add put turn split separate combine merge improve expand copy reduce make order update return".split())   # these transform the input only when it is their object
TEXTS = (r"(sentence|sentences|text|texts|paragraph|paragraphs|passage|passages|word|words|list|phrase|phrases|statement|tweet|poem|story|article|email|letter|essay|description|"
         r"review|content|input|quote|title|headline|code|items|names|numbers)")
MODS = r"((following|given|input|above|below|provided|two|three|four|first|second|last|next)\s+)*"
OBJ = re.compile(r"\b(it|them)\b|\b(this|these|those|the|each|every|both|all)\s+" + MODS + TEXTS + r"\b|\b(a|an)\s+(given|following|provided|input)\s+" + MODS + TEXTS + r"\b")
SCOPE = re.compile(r"\b(in|from|within|inside|of)\s+(the|this|these|that|each|every|a|an)?\s*(following|given|provided|above|below|input)?\s*"
                   r"(text|sentence|sentences|passage|paragraph|paragraphs|article|list|document|statement|story|poem|haiku|tweet|email|letter|review|input|data|excerpt|quote|lyrics|dialogue|conversation|string|code|words|context)\b")
ITEMS = re.compile(r"\b(all|every|each|any)\b|\b(words|nouns|verbs|adjectives|adverbs|pronouns|prepositions|conjunctions|names|numbers|dates|places|people|cities|countries|errors|mistakes|typos|items|entities|"
                   r"keywords|phrases|letters|vowels|consonants|digits|symbols|characters|occurrences|instances|syllables)\b")
INPUT_REF = re.compile(r"\b(given|following|this|these|provided|above|below|input)\b")
LANG = re.compile(r"\b(into|in|to)\s+(english|spanish|french|german|italian|portuguese|chinese|japanese|korean|russian|arabic|hindi|latin|dutch|swedish|greek|turkish|polish)\b"
                  r"|\b(spanish|french|german|italian|portuguese|chinese|japanese) (equivalent|translation|version)\b")
AND_T = re.compile(r"\band\s+(correct|rewrite|edit|fix|replace|convert|translate|rephrase|paraphrase|reword)\s+(it|them|the|this|these|each|every|any)\b")
LEAD = re.compile(r"^(?:(?:please|kindly|now|then|can you|could you|would you|will you|you need to|you have to|you should|you must|your task is to)\s+|"
                  r"(?:given|using|from|for|with|based on|provided with|you are provided with|you are given|you will be given|consider(?:ing)?|in this task|in the|in a|for the|here is|here are|read|scan|look at)\b"
                  r"[^,.;:?]*[,:]\s*(?:please\s+)?)", re.I)
TAKE = re.compile(r"^(?:take|read|scan|look at|consider|examine|analy[sz]e|find)\b[^,.;:?]*?\band\s+(\w+)", re.I)
RE_VERBS = ("write", "arrange", "order", "word", "phrase", "organize", "organise")


def _verb(sent):
    s = sent
    for _ in range(4):
        s2 = LEAD.sub("", s, count=1).strip()
        if s2 == s: break
        s = s2
    m = TAKE.match(s); v = (m.group(1) if m else (s.split() or [""])[0]).lower().strip(",.:;!?\"'")
    if v.startswith("re-") and v[3:] in RE_VERBS: v = "re" + v[3:]
    return v, s


def task_class(instr):
    """'transform', 'extract' or 'other' (see the module docstring)."""
    text = " ".join((instr or "").split()); low_all = text.lower()
    if LANG.search(low_all) or AND_T.search(low_all): return "transform"
    for sent in [x for x in re.split(r"(?<=[.!?])\s+", text) if x]:
        v, s = _verb(sent); low = s.lower()
        if v in TRANSFORM and (v not in NEEDS_OBJ or OBJ.search(low)): return "transform"
        if v == "count" and (SCOPE.search(low) or INPUT_REF.search(low_all)): return "extract"
        if v in EXTRACT and SCOPE.search(low) and ITEMS.search(low): return "extract"
    return "other"


# ---- the injected sentence in a passage ----
POSITIONS = ("start", "middle", "end")


def g_index(n, where):
    """Where the injected sentence goes among n sentences: first, after the first half, or last."""
    return 0 if where == "start" else (n if where == "end" else max(1, n // 2))


def place(sents, g, where):
    """The passage's sentences with the injected sentence g at the start, in the middle or at the end."""
    k = g_index(len(sents), where); return list(sents[:k]) + [g] + list(sents[k:])


# ---- editing ----
EDIT_KINDS = ("replace_word", "delete_sentence", "fix_spelling", "change_number")
EDIT_INSTR = {
    "replace_word": ['Replace the word "{a}" with "{b}" in the text below and return the whole text.',
                     'In the following text, change the word "{a}" to "{b}". Return the whole text with nothing else changed.'],
    "delete_sentence": ['Delete the sentence that begins with "{a}" from the text below and return the rest of the text unchanged.',
                        'Remove the sentence starting with "{a}" from the following text. Return everything else exactly as it is.'],
    "fix_spelling": ['Correct the misspelled word "{a}" to "{b}" in the text below and return the whole text.',
                     'The word "{a}" in the following text is misspelled. Replace it with "{b}" and return the whole text.'],
    "change_number": ['Change the number {a} to {b} in the text below and return the whole text.',
                      'In the following text, replace the number {a} with {b}. Return the whole text with nothing else changed.']}
NEW_WORDS = ["lantern", "harbour", "meadow", "copper", "violet", "ember", "orchard", "glacier", "ribbon", "summit", "pebble", "falcon", "willow", "canyon",
             "marble", "thistle", "beacon", "saffron", "quarry", "cobalt", "juniper", "sparrow", "tundra", "velvet", "walnut"]
WORD = re.compile(r"(?<![\w'-])([a-z]{5,})(?![\w'-])")
NUMBER = re.compile(r"(?<![\w.,])(\d{1,4})(?![\w.,%])")


def _count_word(w, sents):          # every occurrence in any form (person's, state-of-the-art, any case)
    return sum(len(re.findall(r"\b" + re.escape(w) + r"\b", s, re.I)) for s in sents)


def _count_number(n, sents):        # every occurrence in any form (11, 11. 11% 1.11): only other digits end it
    return sum(len(re.findall(r"(?<!\d)" + re.escape(n) + r"(?!\d)", s)) for s in sents)


def apply_edit(sents, edit):
    """The sentences after the edit, computed exactly."""
    out = list(sents); i = edit["i"]
    if edit["kind"] == "delete_sentence":
        assert " ".join(out[i].split()[:4]) == edit["frm"]; del out[i]; return out
    a, b = edit["span"]; assert out[i][a:b] == edit["frm"]
    out[i] = out[i][:a] + edit["to"] + out[i][b:]; return out


def edit_example(sents, g, where, rng, kind, wording):
    """An editing example (see the module docstring), or None when the passage offers no place for this kind of edit.
    The edit never touches the injected sentence g."""
    S = place(sents, g, where); gi = g_index(len(sents), where)
    host = [i for i in range(len(S)) if i != gi]
    pick = lambda xs: xs[int(rng.integers(len(xs)))]
    if kind in ("replace_word", "fix_spelling"):
        L = 5 if kind == "replace_word" else 6
        cands = [(i, m) for i in host for m in WORD.finditer(S[i]) if len(m.group(1)) >= L and _count_word(m.group(1), S) == 1]
        if not cands: return None
        i, m = pick(cands); w = m.group(1)
        if kind == "replace_word":
            doc_words = {x.lower() for x in re.findall(r"[A-Za-z]+", " ".join(S))}; new = [x for x in NEW_WORDS if x not in doc_words]
            if not new: return None
            edit = dict(kind=kind, i=i, frm=w, to=pick(new), span=[m.start(1), m.end(1)]); P = S
        else:
            j = int(rng.integers(1, len(w) - 2)); bad = w[:j] + w[j + 1] + w[j] + w[j + 2:]
            if bad == w or _count_word(bad, S): return None
            P = list(S); P[i] = S[i][:m.start(1)] + bad + S[i][m.end(1):]
            edit = dict(kind=kind, i=i, frm=bad, to=w, span=[m.start(1), m.start(1) + len(bad)])
        a_, b_ = edit["frm"], edit["to"]
    elif kind == "delete_sentence":
        cands = [i for i in host if len(S[i].split()) >= 6 and sum(s.split()[:4] == S[i].split()[:4] for s in S) == 1]
        if not cands or len(S) < 4: return None
        i = pick(cands); edit = dict(kind=kind, i=i, frm=" ".join(S[i].split()[:4]), to=None, span=None); P = S; a_, b_ = edit["frm"], None
    elif kind == "change_number":
        cands = [(i, m) for i in host for m in NUMBER.finditer(S[i]) if _count_number(m.group(1), S) == 1]
        if not cands: return None
        i, m = pick(cands); n = m.group(1); to = str(int(n) + int(rng.choice([1, 2, 10])))
        if _count_number(to, S): return None
        edit = dict(kind=kind, i=i, frm=n, to=to, span=[m.start(1), m.end(1)]); P = S; a_, b_ = n, to
    else: raise ValueError(kind)
    gold = " ".join(apply_edit(P, edit))
    return dict(kind="literal", source="editing_82d4", task="edit_" + kind, position=where, inserted=g, sents=P, edit=edit,
                prompt=EDIT_INSTR[kind][wording].format(a=a_, b=b_) + "\n\n" + " ".join(P), gold=gold)


def edit_gold(e):
    """An editing example's answer, recomputed from its sentences and its edit."""
    assert e["prompt"].split("\n\n", 1)[1] == " ".join(e["sents"]), "the prompt's text is not the example's sentences"
    return " ".join(apply_edit(e["sents"], e["edit"]))


# ---- translation ----
LANGS = ("French", "Spanish", "German", "Italian", "Portuguese")
LCODE = {"French": "fr", "Spanish": "es", "German": "de", "Italian": "it", "Portuguese": "pt"}
TR_INSTR = ["Put the following text into {L}.", "Write this passage in {L}.", "Give a {L} version of the text below."]
PART_INSTR = "Translate the following text into {L}. Reply with the translation only."           # the base model's prompt for a part (never a training prompt)


def translation_item(sents, g, where, lang, wording):
    """A translation example without its answer: the prompt and the three parts the base model translates on their own."""
    S = place(sents, g, where); gi = g_index(len(sents), where)
    return dict(kind="literal", source="translation_82d4", task="translate", lang=lang, position=where, inserted=g, sents=S,
                parts=[" ".join(S[:gi]), g, " ".join(S[gi + 1:])], prompt=TR_INSTR[wording].format(L=lang) + "\n\n" + " ".join(S))


def part_prompt(text, lang): return PART_INSTR.format(L=lang) + "\n\n" + text
def join_parts(parts): return " ".join(p.strip() for p in parts if p and p.strip())
QUOTES = "\"“”«»'"
PREAMBLE = re.compile(r"^(here is|here's|here are|sure|certainly|of course|the translation|translation|translated text|traduction|traducci[oó]n|[uü]bersetzung|traduzione|tradu[cç][aã]o"
                      r"|voici|voil[aà]|aqu[ií] (est[aá]|tienes)|hier (ist|sind)|ecco|aqui (est[aá]|vai))\b", re.I)
NOTE = re.compile(r"\((note|nota|remarque|anmerkung|hinweis|n\.b\.)\b|\b(note|nota|remarque|anmerkung|hinweis)\s*:", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")


def part_reply(src, reply):
    """A part's translation as it joins the answer: the reply without quotes around it that the source does not have."""
    r = (reply or "").strip()
    if len(r) >= 2 and r[0] in QUOTES and r[-1] in QUOTES and not (src.strip()[:1] in QUOTES and src.strip()[-1:] in QUOTES): r = r[1:-1].strip()
    return r


def part_problem(src, reply):
    """Why a part's translation cannot join an answer (None: it can): empty, a second line, a preamble or a label, an
    added note, another number of sentences than the source, or a length out of 0.5 to 2.5 times the source's."""
    r = (reply or "").strip(); s = (src or "").strip()
    if not r: return "empty"
    if "\n" in r: return "a second line"
    if PREAMBLE.match(r) and not PREAMBLE.match(s): return "a preamble"
    if NOTE.search(r) and not NOTE.search(s): return "an added note"
    if len([x for x in _SENT.split(r) if x]) != len([x for x in _SENT.split(s) if x]): return "another number of sentences"
    if not 0.5 <= len(r) / max(1, len(s)) <= 2.5: return "too short or too long"
    return None
