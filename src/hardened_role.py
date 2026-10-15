"""The hardened phase in the two-role format (notebook 69b): role_train.train_phase_role with every rollout scored.
Added for notebook 69b; no existing module is changed."""
from __future__ import annotations
import os, json
from llama_h2h import load_llama
from role_train import PROBE, chat_role, sample_rollouts_role, response_logprobs_role


def train_phase_role_all(EX, out_adapter, workdir, system, tokenizer_from, init_adapter=None, lam=0.3, B=4, LOG=10, CKPT=50, MAXNEW=128, lr=2e-5, min_chars=0):
    """llama_h2h.train_phase with the two-role prompt everywhere: attacked and twin examples by on-policy distillation
    toward the same model with the adapter off, literal examples by the exact-target loss (weight lam). Checkpoints
    every CKPT batches and resumes from workdir/progress.json. tokenizer_from: the tokenizer role_tokenizer chose.
    The one change from role_train.train_phase_role: rollouts shorter than min_chars characters are dropped (that function
    drops those under 5). With min_chars=0 every rollout is scored (notebook 68b). Short rollouts (under 20 characters)
    are counted per batch in the log."""
    import shutil, numpy as np, torch
    from peft import LoraConfig, get_peft_model, PeftModel
    from twin_distill import distill_loss
    from literal_tasks import sft_loss
    os.makedirs(workdir, exist_ok=True); PROG = os.path.join(workdir, "progress.json"); LOGF = os.path.join(workdir, "train_log.json")
    start = json.load(open(PROG))["step"] if os.path.exists(PROG) else 0
    if start >= len(EX) and os.path.exists(os.path.join(out_adapter, "adapter_config.json")): print("phase complete:", out_adapter); return
    base, tok = load_llama(tokenizer_from=tokenizer_from, train=True)
    assert "<|start_header_id|>input<|end_header_id|>" in chat_role(tok, system, PROBE), "the training tokenizer does not render the input role: stop"
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
            roll = sample_rollouts_role(model, tok, [e["student"] for e in dist], system, max_new_tokens=MAXNEW)
            keep = [i for i, r in enumerate(roll) if len(r) >= min_chars]; rec["short"] = sum(len(r) < 20 for r in roll); rec["nroll"] = len(roll)
            if keep:
                dk = [dist[i] for i in keep]; rk = [roll[i] for i in keep]
                lp_s = response_logprobs_role(model, tok, [e["student"] for e in dk], rk, system)
                with torch.no_grad(), model.disable_adapter():
                    lp_t = response_logprobs_role(model, tok, [e["teacher"] for e in dk], rk, system)
                dl, kl = distill_loss(lp_s, lp_t); terms.append(dl); rec["kl"] = kl
        if lit:
            sl = sft_loss(response_logprobs_role(model, tok, [e["prompt"] for e in lit], [e["gold"] for e in lit], system)); terms.append(lam * sl); rec["sft"] = float(sl)
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
