---
license: llama3.1
license_link: https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE
base_model: meta-llama/Llama-3.1-8B-Instruct
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

# Llama-3.1-8B-Instruct-TwinDistillation

A LoRA adapter (rank 16) for **meta-llama/Llama-3.1-8B-Instruct** trained with **twin distillation**, a fine-tuning recipe against indirect prompt injection: the model learns to judge an instruction by where it came from, not by what it says. It is the final Llama-3.1-8B-Instruct model of the paper *Twin Distillation Against Indirect Prompt Injection: Training Language Models to Distinguish User Instructions from Injected Instructions* (Md Anas Biswas, 2026, https://doi.org/10.20944/preprints202611.2399.v1; code at https://github.com/anasbiswas1/picalib-research). Nothing else about the model changes: same base weights, same chat template, one small adapter.

**Built with Llama.** Llama 3.1 is licensed under the Llama 3.1 Community License, Copyright Meta Platforms, Inc. All Rights Reserved.

## What it does

- Follows the user's instructions and ignores instructions that sit inside the document it is asked to read, including instructions dressed as a fake user turn, a fake end of task, an authority claim and the other standard attack forms.
- Keeps the document's text when asked to copy, count, list, edit or translate it: an instruction-like sentence in the document is carried through like any other sentence, neither obeyed nor deleted.
- Trained for the summarisation framing (a task sentence over a document) and measured on that framing, on SecFid's counting, extraction, translation and editing tasks, and on AgentDojo tool outputs read as text. A deployment in another framing needs its own measurement.

## Prompt layout

two roles, as Meta-SecAlign specifies: the task in the user role, the document in the input role (tokenizer and chat template of facebook/Meta-SecAlign-8B). System prompt used in training and evaluation: `You are a helpful assistant that processes the content users give you.`

## How to load

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
base = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-3.1-8B-Instruct", torch_dtype="bfloat16", device_map="auto")
model = PeftModel.from_pretrained(base, "anasbiswas/Llama-3.1-8B-Instruct-TwinDistillation").eval()
tok = AutoTokenizer.from_pretrained("facebook/Meta-SecAlign-8B")   # its chat template has the input role
SYSTEM = "You are a helpful assistant that processes the content users give you."
messages = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Summarise the key information in the document below."},
            {"role": "input", "content": document_text}]   # the untrusted document goes in the input role
ids = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)
out = model.generate(ids, max_new_tokens=160, do_sample=False)
print(tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True))
```
The base model is gated: accept the Llama 3.1 licence on its Hugging Face page first. Remove Llama special tokens (`<|start_header_id|>`, `<|end_header_id|>`, `<|eot_id|>`, `<|begin_of_text|>`) from the document before passing it, as the paper's code does. The defence was trained and measured in this two-role layout; the same weights run with the document inside the user turn are a different, weaker defence (paper, Section 7.11).

## Headline numbers (paper, Tables 4 and 13; report files at commit 08e477d)

| measure | this adapter | undefended base |
|---|---|---|
| BIPIA injections followed, fixed attacker, 13 wordings (lower is better) | 0.086 | 0.490 |
| BIPIA injections followed, adaptive attacker, 13 attempts | 0.000 | 0.714 |
| BIPIA injections followed, combined | 0.086 | 0.738 |
| sealed S2: fresh injected instructions followed (rule-decided, 500 rows) | 0.002 | 0.650 |
| sealed S4: the user's own instructions followed on fresh documents (240; higher is better) | 0.662 | 0.613 |
| white-box GCG attack, share of 25 documents broken | 0.040 | 0.960 |

## Limits

- A white-box attacker with the weights (GCG) broke this adapter on 0.040 of 25 documents in the paper's run (undefended base 0.960); the paper's Qwen adapters are broken on 0.440 and 0.760, as are the published defences on those bases. Do not rely on any adapter alone against an attacker who holds the weights.
- The defence is tied to the prompt layout it was trained in (above). Run it in that layout.
- Residual attack success against the fixed attacker comes mostly from rewrites that replace most of the host document (paper, Section 7.1).
- One training run per model; the paper reports confidence intervals for every number above.

## Training

Four stages on one adapter: twin distillation (an on-policy distillation loss on attacked prompts, each paired with a twin in which the same instruction comes from the user), a literal phase, processing and task phases (none on Llama), and a forged-turn phase. Full recipe, data and settings: paper, Section 5 and Table 3; code: notebook 73c and `src/` in the repository.

## Licence

This adapter is a derivative of Llama-3.1-8B-Instruct and is released under the Llama 3.1 Community License of its base model.

## Citation

Md Anas Biswas. Twin Distillation Against Indirect Prompt Injection: Training Language Models to Distinguish User Instructions from Injected Instructions. 2026. Preprint: https://doi.org/10.20944/preprints202611.2399.v1. Code: https://github.com/anasbiswas1/picalib-research.
