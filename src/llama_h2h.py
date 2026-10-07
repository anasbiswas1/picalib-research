"""Head-to-head on Llama-3.1-8B-Instruct: loading in bf16, Hugging Face authentication without printing the token,
prompts in two formats (one user turn, or the trusted instruction in the user role and the untrusted data in the
"input" role that Meta-SecAlign was trained with), batched generation from full message lists, and IFEval scored with
Google's official code fetched at a pinned commit."""
from __future__ import annotations
import os, sys, json, getpass, urllib.request

BASE = "meta-llama/Llama-3.1-8B-Instruct"
SECALIGN = "facebook/Meta-SecAlign-8B"
IFEVAL_COMMIT = "e49bbfe381c9c0e564b937f1c4e163a2273c65cc"     # google-research/google-research, pinned for reproducibility
IFEVAL_FILES = ("instructions.py", "instructions_registry.py", "instructions_util.py", "evaluation_lib.py", "data/input_data.jsonl")


def hf_login():
    """Read HF_TOKEN from Colab Secrets if present, otherwise ask for it in a hidden prompt. Never prints the token."""
    tok = None
    try:
        from google.colab import userdata
        tok = userdata.get("HF_TOKEN")
    except Exception:
        tok = None
    if not tok: tok = getpass.getpass("Hugging Face token (read access; it is not shown or saved in the notebook): ")
    os.environ["HF_TOKEN"] = tok
    from huggingface_hub import login
    login(token=tok, add_to_git_credential=False)
    return True


def load_llama(adapter=None, tokenizer_from=None, train=False):
    """bf16 Llama-3.1-8B-Instruct, optionally with a LoRA adapter. tokenizer_from lets Meta-SecAlign use its own
    tokenizer, whose chat template defines the input role."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(tokenizer_from or BASE)
    if tok.pad_token is None: tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="auto")
    if train:
        model.gradient_checkpointing_enable(); model.enable_input_require_grads(); model.config.use_cache = False
    else: model.eval()
    if adapter is not None:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter, is_trainable=train)
        if not train: model.eval()
    return model, tok


def split_prompt(prompt):
    """Trusted instruction and untrusted data. Every task prompt in this project is '<instruction>\\n\\n<data>', with an
    optional 'Input:\\n' label before the data (the Alpaca format)."""
    instr, sep, data = prompt.partition("\n\n")
    if not sep: return prompt, None
    if data.startswith("Input:\n"): data = data[len("Input:\n"):]
    return instr, data


def recursive_filter(s, filters=("<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>", "<|begin_of_text|>")):
    """Exactly the filter in Meta-SecAlign's demo.py: the untrusted part may not contain the special delimiters."""
    orig = s
    for f in filters: s = s.replace(f, "")
    return recursive_filter(s, filters) if s != orig else s


def messages_for(prompt, mode, system=None):
    """mode 'plain': one user turn. mode 'input_role': trusted instruction in the user role, filtered data in the input
    role, as Meta-SecAlign specifies (a trusted system prompt is allowed first)."""
    head = [{"role": "system", "content": system}] if system else []
    if mode == "plain": return head + [{"role": "user", "content": prompt}]
    instr, data = split_prompt(prompt)
    if data is None: return head + [{"role": "user", "content": instr}]
    return head + [{"role": "user", "content": instr}, {"role": "input", "content": recursive_filter(data)}]


def check_input_role_template(tok):
    """Render a two-role conversation and confirm the template really emits an input header."""
    text = tok.apply_chat_template(messages_for("Summarize this.\n\nSome data.", "input_role", "sys"), tokenize=False, add_generation_prompt=True)
    assert "<|start_header_id|>input<|end_header_id|>" in text, "this tokenizer's chat template has no input role"
    return text


