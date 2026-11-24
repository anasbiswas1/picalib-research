# Twin distillation against indirect prompt injection

Code, notebooks, report files and released models for two papers on indirect prompt injection by Md Anas Biswas (School of Computing, University of Portsmouth).

- **Method paper:** *Twin Distillation Against Indirect Prompt Injection: Training Language Models to Distinguish User Instructions from Injected Instructions* (2026). Preprint: [doi:10.20944/preprints202611.2399.v1](https://doi.org/10.20944/preprints202611.2399.v1).
- **Evaluation paper:** *Confidently Wrong: Severity-Aware Calibration of Prompt-Injection Detectors under Attack Shift*, [arXiv:2606.22659](https://arxiv.org/abs/2606.22659).
- **Released models (Hugging Face):** [Qwen2.5-3B-Instruct-TwinDistillation](https://huggingface.co/anasbiswas/Qwen2.5-3B-Instruct-TwinDistillation) | [Qwen2.5-7B-Instruct-TwinDistillation](https://huggingface.co/anasbiswas/Qwen2.5-7B-Instruct-TwinDistillation) | [Llama-3.1-8B-Instruct-TwinDistillation](https://huggingface.co/anasbiswas/Llama-3.1-8B-Instruct-TwinDistillation)

## The idea

When an assistant reads a web page, an e-mail or a document for its user, an instruction hidden in that text can make the assistant obey the attacker instead of the user. Detectors placed in front of the model are fooled by rewording. Retraining recipes work better, but they mostly teach the model to ignore anything that sounds like an instruction, so it ignores its user too and deletes sentences it should copy or translate.

Twin distillation teaches the model to judge an instruction by where it came from, not by how it sounds. Training examples come in pairs: in one, an instruction is hidden inside the document and the model learns to answer as if it were not there; in its twin, the same words come from the user and the model learns to follow them. Later phases teach it to copy, count, edit and translate documents without dropping such sentences, and to hold up against the disguises attackers use (a fake user turn, a fake end of task, an authority claim, and others). The result is one small LoRA adapter (rank 16) on an unchanged base model.

Measured on sets no notebook had used before, the three final models are the only defences in the comparison that stay secure against the black-box attackers, follow the user's instructions as often as their bases and keep the document's text. An attacker who holds the model weights still breaks the Qwen models, as it breaks the published defences on the same bases.

![Final evaluation on sealed sets](figures/final/final_evaluation_78.png)

*The final models (blue) against their undefended bases (grey) and the published defences on the same bases (orange: SecAlign's recipe retrained on Qwen; Meta-SecAlign-8B on Llama), on sets no notebook had used before: BIPIA injections on fresh documents, fresh injected instructions (S2), and the user's own instructions on fresh documents (S4). Notebook 78, `reports/final/`.*

## Headline numbers

Lower is better except S4. Every number has a 95 percent interval in the report file named in the last column.

| measure | Qwen2.5-3B: ours / base | Qwen2.5-7B: ours / base | Llama-3.1-8B: ours / base | report file |
|---|---|---|---|---|
| BIPIA injections followed, fixed and adaptive attackers combined | 0.176 / 0.776 | 0.238 / 0.743 | 0.086 / 0.738 | `reports/forged/security_73e.csv`, `security_73f.csv`, `security_73c.csv` |
| sealed S2: fresh injected instructions followed (500 rows) | 0.028 / 0.594 | 0.000 / 0.668 | 0.002 / 0.650 | `reports/final/security_78.csv` |
| sealed S4: the user's own instructions followed on fresh documents (240; higher is better) | 0.571 / 0.504 | 0.746 / 0.742 | 0.662 / 0.613 | `reports/final/user_issued_78.csv` |
| white-box GCG attack, share of 25 documents broken | 0.440 / 1.000 | 0.760 / 1.000 | 0.040 / 0.960 | `reports/baselines/gcg_79.csv` |

The full comparison with Meta-SecAlign-8B, DefensiveTokens and SecAlign's recipe retrained on Qwen, the sixteen attack forms, the free adaptive attacker, the copy battery, SecFid and AgentDojo tool outputs is in the method paper (Tables 4 to 16) and in `reports/`.

## Quick start

```bash
pip install transformers peft accelerate
```

Qwen models (one user turn: task sentence, blank line, document):

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
BASE, ADAPTER = "Qwen/Qwen2.5-3B-Instruct", "anasbiswas/Qwen2.5-3B-Instruct-TwinDistillation"   # or the 7B pair
base = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype="bfloat16", device_map="auto")
model = PeftModel.from_pretrained(base, ADAPTER).eval()
tok = AutoTokenizer.from_pretrained(BASE)
SYSTEM = "You are a helpful assistant that processes the content users give you."
prompt = "Summarise the key information in the document below.\n\n" + document_text
messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
ids = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)
out = model.generate(ids, max_new_tokens=160, do_sample=False)
print(tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True))
```

Llama model (two roles, as Meta-SecAlign specifies: the task in the user role, the document in the input role, using the tokenizer and chat template of `facebook/Meta-SecAlign-8B`; the base is gated, accept the Llama 3.1 licence first):

```python
base = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-3.1-8B-Instruct", torch_dtype="bfloat16", device_map="auto")
model = PeftModel.from_pretrained(base, "anasbiswas/Llama-3.1-8B-Instruct-TwinDistillation").eval()
tok = AutoTokenizer.from_pretrained("facebook/Meta-SecAlign-8B")
messages = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Summarise the key information in the document below."},
            {"role": "input", "content": document_text}]
