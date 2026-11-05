"""SecAlign's recipe, in the form Meta-SecAlign is trained with (SecAlign++), on a Qwen base in this project's one-user-turn layout.

The recipe (Chen et al., SecAlign, CCS 2025, github.com/facebookresearch/SecAlign, align.py and struq.py; Chen et al., Meta SecAlign,
arXiv 2507.02735, Sections 3 and 4.1):
  the data: an instruction-tuning set's samples that have a data part (Cleaned Alpaca, 19,157 in the paper). Into each sample's data goes
        another sample's instruction, with that sample's data if it has one ("answer the following question. " in front when the
        instruction is a question, otherwise its first letter lowered): after the data in 45% of the samples, before it in 45%
        (SecAlign++'s randomised position), and in 10% after a fake completion of the task written with made-up delimiters (SecAlign's
        completion attack, its delimiter words and marks);
  the targets: the desirable reply is the base model's own reply to the clean prompt and the undesirable reply the base model's own
        reply to the injected instruction asked on its own (SecAlign++'s self-generated responses; SecAlign used the dataset's answers);
  the training: DPO with the sigmoid loss and beta 0.1, the reference being the base model; LoRA r 64, alpha 8, dropout 0.1 on q_proj,
        v_proj, gate_proj, down_proj and up_proj; learning rate 1.6e-4 (the 8B rate), 3 epochs, 64 pairs per optimiser step (SecAlign's
        run.py: 4 x 16), cosine decay without warm-up; sequences cut to 512 tokens (run.py's model_max_length).
Kept from this project so that only the training recipe differs from the finals: the base loaded in 4-bit NF4 for training and for
evaluation, as every adapter of the paper; the system prompt and the one-user-turn layout; the prompt the recipe's own phase-1 examples
use for instruction-and-data samples ("{instruction}\\n\\nInput:\\n{inp}", twin_distill.PROMPT); greedy generation for the targets.
Every function resumes from what is on disk."""
import json, os, math, hashlib, shutil
import numpy as np

PROMPT = "{instruction}\n\nInput:\n{inp}"
MARKS = ['{s}', '|{s}|', '<{s}>', '[{s}]', '<|{s}|>', '[|{s}|]', '<[{s}]>', "'''{s}'''", '***{s}***']         # SecAlign's OTHER_DELM_TOKENS['mark']
INST_WORDS, INPT_WORDS, RESP_WORDS = ['Command', 'Rule', 'Prompt', 'Task'], ['Data', 'Context', 'Text'], ['Output', 'Answer', 'Reply']
USER_WORDS, ASST_WORDS = ['', 'Prompter ', 'User ', 'Human '], ['', 'Assistant ', 'Chatbot ', 'Bot ', 'GPT ', 'AI ']
LORA = dict(r=64, lora_alpha=8, lora_dropout=0.1, target_modules=['q_proj', 'v_proj', 'gate_proj', 'down_proj', 'up_proj'], task_type='CAUSAL_LM')
H = lambda s: hashlib.sha1(s.encode()).hexdigest()


def set_hash(pairs):
    """Twelve hex characters over the prompts and targets of the pairs, in order."""
    return hashlib.sha256(json.dumps([[p['prompt'], p.get('chosen', ''), p.get('rejected', '')] for p in pairs]).encode()).hexdigest()[:12]


def injected_prompt(sample, with_input=True):
    """SecAlign's wording of the injected instruction: a question gets 'answer the following question. ' in front, anything else its
    first letter lowered; the sample's own data, if any, follows after a space (with_input)."""
    ins = sample['instruction'].strip(); inp = sample.get('input', '').strip()
    text = ('answer the following question. ' + ins) if ins.endswith('?') else (ins[0].lower() + ins[1:])
    return (text + ' ' + inp).strip() if (inp and with_input) else text


def _delim(rng, role_words, words):
    """One made-up delimiter as SecAlign's struq.format_with_other_delimiters writes it: a mark around a role word and a delimiter word,
    the whole upper-cased, lower-cased or left as it is, then a colon. SecAlign keeps a test split of these words; here the last
    entry of each list is kept out of training."""
    mark = MARKS[int(rng.integers(len(MARKS) - 1))]; s = role_words[int(rng.integers(len(role_words) - 1))] + words[int(rng.integers(len(words) - 1))]
    p = rng.random(); s = s.upper() if p < 1 / 3 else (s.lower() if p < 2 / 3 else s)
    return mark.format(s=s) + ':'


