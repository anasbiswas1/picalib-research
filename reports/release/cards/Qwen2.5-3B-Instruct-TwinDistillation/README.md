---
license: other
license_name: qwen-research
license_link: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE
base_model: Qwen/Qwen2.5-3B-Instruct
library_name: peft
pipeline_tag: text-generation
language:
- en
tags:
- prompt-injection
- indirect-prompt-injection
- llm-security
- lora
- twin-distillation
---

# Qwen2.5-3B-Instruct-TwinDistillation

A LoRA adapter (rank 16) for **Qwen/Qwen2.5-3B-Instruct** trained with **twin distillation**, a fine-tuning recipe against indirect prompt injection: the model learns to judge an instruction by where it came from, not by what it says. It is the final Qwen2.5-3B-Instruct model of the paper *Twin Distillation Against Indirect Prompt Injection: Training Language Models to Distinguish User Instructions from Injected Instructions* (Md Anas Biswas, 2026; code at https://github.com/anasbiswas1/picalib-research). Nothing else about the model changes: same base weights, same chat template, one small adapter.

## What it does

- Follows the user's instructions and ignores instructions that sit inside the document it is asked to read, including instructions dressed as a fake user turn, a fake end of task, an authority claim and the other standard attack forms.
- Keeps the document's text when asked to copy, count, list, edit or translate it: an instruction-like sentence in the document is carried through like any other sentence, neither obeyed nor deleted.
- Trained for the summarisation framing (a task sentence over a document) and measured on that framing, on SecFid's counting, extraction, translation and editing tasks, and on AgentDojo tool outputs read as text. A deployment in another framing needs its own measurement.

## Prompt layout

one user turn: task sentence, blank line, document. System prompt used in training and evaluation: `You are a helpful assistant that processes the content users give you.`

## How to load

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
base = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-3B-Instruct", torch_dtype="bfloat16", device_map="auto")
model = PeftModel.from_pretrained(base, "anasbiswas/Qwen2.5-3B-Instruct-TwinDistillation").eval()
tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-3B-Instruct")
SYSTEM = "You are a helpful assistant that processes the content users give you."
prompt = "Summarise the key information in the document below.\n\n" + document_text   # task, blank line, document
messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
ids = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)
out = model.generate(ids, max_new_tokens=160, do_sample=False)
print(tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True))
```
The paper's models were run with the base in 4-bit quantisation and greedy decoding; bfloat16 is fine for use. The defence was trained and measured in this one-user-turn layout (paper, Section 7.11).

## Headline numbers (paper, Tables 4 and 13; report files at commit 08e477d)

| measure | this adapter | undefended base |
|---|---|---|
| BIPIA injections followed, fixed attacker, 13 wordings (lower is better) | 0.176 | 0.510 |
| BIPIA injections followed, adaptive attacker, 13 attempts | 0.000 | 0.748 |
| BIPIA injections followed, combined | 0.176 | 0.776 |
| sealed S2: fresh injected instructions followed (rule-decided, 500 rows) | 0.028 | 0.594 |
| sealed S4: the user's own instructions followed on fresh documents (240; higher is better) | 0.571 | 0.504 |
| white-box GCG attack, share of 25 documents broken | 0.440 | 1.000 |

## Limits

- A white-box attacker with the weights (GCG) still breaks this adapter on 0.440 of 25 documents (undefended base 1.000); the published defences on the same base are broken as well. Do not rely on this adapter alone against an attacker who holds the weights.
- The defence is tied to the prompt layout it was trained in (above). Run it in that layout.
- Residual attack success against the fixed attacker comes mostly from rewrites that replace most of the host document (paper, Section 7.1).
- One training run per model; the paper reports confidence intervals for every number above.

## Training

Four stages on one adapter: twin distillation (an on-policy distillation loss on attacked prompts, each paired with a twin in which the same instruction comes from the user), a literal phase, processing and task phases, and a forged-turn phase. Full recipe, data and settings: paper, Section 5 and Table 3; code: notebook 73e and `src/` in the repository.

## Licence

This adapter is a derivative of Qwen2.5-3B-Instruct and is released under the Qwen Research License of its base model (research use; see the licence link above).

## Citation

Md Anas Biswas. Twin Distillation Against Indirect Prompt Injection: Training Language Models to Distinguish User Instructions from Injected Instructions. 2026. Code: https://github.com/anasbiswas1/picalib-research.
