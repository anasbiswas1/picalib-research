"""Fine-tune and score a payload-decoupled structural detector on the notebook-17 dataset."""
from __future__ import annotations
import json, os, inspect, random, math
import numpy as np

MODEL_NAME = "microsoft/deberta-v3-base"
MAX_LEN = 512


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def select_config(records, config, rng):
    pos = [r for r in records if r["label"] == 1]
    neg = [r for r in records if r["label"] == 0]
    if config == "full":
        return pos + neg
    if config == "ablation_no_twins":
        return pos + [r for r in neg if r["form"] in ("host_only", "declarative_insert")]
    if config == "full_sizematched":
        target = sum(r["form"] in ("host_only", "declarative_insert") for r in neg)
        by_form = {}
        for r in neg: by_form.setdefault(r["form"], []).append(r)
        total = len(neg); out = []
        for form, rs in by_form.items():
            k = int(round(target * len(rs) / total)); rng.shuffle(rs); out += rs[:k]
        return pos + out
    raise ValueError(config)


def class_weights(records):
    n1 = sum(r["label"] for r in records); n0 = len(records) - n1
    return [len(records) / (2 * n0), len(records) / (2 * n1)]


def train_model(train_records, val_records, out_dir, seed=0, epochs=2, lr=2e-5, batch=8, accum=2, max_len=MAX_LEN):
    """Fine-tune with a class-weighted loss; select the epoch with the best val AUROC. Returns the best-model dir."""
    import torch
    from datasets import Dataset
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification, TrainingArguments, Trainer, set_seed)
    from sklearn.metrics import roc_auc_score
    set_seed(seed)
    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    def enc(b): return tok(b["text"], truncation=True, max_length=max_len)
    tr = Dataset.from_list([{"text": r["text"], "label": int(r["label"])} for r in train_records]).map(enc, batched=True, remove_columns=["text"])
    va = Dataset.from_list([{"text": r["text"], "label": int(r["label"])} for r in val_records]).map(enc, batched=True, remove_columns=["text"])
    w = torch.tensor(class_weights(train_records), dtype=torch.float)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)
    model = model.float()   # transformers 5.x can load in the checkpoint dtype; fp16 mixed precision needs fp32 master weights

    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels = inputs.pop("labels")
            outputs = model(**inputs)
            loss = torch.nn.functional.cross_entropy(outputs.logits.float(), labels, weight=w.to(outputs.logits.device))
            return (loss, outputs) if return_outputs else loss

    def metrics(ep):
        logits, labels = ep.predictions, ep.label_ids
        if isinstance(logits, (tuple, list)): logits = logits[0]
        p = torch.softmax(torch.tensor(np.asarray(logits)).float(), -1)[:, 1].numpy()
        return {"auroc": float(roc_auc_score(labels, p))}

    params = inspect.signature(TrainingArguments.__init__).parameters
    strat_key = "eval_strategy" if "eval_strategy" in params else "evaluation_strategy"
    total_steps = math.ceil(len(tr) / (batch * accum)) * epochs
    warm = {"warmup_ratio": 0.06} if "warmup_ratio" in params else {"warmup_steps": int(0.06 * total_steps)}
    args = TrainingArguments(output_dir=out_dir, per_device_train_batch_size=batch, per_device_eval_batch_size=32,
                             gradient_accumulation_steps=accum, num_train_epochs=epochs, learning_rate=lr, weight_decay=0.01,
                             fp16=torch.cuda.is_available(), save_strategy="epoch", load_best_model_at_end=True,
                             metric_for_best_model="auroc", greater_is_better=True, save_total_limit=1, logging_steps=50,
                             report_to="none", seed=seed, **warm, **{strat_key: "epoch"})
    tok_key = "processing_class" if "processing_class" in inspect.signature(Trainer.__init__).parameters else "tokenizer"
    trainer = WeightedTrainer(model=model, args=args, train_dataset=tr, eval_dataset=va, compute_metrics=metrics, **{tok_key: tok})
    trainer.train()
    trainer.save_model(os.path.join(out_dir, "best")); tok.save_pretrained(os.path.join(out_dir, "best"))
    json.dump({"best_metric": trainer.state.best_metric, "log": trainer.state.log_history}, open(os.path.join(out_dir, "train_log.json"), "w"))
    return os.path.join(out_dir, "best")


def score_texts(model_dir, texts, batch=32, max_len=MAX_LEN):
    """P(injection) for each text, batched inference."""
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(model_dir); model = AutoModelForSequenceClassification.from_pretrained(model_dir).float().to(dev).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            b = tok(texts[i:i + batch], truncation=True, max_length=max_len, padding=True, return_tensors="pt").to(dev)
            out.append(torch.softmax(model(**b).logits.float(), -1)[:, 1].cpu().numpy())
    return np.concatenate(out) if out else np.array([])