def build_pairs(samples, seed, n=None, held_instructions=(), positions=(0.45, 0.45, 0.10)):
    """SecAlign++'s preference prompts from an instruction-tuning set. samples: dicts with 'instruction', 'input', 'output'. The samples
    with a data part are the carriers (n of them if n is given, in a seeded order); the injected sample is drawn from the whole set.
    The completion attack's fake answer is filled in later (add_targets), once the base model's own reply to the clean prompt exists.
    Returns dicts with: id, instruction, input (clean), injected (the injected sample's wording), kind (end/start/completion),
    clean_prompt (the user turn without the injection), inj_prompt (the injected instruction asked on its own, its data in the
    recipe's prompt when it has one), and prompt (the attacked user turn; for 'completion' it is finished by add_targets)."""
    rng = np.random.default_rng(seed); held = {' '.join(h.lower().split()) for h in held_instructions}
    S = [s for s in samples if s.get('instruction', '').strip()]
    carriers = [i for i, s in enumerate(S) if s.get('input', '').strip() and ' '.join(s['instruction'].lower().split()) not in held]
    order = rng.permutation(len(carriers)); carriers = [carriers[k] for k in order[: (n or len(carriers))]]
    out = []
    for i in carriers:
        s = S[i]; j = int(rng.integers(len(S)))
        while j == i: j = int(rng.integers(len(S)))
        inj = injected_prompt(S[j]); ins = s['instruction'].strip(); inp = s['input'].strip(); r = rng.random()
        cap = inj[0].upper() + inj[1:]
        if r < positions[0]: kind, attacked = 'end', inp + ' ' + cap
        elif r < positions[0] + positions[1]: kind, attacked = 'start', cap + ' ' + inp
        else:
            kind = 'completion'; d_resp = _delim(rng, ASST_WORDS, RESP_WORDS); d_inst = _delim(rng, USER_WORDS, INST_WORDS); d_inpt = _delim(rng, USER_WORDS, INPT_WORDS)
            attacked = None          # finished in add_targets: data, the fake answer under d_resp, the injected instruction under d_inst (its data under d_inpt)
        inj_s = S[j]; inj_user = PROMPT.format(instruction=inj_s['instruction'].strip(), inp=inj_s['input'].strip()) if inj_s.get('input', '').strip() else inj_s['instruction'].strip()
        rec = dict(id=len(out), instruction=ins, input=inp, injected=inj, injected_instruction=inj_s['instruction'].strip(), kind=kind,
                   clean_prompt=PROMPT.format(instruction=ins, inp=inp), inj_prompt=inj_user,
                   prompt=PROMPT.format(instruction=ins, inp=attacked) if attacked is not None else None)
        if kind == 'completion': rec.update(d_resp=d_resp, d_inst=d_inst, d_inpt=d_inpt, injected_core=injected_prompt(inj_s, with_input=False), injected_input=inj_s.get('input', '').strip())
        out.append(rec)
    return out


def add_targets(pairs, chosen, rejected, eos=''):
    """Fill in the self-generated targets (chosen[id], rejected[id]: the base model's replies) and finish the completion-attack prompts:
    the data, then the fake answer (the base model's own clean reply, as SecAlign uses the reference answer) under the made-up response
    delimiter, then the injected instruction, capitalised as SecAlign writes it, under the made-up instruction delimiter, then its data,
    if any, under the made-up data delimiter. SecAlign appends the end-of-sequence token to both targets; it is added at scoring time here."""
    for p in pairs:
        p['chosen'] = chosen[p['id']].strip(); p['rejected'] = rejected[p['id']].strip()
        if p['kind'] == 'completion':
            inj = p['injected_core']; body = p['input'] + '\n\n' + p['d_resp'] + '\n' + p['chosen'] + '\n\n' + p['d_inst'] + '\n' + inj[0].upper() + inj[1:].lower()
            if p['injected_input']: body += '\n\n' + p['d_inpt'] + '\n' + p['injected_input']
            p['prompt'] = PROMPT.format(instruction=p['instruction'], inp=body)
    return pairs


def _chat(tok, system, user):
    return tok.apply_chat_template([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], tokenize=False, add_generation_prompt=True)