```

Each defence was trained and measured in the layout shown above; the same weights run in another layout are a different, weaker defence (method paper, Section 7.11). The model cards on Hugging Face carry the per-model numbers, limits and licences.

## What is in the repository

| path | contents |
|---|---|
| `src/` | All code the notebooks call. Training: `twin_distill.py` (twin distillation loss and twins), `processing_literal.py`, `literal_tasks.py`, `hardened_phase.py`, `task_aware.py`, `contrast_phase.py`, `forged_turn.py`, `forged_processing.py`, `role_train.py`, `qwen_role.py`. Attacks: `adaptive_attack.py`, `adaptive_strict.py`, `free_adaptive.py`, `untrained_attacks.py`, `manual_attacks.py`, `gcg_attack.py`, `attack_success.py`. Baselines: `secalign_qwen.py`, `defensive_tokens.py`, `llama_h2h.py`. Evaluation: `final_scoring.py`, `fidelity_audit.py`, `fidelity_exact.py`, `agentdojo_source.py`, `interval_panel.py`, `ci_tools.py`, `reslog.py`. Mechanism: `head_patching.py`, `head_blind.py`, `head_steer.py`, `attn_read.py`, `state_patching.py`. Detectors and calibration (evaluation paper): `detectors.py`, `metrics.py`, `rank_metrics.py`, `calibration_pool.py`, `structural_*.py`. |
| `notebooks/` | Every experiment, numbered in the order it was run (below). Each notebook runs through `src/`, writes its CSVs to `reports/` and ends with the repository's commit step. |
| `reports/` | The CSV and text files behind every number in both papers, plus `RESULTS_LOG.md`, a running log of every notebook's result. The number after an underscore in a file name is the notebook that wrote it (`security_78.csv` is from notebook 78). |
| `figures/` | Figures written by the notebooks at 600 dpi. |
| `tools/commit_cell.py` | The single commit step every notebook ends with (restores credentials, strips notebook outputs, refuses data and secrets, commits and pushes). |
| `tests/` | Unit checks for training code paths. |

Not in the repository: `data/` (datasets, model caches, trained adapters, per-item model outputs and judge verdicts). The adapters are on Hugging Face; the datasets are fetched by the notebooks under their own licences; the cached outputs and verdicts are available from the author on request.

## Notebook map

| notebooks | what they do |
|---|---|
| 00 to 27 | Evaluation paper: the metric harness, data spine and deduplication, detector probes, released detectors, transport across sources, the LLM judge, adaptive adversaries, calibration and interval studies, AgentDojo, paraphrase smoothing, task-drift probe. |
| 28 to 42 | First twin-distillation runs on Qwen2.5-3B, validation, ablations, the 7B replication, the full recipe on the 7B, Llama training and the head-to-head with Meta-SecAlign. |
| 43 to 50 | Adaptive and strict attackers, final and paper scoring, threshold and stopping audits, review audits, literal-phase controls. |
| 51 to 61b | Mechanism: task-state and state-patching tests, risk-control feasibility, the carrier heads (localisation, re-ranking, held-out check, head-restricted defence, where the heads look), shared direction across defences, the input-role Llama model and its matched-format baselines. |
| 62 | SecFid benchmark. |
| 65 to 71b | The processing, rebalancing, hardened, task-aware and contrast phases on all three bases; the rebuilt user-issued and form checks. |
| 72 to 74e | Manual attack suite, the forged-turn phase (final models 73e, 73f, 73c), sixteen untrained attack forms, the free adaptive attacker, white-box GCG, the input-role Qwen checks. |
| 75 to 79 | Twin ablation on the final recipe, agent tool outputs (AgentDojo, two-way judge), SecAlign's recipe retrained on Qwen, the sealed-set evaluation, the published baselines through the hard tests. |
| 80 to 82f | Routes that were tested and closed (provenance margin, inner attack gate, adversarial twin distillation); their decisions are in `reports/` and they are not part of the method. |
| 83 | Release of the three adapters on Hugging Face (model cards under `reports/release/cards/`, URLs and checksums in `reports/release/adapters_83.csv`). |

## Reproducing

The notebooks were run on Google Colab (G4 GPU) with the repository at `/content/drive/MyDrive/PICALIB_Research/picalib-research`; each notebook's first cell mounts Drive and sets the paths. The method paper's tables are built from the report files at commit `08e477d`; the main ones are `reports/forged/security_73*.csv` and `fidelity_73*.csv` (Tables 4 and 9), `reports/untrained/forms_74.csv` (Table 5), `reports/adaptive_free/free_attacker_74b.csv` and `reports/whitebox/gcg_74c.csv` (Table 7), `reports/final/user_issued_78.csv` (Table 8), `reports/forged/secfid_73*.csv` (Table 10), `reports/baselines/*_79.csv` (Tables 11 and 12), `reports/final/security_78.csv` (Table 13), `reports/final/agent_strict_76b.csv` (Table 14), `reports/forged/*_75.csv` (Table 15) and `reports/shared_drive/drive_59b.csv` and `drive_61b.csv` (Table 16).

## Datasets and licences

BIPIA, Open-Prompt-Injection, AgentDojo and SecFid are used under their own licences; the IFEval scoring code and prompts are fetched from Google's repository at a pinned commit rather than redistributed. The code in this repository is released under the MIT licence (see `LICENSE`). The adapters are derivatives of their base models and are released under the base models' licences (Qwen Research License for the 3B, Apache 2.0 for the 7B, Llama 3.1 Community License for the Llama model).

## Citation

```bibtex
@misc{biswas2026twin,
  title  = {Twin Distillation Against Indirect Prompt Injection: Training Language Models to Distinguish User Instructions from Injected Instructions},
  author = {Biswas, Md Anas},
  year   = {2026},
  publisher = {Preprints.org},
  doi    = {10.20944/preprints202611.2399.v1},
  note   = {Code: https://github.com/anasbiswas1/picalib-research}
}

@misc{biswas2026confidently,
  title  = {Confidently Wrong: Severity-Aware Calibration of Prompt-Injection Detectors under Attack Shift},
  author = {Biswas, Md Anas},
  year   = {2026},
  eprint = {2606.22659},
  archivePrefix = {arXiv}
}
```
