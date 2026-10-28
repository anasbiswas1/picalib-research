"""W0 for notebook 82f: the opening-only loss in src/atd.py (train_atd's window), checked on a tiny random model on the CPU.
  R  regression: with window=None, train_atd gives the same training log (reverse KL, exact-target loss, kinds, the reverse KL
     by kind) as the reference module, step for step from the same seed. The reference is src/atd.py at HEAD (git show),
     which before notebook 82f's commit is the module without the window; a path to another reference may be given instead.
  W  with window=8, inside train_atd the distillation loss receives, for every attacked example (student and teacher prompts
     differ; the pool's draws included), the first min(8, length) per-token terms of its reply, and for every twin and clean
     anchor all of them; the first batch's rollouts and log-probability passes are the same as without the window.
Needs: the repository as the working directory, data/atd82d/phase4_examples.json and pool_sources.json (notebook 82d's set),
and the Qwen2.5-3B-Instruct tokenizer (downloaded if not cached). The model is a two-layer random Qwen2 built here; no GPU.
  python tests/test_atd_window.py [path of the reference module]"""
import os, sys, json, shutil, subprocess, tempfile, importlib.util
import torch
ROOT = os.getcwd(); sys.path.insert(0, os.path.join(ROOT, 'src'))
import targets, qwen_role, twin_distill
from targets import TASK_SYSTEM
from transformers import AutoTokenizer, Qwen2Config, Qwen2ForCausalLM
TOK_NAME = 'Qwen/Qwen2.5-3B-Instruct'; WORK = tempfile.mkdtemp(prefix='atd_window_')
# ---- the reference module and the module under test ----
ref_path = sys.argv[1] if len(sys.argv) > 1 else None
if ref_path is None:
    ref_path = os.path.join(WORK, 'atd_ref.py'); r_ = subprocess.run(['git', 'show', 'HEAD:src/atd.py'], capture_output=True, text=True)
    assert r_.returncode == 0 and r_.stdout, 'git show HEAD:src/atd.py failed: give the reference module as the argument'
    open(ref_path, 'w').write(r_.stdout)
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
REF = load(ref_path, 'atd_ref'); NEW = load(os.path.join(ROOT, 'src', 'atd.py'), 'atd_new')
assert 'window' in NEW.train_atd.__code__.co_varnames, 'src/atd.py has no window parameter'
# ---- a tiny random model with the real tokenizer, loaded on the CPU in place of the 4-bit load ----
tok = AutoTokenizer.from_pretrained(TOK_NAME)
if tok.pad_token is None: tok.pad_token = tok.eos_token
torch.manual_seed(0)
cfg_ = Qwen2Config(vocab_size=len(tok), hidden_size=64, intermediate_size=128, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=2048, tie_word_embeddings=True,
                   bos_token_id=tok.bos_token_id, eos_token_id=tok.eos_token_id, pad_token_id=tok.pad_token_id)
TINY = os.path.join(WORK, 'tiny'); Qwen2ForCausalLM(cfg_).save_pretrained(TINY); tok.save_pretrained(TINY)
def load_lm_cpu(model_name, four_bit=True):
    t_ = AutoTokenizer.from_pretrained(TINY)
    if t_.pad_token is None: t_.pad_token = t_.eos_token
    return Qwen2ForCausalLM.from_pretrained(TINY, dtype=torch.float32).eval(), t_
targets.load_lm = load_lm_cpu
# ---- a 12-example slice of notebook 82d's set: attacked examples with their twins, clean anchors, exact-target examples ----
EX = json.load(open('data/atd82d/phase4_examples.json')); POOL = json.load(open('data/atd82d/pool_sources.json'))
idx = []
for j, e in enumerate(EX):
    if e['kind'] == 'attacked' and j + 1 < len(EX) and EX[j + 1]['kind'] == 'twin' and len(idx) < 8: idx += [j, j + 1]