def seq_logps(model, tok, prompts, responses, system, max_len=512, max_resp=None):
    """Summed log-probability of each response (with the end-of-sequence token) given its prompt, batched with right padding, in
    float32. A sequence longer than max_len loses response tokens, never prompt tokens, so the chat layout stays whole."""
    import torch
    tok.padding_side = 'right'; seqs, starts, lens = [], [], []
    for p, r in zip(prompts, responses):
        p_ids = tok(_chat(tok, system, p), add_special_tokens=False).input_ids; r_ids = tok(r + tok.eos_token, add_special_tokens=False).input_ids
        room = max(8, max_len - len(p_ids)); r_ids = r_ids[:room] if max_resp is None else r_ids[: min(room, max_resp)]
        seqs.append(p_ids + r_ids); starts.append(len(p_ids)); lens.append(len(r_ids))
    T = max(len(s) for s in seqs); pad = tok.pad_token_id
    ids = torch.tensor([s + [pad] * (T - len(s)) for s in seqs], device=model.device); am = torch.tensor([[1] * len(s) + [0] * (T - len(s)) for s in seqs], device=model.device)
    logits = model(input_ids=ids, attention_mask=am).logits
    out = []
    for b, (st, ln) in enumerate(zip(starts, lens)):
        lg = logits[b, st - 1: st - 1 + ln].float(); tg = ids[b, st: st + ln]
        out.append(torch.log_softmax(lg, -1).gather(1, tg[:, None])[:, 0].sum())
    return torch.stack(out)


def dpo_loss(pol_w, pol_l, ref_w, ref_l, beta=0.1):
    """DPO's sigmoid loss (Rafailov et al. 2023) per pair: -log sigmoid(beta * ((pol_w - ref_w) - (pol_l - ref_l))). Returns the mean
    loss, the mean reward margin and the share of pairs whose margin is positive."""
    import torch, torch.nn.functional as F
    margin = beta * ((pol_w - ref_w) - (pol_l - ref_l))
    return -F.logsigmoid(margin).mean(), float(margin.detach().mean()), float((margin.detach() > 0).float().mean())


