"""Adversarial twin distillation (notebook 82): twin distillation on documents whose end an attacker has written.

Two attackers, both restricted to the end of the document in the input turn. The forged onset: a reply opening (a
word such as "Output:" or "Summary:") followed by the compliance onset, the first tokens of the base model's reply when
the user asks for the injected instruction, after the prefix it shares with the clean reply is removed. The live pool:
suffixes of twenty tokens that GCG (src/gcg_attack.py, the project's implementation, with a smaller candidate batch)
keeps optimising against the model as it trains, each on its own triplet, with the compliance onset as the target and
the test-time filters. The training step is src/qwen_role.py's (on-policy reverse-KL distillation towards the same
model with the adapter off, the twins, the literal tasks); the pool adds two attacked prompts to every batch."""
from __future__ import annotations
import os, json, shutil, hashlib, time
import numpy as np
import torch
from gcg_attack import Harness, GCG, INIT, kv_of
from qwen_role import messages_q, chat_q, qwen_filter, patch_template, INPUT_HEADER
from manual_attacks import filter_special

FORMS = ["Output:", "Summary:", "Response:", "Answer:", "Assistant:", "Here is the summary:", "Here is the result:", "Key information:",
         "Result:", "```", "Okay.", "Sure.", "### Output", "Final answer:", "Output =", "Response =", "Begin:", "Start of reply:"]
GLUE = ["!", "::", "->", "=>", "##", "**", "--", "\"\"\"", "//", "';"]


def parse_triplet(e):
    """An attacked example whose injection sits at the start or the end of the data -> the triplet it was built from
    (instruction, data label, clean data, injected data, injected instruction g, where). None if g cannot be read back
    exactly (a mid-document or fake-completion injection) or the instruction holds a blank line."""
    si, sep, sd = e["student"].partition("\n\n"); ti, _, td = e["teacher"].partition("\n\n")
    if not sep or si != ti or not sd.strip() or not td.strip(): return None
    label = "Input:\n" if sd.startswith("Input:\n") else ""
    if td.startswith("Input:\n") != bool(label): return None
    sd, td = sd[len(label):], td[len(label):]
    for where in ("end", "start"):
        core = td.rstrip() if where == "end" else td
        if where == "end" and sd.startswith(core): g = sd[len(core):]
        elif where == "start" and sd.endswith(core): g = sd[: len(sd) - len(core)]
        else: continue
        g = g.strip()
        if g and "\n" not in g and len(g) >= 8: return dict(instr=si, label=label, clean=td, injected=sd, g=g, where=where)
    return None


def twin_prompt(t): return f"{t['instr']} {t['g']}\n\n{t['label']}{t['clean']}"
def clean_prompt(t): return f"{t['instr']}\n\n{t['label']}{t['clean']}"
def attacked_prompt(t, tail=""): return f"{t['instr']}\n\n{t['label']}{t['injected']}{tail}"


@torch.no_grad()
def greedy_ids(model, tok, prompts, system, k=16, bs=16):
    """The first k tokens of the greedy reply to each prompt in the two-role format, as token ids (the generation code's
    decoding: generate with do_sample=False, left padding)."""
    was_training = model.training; model.eval(); tok.padding_side = "left"; out = []
    stop = {tok.eos_token_id, tok.pad_token_id} | set(tok.convert_tokens_to_ids(["<|im_end|>", "<|endoftext|>"]))
    for i in range(0, len(prompts), bs):
        enc = tok([chat_q(tok, system, p) for p in prompts[i:i + bs]], return_tensors="pt", padding=True, truncation=True, max_length=2048, add_special_tokens=False).to(model.device)
        gen = model.generate(**enc, max_new_tokens=k, do_sample=False, temperature=None, top_p=None, pad_token_id=tok.pad_token_id)
        for g in gen:
            ids = g[enc["input_ids"].shape[1]:].tolist(); cut = next((j for j, x in enumerate(ids) if x in stop), len(ids)); out.append(ids[:cut])
    if was_training: model.train()
    return out


def onset_of(yc, yg, k):
    """The compliance onset: the first k tokens of the compliance reply after the prefix it shares with the clean reply.
    Returns (ids or None, length of the shared prefix)."""
    c = 0
    while c < min(len(yc), len(yg)) and yc[c] == yg[c]: c += 1
    rest = yg[c: c + k]
    return (rest if len(rest) == k else None), c


def forged_tail(rng, onset_text):
    """A hand-built forged opening: a reply form, sometimes with glue tokens, then the compliance onset."""
    f = FORMS[int(rng.integers(len(FORMS)))]; sep = "\n" if rng.random() < 0.5 else " "
    if rng.random() < 0.4: f = GLUE[int(rng.integers(len(GLUE)))] + " " + f
    if rng.random() < 0.3: f = f + " " + GLUE[int(rng.integers(len(GLUE)))]
    return sep + f + " " + onset_text.strip()