idx += [j for j, e in enumerate(EX) if e['kind'] == 'clean'][:2] + [j for j, e in enumerate(EX) if e['kind'] == 'literal'][:2]
SUB = [EX[j] for j in idx]; assert len(SUB) == 12 and sum(e['kind'] == 'attacked' for e in SUB) == 4
CFG = dict(k=4, P=4, n_p=2, m=2, n_cand=16, topk=8, tau=0.5, L=2, mini=8)
PROBES = [e['student'] if e['kind'] != 'literal' else e['prompt'] for e in SUB[:6]]
def run(mod, tag, **kw):
    wd = os.path.join(WORK, tag); shutil.rmtree(wd, ignore_errors=True); os.makedirs(wd)
    mod.train_atd(SUB, POOL, out_adapter=os.path.join(wd, 'lora'), workdir=wd, model_name=TINY, system=TASK_SYSTEM, torch_seed=82_500_000, init_adapter=None, probe_prompts=PROBES, cfg=CFG, min_chars=0, pool_twins=True, MAXNEW=24, LOG=1, **kw)
    return json.load(open(os.path.join(wd, 'train_log.json')))
# ---- R ----
LO = run(REF, 'ref'); LN = run(NEW, 'new_nowindow')
assert len(LO) == len(LN) == 3, (len(LO), len(LN))
for a, b in zip(LO, LN):
    assert a['kinds'] == b['kinds'] and a['kl'] == b['kl'] and a['sft'] == b['sft'] and a.get('kl_by') == b.get('kl_by'), (a, b)
    assert 'window' not in b
print(f"R: window=None: {len(LN)} logged batches identical to the reference module (reverse KL {[round(x['kl'], 5) if x['kl'] is not None else None for x in LN]})")
# ---- W ----
K = 8; calls = {'lp': [], 'dl': []}
orig_lp, orig_dl = qwen_role.response_logprobs_q, twin_distill.distill_loss
def lp_spy(model, tok_, prompts, responses, system, max_len=1024):
    out = orig_lp(model, tok_, prompts, responses, system, max_len); calls['lp'].append((list(prompts), [int(x.shape[0]) for x in out])); return out
def dl_spy(lp_s, lp_t):
    calls['dl'].append(([int(x.shape[0]) for x in lp_s], [int(x.shape[0]) for x in lp_t])); return orig_dl(lp_s, lp_t)
qwen_role.response_logprobs_q, twin_distill.distill_loss = lp_spy, dl_spy
try: LW = run(NEW, 'new_window', window=K)
finally: qwen_role.response_logprobs_q, twin_distill.distill_loss = orig_lp, orig_dl
assert all(x.get('window') == K for x in LW)
n_att = n_same = 0
for (sp, sl), (tp, tl), (ds, dt) in zip(calls['lp'][0::2], calls['lp'][1::2], calls['dl']):       # each batch: the student pass, the teacher pass, then distill_loss
    assert sl == tl and len(sp) == len(ds) == len(dt)
    for p_s, p_t, full, ks, kt in zip(sp, tp, sl, ds, dt):
        if p_s != p_t: assert ks == kt == min(K, full), (ks, kt, full); n_att += 1
        else: assert ks == kt == full, (ks, full); n_same += 1
assert n_att >= 4 and n_same >= 4, (n_att, n_same)
calls2 = []
def lp_spy2(model, tok_, prompts, responses, system, max_len=1024):
    out = orig_lp(model, tok_, prompts, responses, system, max_len); calls2.append([int(x.shape[0]) for x in out]); return out
qwen_role.response_logprobs_q = lp_spy2
try: run(NEW, 'new_nowindow2')
finally: qwen_role.response_logprobs_q = orig_lp
assert [l for _, l in calls['lp']][:2] == calls2[:2], "the window changed the first batch's rollouts or log-probability passes"
print(f"W: window={K}: {n_att} attacked examples (the pool's draws included) scored on their first min({K}, length) reply tokens, {n_same} twins, pool twins and clean anchors on their whole reply; the first batch's rollouts and log-probability passes unchanged")
shutil.rmtree(WORK, ignore_errors=True); print('W0 PASSED')