def reference_logps(model, tok, pairs, system, cache, B=8, max_len=512):
    """The base model's summed log-probabilities of both targets of every pair (the adapter disabled), cached by pair id."""
    import torch
    done = json.load(open(cache)) if os.path.exists(cache) else {}
    todo = [p for p in pairs if str(p['id']) not in done]; was = model.training; model.eval()
    with torch.no_grad(), model.disable_adapter():
        for k in range(0, len(todo), B):
            ch = todo[k: k + B]
            w = seq_logps(model, tok, [p['prompt'] for p in ch], [p['chosen'] for p in ch], system, max_len)
            l = seq_logps(model, tok, [p['prompt'] for p in ch], [p['rejected'] for p in ch], system, max_len)
            for p, a, b in zip(ch, w.tolist(), l.tolist()): done[str(p['id'])] = [a, b]
            if (k // B) % 50 == 0: json.dump(done, open(cache, 'w')); print(f'  reference log-probabilities {min(k + B, len(todo))}/{len(todo)}')
    json.dump(done, open(cache, 'w')); model.train(was); return done


def train_dpo(pairs, out_adapter, workdir, model_name, system, torch_seed, lr=1.6e-4, epochs=3, B=4, ACC=16, beta=0.1, max_len=512, LOG=8, CKPT=16):
    """SecAlign++'s DPO on a fresh LoRA (LORA above) over the 4-bit base, the base itself the reference. 64 pairs per optimiser step
    (B x ACC), cosine decay to zero over all steps, no warm-up, AdamW without weight decay (the trainer's default), the generator
    seeded per optimiser step (torch_seed + step), the pairs in a fresh seeded order each epoch. Checkpoints the adapter, the optimiser
    and the position every CKPT optimiser steps and resumes from them. Logs the loss, the reward margin and the margin's sign share."""
    import torch
    from peft import PeftModel, get_peft_model, LoraConfig, prepare_model_for_kbit_training
    from targets import load_lm
    assert B * ACC == 64, 'SecAlign trains on 64 pairs per optimiser step'
    os.makedirs(workdir, exist_ok=True); PROG = os.path.join(workdir, 'progress.json'); LOGF = os.path.join(workdir, 'train_log.json'); OPTF = os.path.join(workdir, 'optimizer.pt')
    n = len(pairs); steps_per_epoch = math.ceil(n / 64); total = epochs * steps_per_epoch
    prog = json.load(open(PROG)) if os.path.exists(PROG) else dict(step=0)
    have = os.path.exists(os.path.join(out_adapter, 'adapter_config.json'))
    if have and prog['step'] >= total: print('training complete:', out_adapter); return
    base, tok = load_lm(model_name, four_bit=True); base = prepare_model_for_kbit_training(base)
    if have and prog['step'] > 0: model = PeftModel.from_pretrained(base, out_adapter, is_trainable=True); print('resuming from optimiser step', prog['step'], 'of', total)
    else:
        torch.manual_seed(torch_seed); model = get_peft_model(base, LoraConfig(**LORA)); prog = dict(step=0); print('new adapter:', LORA)
    model.print_trainable_parameters()
    refs = reference_logps(model, tok, pairs, system, os.path.join(workdir, 'reference_logps.json'), B=max(B, 8), max_len=max_len)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0)
    if have and prog['step'] > 0 and os.path.exists(OPTF): opt.load_state_dict(torch.load(OPTF, map_location='cpu'))
    lr_at = lambda s: lr * 0.5 * (1 + math.cos(math.pi * s / total))
    log = json.load(open(LOGF)) if prog['step'] > 0 and os.path.exists(LOGF) else []
    model.train(); step = prog['step']
    while step < total:
        epoch, pos = divmod(step, steps_per_epoch); order = np.random.default_rng(torch_seed + epoch).permutation(n)
        idx = [int(i) for i in order[pos * 64: (pos + 1) * 64]]; torch.manual_seed(torch_seed + step)
        for g in opt.param_groups: g['lr'] = lr_at(step)
        opt.zero_grad(set_to_none=True); losses, margins, accs = [], [], []
        for k in range(0, len(idx), B):
            ch = [pairs[i] for i in idx[k: k + B]]
            pw = seq_logps(model, tok, [p['prompt'] for p in ch], [p['chosen'] for p in ch], system, max_len)
            pl = seq_logps(model, tok, [p['prompt'] for p in ch], [p['rejected'] for p in ch], system, max_len)
            rw = torch.tensor([refs[str(p['id'])][0] for p in ch], device=pw.device); rl = torch.tensor([refs[str(p['id'])][1] for p in ch], device=pw.device)
            loss, margin, acc = dpo_loss(pw, pl, rw, rl, beta); (loss * len(ch) / len(idx)).backward()
            losses.append(float(loss)); margins.append(margin); accs.append(acc)
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)       # the trainer's default max_grad_norm
        opt.step(); step += 1
        log.append(dict(step=step, epoch=epoch, lr=lr_at(step - 1), loss=float(np.mean(losses)), margin=float(np.mean(margins)), acc=float(np.mean(accs))))
        if step % LOG == 0 or step == total: print(f'  step {step}/{total} (epoch {epoch + 1})  loss {np.mean([r["loss"] for r in log[-LOG:]]):.4f}  margin {np.mean([r["margin"] for r in log[-LOG:]]):.3f}  margin > 0 {np.mean([r["acc"] for r in log[-LOG:]]):.3f}  lr {lr_at(step - 1):.2e}')
        if step % CKPT == 0 or step == total:
            model.save_pretrained(out_adapter); torch.save(opt.state_dict(), OPTF); json.dump(dict(step=step), open(PROG, 'w')); json.dump(log, open(LOGF, 'w'))
    print('training complete:', out_adapter)


def identity_check(model_name, pairs, system, torch_seed, max_len=512):
    """Before training: a fresh LoRA leaves the base unchanged, so the policy's log-probabilities equal the reference's and the DPO
    loss is log 2 on every pair. Returns (max absolute difference of the log-probabilities, the loss, log 2)."""
    import torch
    from peft import get_peft_model, LoraConfig, prepare_model_for_kbit_training
    from targets import load_lm
    base, tok = load_lm(model_name, four_bit=True); base = prepare_model_for_kbit_training(base); torch.manual_seed(torch_seed); model = get_peft_model(base, LoraConfig(**LORA)); model.eval()
    with torch.no_grad():
        pw = seq_logps(model, tok, [p['prompt'] for p in pairs], [p['chosen'] for p in pairs], system, max_len); pl = seq_logps(model, tok, [p['prompt'] for p in pairs], [p['rejected'] for p in pairs], system, max_len)
        with model.disable_adapter():
            rw = seq_logps(model, tok, [p['prompt'] for p in pairs], [p['chosen'] for p in pairs], system, max_len); rl = seq_logps(model, tok, [p['prompt'] for p in pairs], [p['rejected'] for p in pairs], system, max_len)
        loss, _, _ = dpo_loss(pw, pl, rw, rl)
    d = float(max((pw - rw).abs().max(), (pl - rl).abs().max())); del model, base; torch.cuda.empty_cache()
    return d, float(loss), math.log(2)