class EntryHarness(Harness):
    """GCG's harness for one training triplet: the instruction in the user turn, the injected data with the suffix at
    its end in the input turn, the training system prompt, the test-time filters."""
    def __init__(self, tok, instr, label, system):
        super().__init__(tok, "input_role", "qwen", None, system, messages_q, filter_special, qwen_filter); self.instr, self.label = instr, label
    def doc(self, host, suffix): return host + suffix
    def prompt(self, doc): return f"{self.instr}\n\n{self.label}{self.filter_special(doc, self.family)}"


class PoolAttacker:
    """GCG steps on a pool entry against the current model: the project's gradient, candidate filters, cached losses and
    exact re-tokenisation check, with n candidates drawn from the top-k tokens per position."""
    def __init__(self, model, tok, system, bad, n=128, topk=256, mini=64, seed=0):
        self.model, self.tok, self.system, self.bad, self.n, self.topk, self.mini = model, tok, system, bad, n, topk, mini
        self.gen = torch.Generator().manual_seed(seed)

    def sample(self, a, suffix, g):
        L = suffix.shape[1]; g = g.clone(); g[:, self.bad] = float("inf")
        top = (-g).topk(self.topk, dim=1).indices.cpu(); pos = torch.arange(0, L, L / self.n).long()[:self.n]
        perm = torch.argsort(torch.rand((L, self.topk), generator=self.gen), dim=1)
        pick = torch.cat([perm[i, :int((pos == i).sum())] for i in range(L)])
        cands = suffix.cpu().repeat(self.n, 1); cands[torch.arange(self.n), pos] = top[pos, pick]
        return cands.to(a.dev)

    def steps(self, entry, m, tau):
        """m GCG steps on the entry's suffix; updates the entry (suffix, loss, steps, won) and returns its student
        prompt string, which renders to exactly the optimised tokens."""
        was_training = self.model.training; self.model.eval()
        h = EntryHarness(self.tok, entry["instr"], entry["label"], self.system); a = GCG(self.model, h, self.bad, self.mini)
        a.target = torch.tensor([entry["onset_ids"]], device=a.dev)
        host = entry["injected"]; before, after_text, bi, si, ai = h.split(host)
        after = torch.tensor([ai], device=a.dev)
        if entry.get("suffix_ids"): suffix, text = torch.tensor([entry["suffix_ids"]], device=a.dev), entry["suffix"]
        else: suffix, text = torch.tensor([si], device=a.dev), INIT
        with torch.no_grad():
            out = self.model(input_ids=torch.tensor([bi], device=a.dev), use_cache=True); kv = kv_of(out.past_key_values)
            a.base = torch.zeros(out.logits.shape[-1], dtype=torch.bool, device=a.dev); a.base[torch.tensor(bi + ai, device=a.dev)] = True; out = None
            loss_now = float(a.losses(kv, suffix, after)[0])
        entry["loss_before"] = round(loss_now, 4); t0 = time.time()
        for _ in range(m):
            g = a.grad(kv, suffix, after)
            if not torch.isfinite(g).all(): entry["nonfinite_grad"] = entry.get("nonfinite_grad", 0) + 1; g = torch.nan_to_num(g, nan=0.0, posinf=0.0, neginf=0.0)
            cands = self.sample(a, suffix, g); ok, texts = a.valid(host, before, after_text, bi, ai, cands)
            if not ok: entry["no_valid"] = entry.get("no_valid", 0) + 1; continue
            loss = a.losses(kv, cands[ok], after); chosen = None
            for j in torch.argsort(loss).tolist():
                c = cands[ok[j]]
                if a.exact(host, texts[ok[j]], bi + c.tolist() + ai): chosen = (c, texts[ok[j]], float(loss[j])); break
            if chosen is None: entry["render_mismatch"] = entry.get("render_mismatch", 0) + 1; continue
            suffix, text, loss_now = chosen[0].unsqueeze(0), chosen[1], chosen[2]; entry["steps"] = entry.get("steps", 0) + 1
        assert a.exact(host, text, bi + suffix[0].tolist() + ai), "the pool suffix no longer renders to the optimised tokens"
        entry.update(suffix_ids=suffix[0].tolist(), suffix=text, loss=round(loss_now, 4), won=loss_now < tau, seconds=round(time.time() - t0, 2))
        student = h.prompt(h.doc(host, text)); kv = None
        if was_training: self.model.train()
        return student


def new_entry(src, k_id):
    e = dict(src); e.update(id=k_id, suffix_ids=None, suffix=None, steps=0, loss=None, won=False, won_before=False, draws=0); return e


