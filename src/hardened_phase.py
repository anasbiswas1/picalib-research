"""The hardened phase (notebook 68b): processing_literal.train_phase with every rollout scored. Added for notebook 68b;
no existing module is changed."""
from __future__ import annotations
import os, json, shutil
import numpy as np


def train_phase_all(EX, out_adapter, workdir, model_name, system, torch_seed, init_adapter, lam=0.3, B=4, LOG=20, CKPT=100, MAXNEW=128, lr=2e-5, min_chars=0):
    """Continue an adapter on a mix of literal examples (exact-target loss, weight lam) and attacked or twin examples
    (on-policy distillation toward the same model with the adapter off): the training step of notebooks 38 and 50,
    with the generator seeded per batch (torch_seed + index of the batch's first example). Resumes from checkpoints.
    The one change from processing_literal.train_phase: rollouts shorter than min_chars characters are dropped (that
    function drops those under 5). With min_chars=0 every rollout is scored, so a near-empty reply to an attacked prompt
    is compared with the teacher's reply to the clean prompt instead of escaping the loss (notebook 68). The number of
    short rollouts (under 20 characters) is logged per batch."""
    import gc, torch
    from peft import PeftModel, prepare_model_for_kbit_training
    from targets import load_lm
    from twin_distill import sample_rollouts, response_logprobs, distill_loss
    from literal_tasks import sft_loss
    os.makedirs(workdir, exist_ok=True); PROG = os.path.join(workdir, "progress.json"); LOGF = os.path.join(workdir, "train_log.json")
    have = os.path.exists(os.path.join(out_adapter, "adapter_config.json"))
    start = json.load(open(PROG))["step"] if (have and os.path.exists(PROG)) else 0
    if have and start >= len(EX): print("phase complete:", out_adapter); return
    base, tok = load_lm(model_name, four_bit=True); base = prepare_model_for_kbit_training(base)
    if not have: shutil.copytree(init_adapter, out_adapter, dirs_exist_ok=True); start = 0; print("initialised from", init_adapter)
    else: print("resuming from example", start)
    model = PeftModel.from_pretrained(base, out_adapter, is_trainable=True); model.print_trainable_parameters()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0); model.train()
    log = json.load(open(LOGF)) if start > 0 and os.path.exists(LOGF) else []
    for step in range(start, len(EX), B):
        torch.manual_seed(torch_seed + step)
        batch = EX[step: step + B]; dist = [e for e in batch if e["kind"] != "literal"]; lit = [e for e in batch if e["kind"] == "literal"]
        terms, rec = [], dict(step=step, kl=None, sft=None, kinds="".join(e["kind"][0] for e in batch))
        if dist:
            roll = sample_rollouts(model, tok, [e["student"] for e in dist], system, max_new_tokens=MAXNEW)
            keep = [i for i, r in enumerate(roll) if len(r) >= min_chars]; rec["short"] = sum(len(r) < 20 for r in roll); rec["nroll"] = len(roll)
            if keep:
                dk = [dist[i] for i in keep]; rk = [roll[i] for i in keep]
                lp_s = response_logprobs(model, tok, [e["student"] for e in dk], rk, system)
                with torch.no_grad(), model.disable_adapter():
                    lp_t = response_logprobs(model, tok, [e["teacher"] for e in dk], rk, system)
                dl, kl = distill_loss(lp_s, lp_t); terms.append(dl); rec["kl"] = kl
        if lit:
            sl = sft_loss(response_logprobs(model, tok, [e["prompt"] for e in lit], [e["gold"] for e in lit], system)); terms.append(lam * sl); rec["sft"] = float(sl.detach())
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
    del model, base, opt; gc.collect(); torch.cuda.empty_cache()
