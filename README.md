# picalib-research

**Calibration Collapse under Security Shift in Prompt-Injection Detectors**

Author: Md Anas Biswas · University of Portsmouth

A security-asymmetric calibration audit of prompt-injection / guardrail detectors.
Core claim: a detector can pass clean, matched-threshold, LODO-style evaluation and
still **confidently** wave attacks through — a high-confidence false negative — and
only severity-aware, attack-conditional metrics see it.

## Metric family (locked)
- **S** — headline. Severity per miss = mean benign-confidence of missed attacks.
  Weight-free, base-rate-invariant.
- **ECE_atk** — primary companion. Attack-conditional calibration (calibration of
  P(attack) restricted to true attacks). Weight-free.
- **SeverityRisk(κ)** — secondary, cost-weighted sensitivity sweep over κ.
- Supporting: FNR, FNCR = FNR·S, HCFN(τ), CCI (collapse under shift), π·FNCR (deployed risk).

Conventions: attack = positive class = 1; p = P(attack); miss = (y=1 and p<t);
N+ = attack count (all rates are attack-conditional).

## Files
- `metrics.py` — the dataset-independent metric harness. Run `python metrics.py`
  for the self-test + base-rate invariance check.
- `00_setup.ipynb` — one-time Colab/Drive/GitHub setup (token stored to Drive once).
- `01_metric_harness.ipynb` — runs the harness, the invariance check, and the figure.
- `figures/` — generated figures.

## Workflow (end of every work unit)
1. Save notebooks to Drive (`/content/drive/MyDrive/PICALIB_Research/picalib-research/`).
2. `git add` → `git commit -m "<meaningful message>"` → `git push`.
3. Confirm Drive and GitHub are in sync. No work left uncommitted overnight.

## Status
- [x] Work unit 1 — metric harness + base-rate invariance check (this commit)
- [ ] Gate 1 — data spine + dedup audit (Open-Prompt-Injection, BIPIA, NotInject)
- [ ] Gate 2 — one-detector probe (e5-base-v2 + XGBoost), direct → indirect
- [ ] Full panel + LODO transport + ranking-reversal stats
- [ ] Add LICENSE (MIT, like EXHEART) before making the repo public / linking it in the paper