def check_rendering(tok, system, student, tail):
    """The tail (a forged opening or a pool suffix) is rendered inside the input turn, after the document and before the
    assistant header; nothing of it reaches the user turn."""
    r = chat_q(tok, system, student); i_in, i_t, i_as = r.find(INPUT_HEADER), r.rfind(tail.strip()[-20:]), r.rfind("<|im_start|>assistant")
    return 0 <= i_in < i_t < i_as and r.count(INPUT_HEADER) == 1


def train_atd(EX, pool_src, out_adapter, workdir, model_name, system, torch_seed, init_adapter, probe_prompts, cfg, lam=0.3, B=4, LOG=20, CKPT=100, MAXNEW=128, lr=2e-5, min_chars=0):
    """qwen_role.train_phase_all_q with the live pool: every batch, n_p pool entries get m GCG steps against the current
    model and join the batch as attacked examples (teacher: the clean prompt). An entry that has won (loss on the
    compliance onset below tau) is used once more at its next draw and then reset to the next source triplet; every L
    batches a random fifth of the pool is reset. The pool and its log are checkpointed with the adapter and resume."""
    import gc
    from peft import PeftModel, LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from targets import load_lm
    from twin_distill import distill_loss
    from literal_tasks import sft_loss
    from qwen_role import sample_rollouts_q, response_logprobs_q, LORA
    from gcg_attack import not_allowed
    os.makedirs(workdir, exist_ok=True); PROG = os.path.join(workdir, "progress.json"); LOGF = os.path.join(workdir, "train_log.json"); POOLF = os.path.join(workdir, "pool.json"); PLOGF = os.path.join(workdir, "pool_log.json")
    have = os.path.exists(os.path.join(out_adapter, "adapter_config.json"))
    start = json.load(open(PROG))["step"] if (have and os.path.exists(PROG)) else 0
    if have and start >= len(EX): print("phase complete:", out_adapter); return
    base, tok = load_lm(model_name, four_bit=True); patch_template(tok, probe_prompts, system); base = prepare_model_for_kbit_training(base)
    assert INPUT_HEADER in chat_q(tok, system, "Do the task.\n\nInput:\nsome data"), "the training tokenizer does not render the input role: stop"
    if have:
        print("resuming from example", start); model = PeftModel.from_pretrained(base, out_adapter, is_trainable=True)
    elif init_adapter is not None:
        shutil.copytree(init_adapter, out_adapter, dirs_exist_ok=True); start = 0; print("initialised from", init_adapter)
        model = PeftModel.from_pretrained(base, out_adapter, is_trainable=True)
    else:
        torch.manual_seed(torch_seed); start = 0; model = get_peft_model(base, LoraConfig(**LORA)); print("new adapter:", LORA)
    model.print_trainable_parameters()
    n_train = sum(p.numel() for p in model.parameters() if p.requires_grad); n_all = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0); model.train()
    log = json.load(open(LOGF)) if start > 0 and os.path.exists(LOGF) else []
    plog = json.load(open(PLOGF)) if start > 0 and os.path.exists(PLOGF) else []
    # ---- the pool ----
    V = model.get_input_embeddings().weight.shape[0]; bad = not_allowed(tok, V)
    att = PoolAttacker(model, tok, system, bad, n=cfg["n_cand"], topk=cfg["topk"], mini=cfg["mini"], seed=torch_seed + 7)
    if start > 0 and os.path.exists(POOLF): PS = json.load(open(POOLF)); pool, nxt = PS["pool"], PS["next"]
    else:
        pool = [new_entry(pool_src[i], i) for i in range(cfg["P"])]; nxt = cfg["P"]
        for e in pool: assert check_rendering(tok, system, attacked_prompt(e, INIT), INIT), "a pool prompt does not render the suffix inside the input turn: stop"
    def reset(e, why, step):
        nonlocal nxt
        plog.append(dict(step=step, id=e["id"], event="reset", why=why, steps=e.get("steps", 0), loss=e.get("loss"), suffix=e.get("suffix")))
        src = pool_src[nxt % len(pool_src)]; nxt += 1; ne = new_entry(src, nxt - 1)
        assert "hacked" not in ne["onset_text"].lower() and check_rendering(tok, system, attacked_prompt(ne, INIT), INIT), "a pool source is not allowed: stop"
        return ne
    # ---- the teacher must not move: its logits on a probe before and after the first update ----
    probe = tok(chat_q(tok, system, EX[0]["student"] if EX[0]["kind"] != "literal" else EX[0]["prompt"]), add_special_tokens=False, return_tensors="pt").input_ids[:, :96].to(model.device)
    def teacher_logits():
        model.eval()
        with torch.no_grad(), model.disable_adapter(): lg = model(input_ids=probe).logits[0, -1].float().cpu()
        model.train(); return lg
    t_before = teacher_logits() if start == 0 else None
    for step in range(start, len(EX), B):
        torch.manual_seed(torch_seed + step); nb = step // B
        batch = EX[step: step + B]; dist = [e for e in batch if e["kind"] != "literal"]; lit = [e for e in batch if e["kind"] == "literal"]
        # the pool's draw: round-robin, so a resumed run draws the same entries
        drawn = [pool[(nb * cfg["n_p"] + j) % cfg["P"]] for j in range(cfg["n_p"])]; pool_ex = []
        for e in drawn:
            s0 = e.get("steps", 0); student = att.steps(e, cfg["m"], cfg["tau"]); e["draws"] += 1
            pool_ex.append(dict(kind="attacked", student=student, teacher=clean_prompt(e)))
            plog.append(dict(step=step, id=e["id"], event="draw", loss_before=e["loss_before"], loss=e["loss"], steps=e["steps"], gained=e["steps"] - s0, won=bool(e["won"]), seconds=e["seconds"], suffix=e["suffix"] if e["won"] else None))
        dist = dist + pool_ex
        terms, rec = [], dict(step=step, kl=None, sft=None, kinds="".join(e["kind"][0] for e in batch) + "p" * len(pool_ex), pool_loss=[e["loss"] for e in drawn], pool_won=[bool(e["won"]) for e in drawn])
        if dist:
            roll = sample_rollouts_q(model, tok, [e["student"] for e in dist], system, max_new_tokens=MAXNEW)
            keep = [i for i, r in enumerate(roll) if len(r) >= min_chars]; rec["short"] = sum(len(r) < 20 for r in roll); rec["nroll"] = len(roll)
            if keep:
                dk = [dist[i] for i in keep]; rk = [roll[i] for i in keep]
                lp_s = response_logprobs_q(model, tok, [e["student"] for e in dk], rk, system)
                with torch.no_grad(), model.disable_adapter():
                    lp_t = response_logprobs_q(model, tok, [e["teacher"] for e in dk], rk, system)
                dl, kl = distill_loss(lp_s, lp_t); terms.append(dl); rec["kl"] = kl
        if lit:
            sl = sft_loss(response_logprobs_q(model, tok, [e["prompt"] for e in lit], [e["gold"] for e in lit], system)); terms.append(lam * sl); rec["sft"] = float(sl.detach())
        if terms:
            loss = terms[0] if len(terms) == 1 else terms[0] + terms[1]; loss.backward()
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0); opt.step(); opt.zero_grad(); log.append(rec)
            del loss, terms; torch.cuda.empty_cache()
        if t_before is not None:
            d_t = float((teacher_logits() - t_before).abs().max()); log[-1]["teacher_drift"] = round(d_t, 5); t_before = None
            assert d_t < 0.05, f"the teacher's logits moved by {d_t} after one update: the base is not frozen: stop"
        # the pool between steps
        for j, e in enumerate(drawn):
            idx = (nb * cfg["n_p"] + j) % cfg["P"]
            if e["won_before"]: pool[idx] = reset(e, "won twice", step)
            elif e["won"]: e["won_before"] = True
        if nb > 0 and nb % cfg["L"] == 0:
            rng = np.random.default_rng(torch_seed + nb)
            for idx in rng.choice(cfg["P"], max(1, cfg["P"] // 5), replace=False).tolist(): pool[idx] = reset(pool[idx], "periodic", step)
        if nb % LOG == 0 and log:
            r = log[-LOG:]; kls = [x["kl"] for x in r if x["kl"] is not None]; sfts = [x["sft"] for x in r if x["sft"] is not None]
            pw = [w for x in r for w in x.get("pool_won", [])]; pl = [l_ for x in r for l_ in x.get("pool_loss", []) if l_ is not None]
            print(f"  {step + len(batch)}/{len(EX)}  reverse-KL {np.mean(kls) if kls else float('nan'):.3f}  exact-target loss {np.mean(sfts) if sfts else float('nan'):.3f}  pool: won {np.mean(pw) if pw else float('nan'):.2f} of draws, median loss {np.median(pl) if pl else float('nan'):.2f}")
        if nb % CKPT == CKPT - 1:
            model.save_pretrained(out_adapter); json.dump(dict(step=step + B), open(PROG, "w")); json.dump(log, open(LOGF, "w"))
            json.dump(dict(pool=pool, next=nxt), open(POOLF, "w")); json.dump(plog, open(PLOGF, "w"))
    model.save_pretrained(out_adapter); json.dump(dict(step=len(EX), trainable=n_train, total=n_all), open(PROG, "w")); json.dump(log, open(LOGF, "w"))
    json.dump(dict(pool=pool, next=nxt), open(POOLF, "w")); json.dump(plog, open(PLOGF, "w")); print("adapter saved:", out_adapter)
    del model, base, opt, att; gc.collect(); torch.cuda.empty_cache()
