"""DefensiveToken (Chen, Wang, Carlini, Sitawarin and Wagner, "Defending Against Prompt Injection With a Few
DefensiveTokens", AISec 2025; github.com/Sizhe-Chen/DefensiveToken), installed as its authors release it (notebook 79).

The release is five embedding vectors per model (defensivetokens.json) and a setup script (setup.py). The script adds
five special tokens [DefensiveToken0] ... [DefensiveToken4] to the tokenizer, resizes the model's embeddings to the
tokenizer's length, writes the five vectors into the last five rows, and sets a chat template that puts the five tokens
before everything else. The authors' instructions (README, demo.py): the trusted instruction goes in the system role,
the untrusted data in the user role, and the special tokens are removed from the data (demo.py's recursive_filter over
tokenizer.all_special_tokens). The model's weights are not changed.

This module does exactly that in memory, from the release pinned by commit and by the hash of the vectors file. The
templates are read from the pinned setup.py itself, not retyped. One change renders identically: the template's
switch is on by default, so every apply_chat_template call adds the tokens unless add_defensive_tokens=False is
passed; check_templates() proves, on the prompts it is given, that the default-on template renders exactly what the
released template renders with add_defensive_tokens=True, and with False. As every condition of the paper, the
document also passes this project's own special-token filter for its model family (manual_attacks.filter_special),
which removes the chat markers the release's filter does not list; the two filters are applied until neither changes
the text."""
from __future__ import annotations
import ast, hashlib, json, os, subprocess

REPO_URL = "https://github.com/Sizhe-Chen/DefensiveToken.git"
COMMIT = "d45cc0072d72e069a67b674065173822338c104f"
TOKENS_SHA1 = "4f538fa0152a7dd14470489796658726fd2b21d5"      # sha1 of defensivetokens.json at COMMIT
NAMES = [f"[DefensiveToken{i}]" for i in range(5)]
SWITCH = "{%- if add_defensive_tokens %}"
SWITCH_ON = "{%- if add_defensive_tokens is not defined or add_defensive_tokens %}"
MAX_LENGTH = 3072                                               # llama_h2h.generate_messages' truncation limit


def release(dest="data/defensivetoken"):
    """Clone the release at COMMIT; return (vectors, templates): the five vectors per model and setup.py's
    chat_templates, parsed from the file (ast.literal_eval of its dictionary)."""
    if not os.path.exists(os.path.join(dest, ".git")): subprocess.run(["git", "clone", "-q", REPO_URL, dest], check=True)
    if subprocess.run(["git", "-C", dest, "cat-file", "-e", COMMIT + "^{commit}"]).returncode != 0:
        subprocess.run(["git", "-C", dest, "fetch", "-q", "origin"], check=True)
    subprocess.run(["git", "-C", dest, "checkout", "-q", COMMIT], check=True)
    raw = open(os.path.join(dest, "defensivetokens.json"), "rb").read()
    assert hashlib.sha1(raw).hexdigest() == TOKENS_SHA1, "defensivetokens.json is not the pinned release: stop"
    vectors = json.loads(raw); templates = None
    for node in ast.walk(ast.parse(open(os.path.join(dest, "setup.py")).read())):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "chat_templates" for t in node.targets):
            templates = ast.literal_eval(node.value)
    assert templates, "setup.py has no chat_templates dictionary: stop"
    for k, v in vectors.items(): assert len(v) == 5 and k in templates, f"the release has no five vectors and template for {k}: stop"
    return vectors, templates


def default_on(template):
    assert template.count(SWITCH) == 1, "the released template does not have exactly one defensive-token switch: stop"
    return template.replace(SWITCH, SWITCH_ON)


def add_tokens(tok, template):
    """setup.py's tokenizer step: the five special tokens, then the chat template (default on). Returns their ids."""
    n_new = tok.add_special_tokens({"additional_special_tokens": NAMES})
    assert n_new == 5, f"{n_new} defensive tokens added, not 5: stop"
    if tok.pad_token is None: tok.pad_token = tok.eos_token
    tok.chat_template = default_on(template)
    ids = tok.convert_tokens_to_ids(NAMES)
    assert ids == list(range(len(tok) - 5, len(tok))), "the defensive tokens are not the tokenizer's last five ids: stop"
    return ids


def install(model, tok, vectors):
    """setup.py's model step: resize the embeddings to the tokenizer's length and write the five vectors into the
    last five rows. Returns the largest absolute difference between the rows and the released vectors cast to the
    model's precision (0 when installed as released)."""
    import numpy as np, torch
    vec = torch.tensor(np.array(vectors))
    model.resize_token_embeddings(len(tok))
    W = model.get_input_embeddings().weight
    with torch.no_grad():
        for i in range(5): W.data[-5 + i] = vec[i].to(W.dtype).to(W.device)
    return float((W.data[-5:].float().cpu() - vec.to(W.dtype).float()).abs().max())