def generate_messages(model, tok, conversations, max_new_tokens=160, batch_size=8, show_every=160):
    """Greedy generation for a list of message lists (left padding)."""
    import torch
    tok.padding_side = "left"; outs = []
    for i in range(0, len(conversations), batch_size):
        chunk = conversations[i:i + batch_size]
        texts = [tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in chunk]
        enc = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=3072, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, temperature=None, top_p=None, pad_token_id=tok.pad_token_id)
        outs += [tok.decode(g[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip() for g in gen]
        if (i // batch_size) % max(1, show_every // batch_size) == 0: print(f"  generated {min(i + batch_size, len(conversations))}/{len(conversations)}")
    return outs


def setup_ifeval(dest="data/ifeval"):
    """Fetch Google's IFEval scoring code and its 541 prompts at the pinned commit (Apache 2.0, licence header kept).
    They go under data/, which git ignores: the pinned commit makes them reproducible without redistributing them."""
    pkg = os.path.join(dest, "instruction_following_eval"); os.makedirs(os.path.join(pkg, "data"), exist_ok=True)
    open(os.path.join(pkg, "__init__.py"), "a").close()
    for f in IFEVAL_FILES:
        out = os.path.join(pkg, f)
        if not os.path.exists(out):
            urllib.request.urlretrieve(f"https://raw.githubusercontent.com/google-research/google-research/{IFEVAL_COMMIT}/instruction_following_eval/{f}", out)
    import nltk; nltk.download("punkt", quiet=True); nltk.download("punkt_tab", quiet=True)
    if dest not in sys.path: sys.path.insert(0, dest)
    from instruction_following_eval import evaluation_lib, instructions_util
    try: instructions_util._get_sentence_tokenizer()                       # IFEval loads the English Punkt model in its old format
    except Exception:                                                       # some NLTK versions refuse that format; the same model in the newer format
        from nltk.tokenize.punkt import PunktTokenizer                      # splits sentences identically
        _tok = PunktTokenizer("english"); instructions_util._get_sentence_tokenizer = lambda: _tok
        print("IFEval: using the English Punkt model in NLTK's newer format")
    return evaluation_lib, evaluation_lib.read_prompt_list(os.path.join(pkg, "data", "input_data.jsonl"))


def score_ifeval(evaluation_lib, inputs, prompt_to_response):
    """The four standard IFEval numbers, and per-prompt strict results for paired tests. The language checks inside
    IFEval use langdetect, which is randomized unless seeded, and some checks draw random defaults; both are seeded at
    every call so identical responses always receive identical scores."""
    import random, langdetect
    langdetect.DetectorFactory.seed = 0; random.seed(0)
    strict = [evaluation_lib.test_instruction_following_strict(i, prompt_to_response) for i in inputs]
    loose = [evaluation_lib.test_instruction_following_loose(i, prompt_to_response) for i in inputs]
    pl = lambda o: sum(x.follow_all_instructions for x in o) / len(o)
    il = lambda o: sum(sum(x.follow_instruction_list) for x in o) / sum(len(x.follow_instruction_list) for x in o)
    return dict(prompt_strict=pl(strict), instruction_strict=il(strict), prompt_loose=pl(loose), instruction_loose=il(loose)), [float(x.follow_all_instructions) for x in strict]


def sample_rollouts_chat(model, tok, prompts, system, max_new_tokens=128, temperature=1.0):
    """twin_distill.sample_rollouts with one difference: the chat text is tokenized without adding special tokens
    again. Llama's chat template already begins with its begin-of-text token, so the default would double it for
    the rollouts while response_logprobs (correctly) does not. Qwen's tokenizer adds none, so the Qwen runs were
    unaffected."""
    import torch
    from twin_distill import _chat
    was_training = model.training; model.eval(); tok.padding_side = "left"
    enc = tok([_chat(tok, system, p) for p in prompts], return_tensors="pt", padding=True, truncation=True, max_length=1024, add_special_tokens=False).to(model.device)
    with torch.no_grad():
        gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=True, temperature=temperature, top_p=1.0, pad_token_id=tok.pad_token_id, use_cache=True)
    outs = [tok.decode(gen[j][enc["input_ids"].shape[1]:], skip_special_tokens=True).strip() for j in range(len(prompts))]
    if was_training: model.train()
    return outs


def train_phase(EX, out_adapter, workdir, system, init_adapter=None, lam=0.3, B=4, LOG=10, CKPT=50, MAXNEW=128, lr=2e-5):
    """One training phase of the recipe on Llama: attacked and twin examples by on-policy distillation toward the
    same model with the adapter off; literal examples by the exact-target loss (weight lam). Checkpoints every CKPT
    batches and resumes from workdir/progress.json. Settings match the Qwen runs."""
    import shutil, numpy as np, torch
    from peft import LoraConfig, get_peft_model, PeftModel
    from twin_distill import response_logprobs, distill_loss
    from literal_tasks import sft_loss
    os.makedirs(workdir, exist_ok=True); PROG = os.path.join(workdir, "progress.json"); LOGF = os.path.join(workdir, "train_log.json")
    start = json.load(open(PROG))["step"] if os.path.exists(PROG) else 0
    if start >= len(EX) and os.path.exists(os.path.join(out_adapter, "adapter_config.json")): print("phase complete:", out_adapter); return
    base, tok = load_llama(train=True)
    if os.path.exists(os.path.join(out_adapter, "adapter_config.json")):
        model = PeftModel.from_pretrained(base, out_adapter, is_trainable=True); print("resuming from example", start)
    elif init_adapter is not None:
        shutil.copytree(init_adapter, out_adapter); model = PeftModel.from_pretrained(base, out_adapter, is_trainable=True); start = 0; print("initialised from", init_adapter)
    else:
        cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"], task_type="CAUSAL_LM")
        model = get_peft_model(base, cfg); start = 0; print("new adapter")
    model.print_trainable_parameters()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0); model.train()
    log = json.load(open(LOGF)) if start > 0 and os.path.exists(LOGF) else []
    for step in range(start, len(EX), B):
        batch = EX[step: step + B]; dist = [e for e in batch if e["kind"] != "literal"]; lit = [e for e in batch if e["kind"] == "literal"]
        terms, rec = [], dict(step=step, kl=None, sft=None)
        if dist:
            roll = sample_rollouts_chat(model, tok, [e["student"] for e in dist], system, max_new_tokens=MAXNEW)
            keep = [i for i, r in enumerate(roll) if len(r) >= 5]
            if keep:
                dk = [dist[i] for i in keep]; rk = [roll[i] for i in keep]
                lp_s = response_logprobs(model, tok, [e["student"] for e in dk], rk, system)
                with torch.no_grad(), model.disable_adapter():
                    lp_t = response_logprobs(model, tok, [e["teacher"] for e in dk], rk, system)
                dl, kl = distill_loss(lp_s, lp_t); terms.append(dl); rec["kl"] = kl
        if lit:
            sl = sft_loss(response_logprobs(model, tok, [e["prompt"] for e in lit], [e["gold"] for e in lit], system)); terms.append(lam * sl); rec["sft"] = float(sl)
        if terms:
            loss = terms[0] if len(terms) == 1 else terms[0] + terms[1]; loss.backward()
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0); opt.step(); opt.zero_grad(); log.append(rec)
            del loss, terms; torch.cuda.empty_cache()
        nb = step // B
        if nb % LOG == 0 and log:
            r = log[-LOG:]; kls = [x["kl"] for x in r if x["kl"] is not None]; sfts = [x["sft"] for x in r if x["sft"] is not None]
            print(f"  {step + len(batch)}/{len(EX)}  reverse-KL {np.mean(kls) if kls else float('nan'):.3f}  exact-target loss {np.mean(sfts) if sfts else float('nan'):.3f}")
        if nb % CKPT == CKPT - 1:
            model.save_pretrained(out_adapter); json.dump(dict(step=step + B), open(PROG, "w")); json.dump(log, open(LOGF, "w"))
    model.save_pretrained(out_adapter); json.dump(dict(step=len(EX)), open(PROG, "w")); json.dump(log, open(LOGF, "w")); print("adapter saved:", out_adapter)
    del model, base; import gc; gc.collect(); torch.cuda.empty_cache()