def load(base, vectors, templates):
    """The base model in bf16 with the release installed. Returns (model, tokenizer, largest row difference)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(base)
    model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.bfloat16, device_map="auto").eval()
    add_tokens(tok, templates[base])
    diff = install(model, tok, vectors[base])
    return model, tok, diff


def filter_data(text, tok, family):
    """demo.py's recursive_filter over tokenizer.all_special_tokens, and the project's filter for the model family,
    applied until neither changes the text."""
    from manual_attacks import filter_special
    specials = [s for s in tok.all_special_tokens if s]
    while True:
        new = text
        for s in specials: new = new.replace(s, "")
        new = filter_special(new, family)
        if new == text: return text
        text = new


def split_prompt(prompt):
    """The project's task prompts are '<instruction>\\n\\n<data>' (llama_h2h.split_prompt)."""
    from llama_h2h import split_prompt as sp
    instr, data = sp(prompt)
    assert data is not None, "a prompt without a data part has no place in the DefensiveToken layout: stop"
    return instr, data


def messages(prompt, tok, family):
    """The authors' layout: the trusted instruction in the system role, the filtered data in the user role."""
    instr, data = split_prompt(prompt)
    return [{"role": "system", "content": instr}, {"role": "user", "content": filter_data(data, tok, family)}]


def messages_split(instruction, data, tok, family):
    return [{"role": "system", "content": instruction}, {"role": "user", "content": filter_data(data, tok, family)}]


def render(convs, tok, tokens=True):
    return [tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True, add_defensive_tokens=tokens) for m in convs]


def check_templates(tok, released_template, prompts, family):
    """The default-on template renders exactly the released template's text, with the tokens and without; with them,
    the text begins with the five tokens. Returns the number of prompts checked."""
    on = tok.chat_template
    for p in prompts:
        m = messages(p, tok, family)
        tok.chat_template = released_template
        want_on = tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True, add_defensive_tokens=True)
        want_off = tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True, add_defensive_tokens=False)
        tok.chat_template = on
        got_default = tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True)
        got_off = tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True, add_defensive_tokens=False)
        assert got_default == want_on and got_off == want_off, "the default-on template does not render as the released one: stop"
        assert want_on.startswith("".join(NAMES)) and not want_off.startswith(NAMES[0]), "the defensive tokens are not placed first: stop"
    return len(prompts)


def generate(model, tok, prompts, family, max_new_tokens=160, batch_size=8, tokens=True, show_every=400, convs=None):
    """Greedy generation in the DefensiveToken layout: llama_h2h.generate_messages with the switch passed on (left
    padding, no special tokens added again, truncation at 3,072 tokens, special tokens skipped in the decoded reply)."""
    import torch
    convs = convs if convs is not None else [messages(p, tok, family) for p in prompts]
    tok.padding_side = "left"; outs = []
    for i in range(0, len(convs), batch_size):
        texts = render(convs[i:i + batch_size], tok, tokens)
        enc = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=MAX_LENGTH, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, temperature=None, top_p=None, pad_token_id=tok.pad_token_id)
        outs += [tok.decode(g[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip() for g in gen]
        if show_every and (i // batch_size) % max(1, show_every // batch_size) == 0: print(f"  generated {min(i + batch_size, len(convs))}/{len(convs)}")
    return outs


def harness(tok, family, task_user):
    """gcg_attack's Harness for the DefensiveToken layout: the same path a document takes to the model in generate()
    (the family filter, the summary task, the two-role layout, the default-on template, the tokenizer call)."""
    from gcg_attack import Harness, INIT, PH
    from manual_attacks import filter_special

    class DTHarness(Harness):
        def render(self, doc):
            return self.tok.apply_chat_template(messages(self.prompt(doc), self.tok, self.family), tokenize=False, add_generation_prompt=True)

        def unchanged(self, doc):
            return filter_special(doc, self.family) == doc and filter_data(doc, self.tok, self.family) == doc

        def split(self, host):
            """Harness.split for a template that puts a line break right after the document. Qwen's and Llama 3's
            tokenizers join punctuation at the end of a piece of text with the line breaks that follow it, so the last
            token of the initial suffix (twenty " !") merges with the template's line break and the initial suffix does
            not survive the round trip on its own. The prompt is split exactly as Harness.split splits it; the round
            trip is checked with the suffix's last token replaced by a letter token, which cannot merge with the line
            break. GCG.valid and GCG.exact already keep only candidates that re-tokenize to themselves in context, so a
            suffix whose last token would merge is never kept; the initial suffix stays the search's starting point, as
            in every other condition."""
            r = self.render(self.doc(host, PH)); assert r.count(PH) == 1, "the suffix slot is not rendered exactly once"
            before, after = r.split(PH)
            bi, si, ai = self.ids([before])[0], self.tok(INIT, add_special_tokens=False)["input_ids"], self.tok(after, add_special_tokens=False)["input_ids"]
            assert len(si) == 20, f"the initial suffix is {len(si)} tokens, not 20"
            assert self.render(self.doc(host, INIT)) == before + INIT + after, "the prompt does not split cleanly around the suffix"
            probe = INIT[:-2] + " a"; pi = self.tok(probe, add_special_tokens=False)["input_ids"]
            assert len(pi) == 20 and pi[:19] == si[:19], "the probe suffix does not tokenize as the initial suffix with one letter token at the end"
            assert self.ids([self.render(self.doc(host, probe))])[0] == bi + pi + ai, "the prompt does not split cleanly around a suffix ending in a letter"
            assert len(bi) + len(si) + len(ai) + 8 < self.max_length, "the prompt could be cut by the generation code"
            return before, after, bi, si, ai

    h = DTHarness(tok, "dt", family, task_user, None, None, filter_special, None)
    assert h.max_length == MAX_LENGTH and h.add_special is False
    return h
