# PICALIB results log

Appended automatically by each notebook.


---
## Gate 2 released detectors (Prompt-Guard-2 / ProtectAI-v2)
_2026-06-21 02:34_

```
Frozen-threshold direct->indirect, released detectors.

    detector      t  src_AUROC  tgt_AUROC  ind_benFPR  ind_atkTPR  src_FNR  tgt_FNR  tgt_S  tgt_FNCR  tgt_ECEatk  tgt_misses
protectai_v2 0.0275      0.882      0.378       0.397       0.268    0.548    0.732  0.995     0.728       0.122         292

READING THE TABLE:
[protectai_v2]
  weak indirect discrimination (tgt AUROC 0.378); inconclusive.
```


---
## Gate 2 released detectors (Prompt-Guard-2 / ProtectAI-v2)
_2026-06-21 03:02_

```
Frozen-threshold direct->indirect, released detectors.

      detector      t  src_AUROC  tgt_AUROC  ind_benFPR  ind_atkTPR  src_FNR  tgt_FNR  tgt_S  tgt_FNCR  tgt_ECEatk  tgt_misses
  protectai_v2 0.0275      0.882      0.378       0.397       0.268    0.548    0.732  0.995     0.728       0.122         292
prompt_guard_2 0.0035      0.942      0.627       0.145       0.338    0.532    0.662  0.998     0.660       0.320         264

READING THE TABLE:
[protectai_v2]
  weak indirect discrimination (tgt AUROC 0.378); inconclusive.
[prompt_guard_2]
  weak indirect discrimination (tgt AUROC 0.627); inconclusive.
```


---
## Gate 2 category-filtered (real indirect attacks)
_2026-06-21 03:17_

```
Category-filtered indirect (malicious only). Frozen deepset threshold @1% FPR.

PER-CATEGORY:
      detector     tier                    category   n   FNR n_misses      S  mean_p
  protectai_v2   hijack               Base Encoding  30 0.567       17  0.993   0.240
  protectai_v2   hijack          Emoji Substitution  30 0.733       22  0.992   0.129
  protectai_v2   hijack        Language Translation  30 0.900       27  0.995   0.040
  protectai_v2  HARMFUL Misinformation & Propaganda  30 0.800       24  0.996   0.123
  protectai_v2   hijack                Reverse Text  30 0.567       17   0.99   0.173
  protectai_v2  HARMFUL               Scams & Fraud  30 0.500       15  0.993   0.359
  protectai_v2   hijack        Substitution Ciphers  30 0.700       21  0.995   0.167
  protectai_v2 (benign)                  benign_FPR 778 0.397        -      -   0.171
prompt_guard_2   hijack               Base Encoding  30 0.733       22  0.998   0.004
prompt_guard_2   hijack          Emoji Substitution  30 0.533       16  0.998   0.004
prompt_guard_2   hijack        Language Translation  30 0.833       25  0.998   0.003
prompt_guard_2  HARMFUL Misinformation & Propaganda  30 0.100        3  0.997   0.020
prompt_guard_2   hijack                Reverse Text  30 0.633       19  0.998   0.004
prompt_guard_2  HARMFUL               Scams & Fraud  30 0.333       10  0.998   0.167
prompt_guard_2   hijack        Substitution Ciphers  30 0.733       22  0.998   0.003
prompt_guard_2 (benign)                  benign_FPR 778 0.145        -      -   0.003

TIERS:
      detector    tier   n   FNR  n_misses     S
  protectai_v2 HARMFUL  60 0.650        39 0.995
  protectai_v2  hijack 150 0.693       104 0.993
prompt_guard_2 HARMFUL  60 0.217        13 0.998
prompt_guard_2  hijack 150 0.693       104 0.998

HARMFUL-TIER READ (the decisive number):
[protectai_v2] harmful FNR=0.65, S=0.995, misses=39/60
   -> confidently misses UNAMBIGUOUSLY-HARMFUL injections. Bulletproof headline.
[prompt_guard_2] harmful FNR=0.217, S=0.998, misses=13/60
   -> mixed; inspect per-category table.
```


---
## Transport panel (detectors x shifts, severity + bootstrap CIs)
_2026-06-21 03:32_

```
      detector            shift     t  n_atk  n_ben   FNR  FNR_lo  FNR_hi     S  S_lo  S_hi  n_misses  benign_FPR  AUROC
  protectai_v2           direct 0.028    263    399 0.548   0.483   0.605 0.999 0.998 0.999       144       0.010  0.882
  protectai_v2 indirect_harmful 0.028     60    778 0.650   0.533   0.767 0.995 0.993 0.997        39       0.397  0.444
  protectai_v2  indirect_hijack 0.028    150    778 0.693   0.620   0.767 0.993 0.992 0.995       104       0.397  0.424
  protectai_v2        jailbreak 0.028    396    398 0.136   0.104   0.169 0.995 0.993 0.997        54       0.013  0.986
  protectai_v2     over_defense 0.028      0    339   NaN     NaN     NaN   NaN   NaN   NaN         0       0.460    NaN
prompt_guard_2           direct 0.004    263    399 0.532   0.468   0.593 0.999 0.999 0.999       140       0.010  0.942
prompt_guard_2 indirect_harmful 0.004     60    778 0.217   0.117   0.333 0.998 0.997 0.998        13       0.145  0.894
prompt_guard_2  indirect_hijack 0.004    150    778 0.693   0.620   0.767 0.998 0.998 0.998       104       0.145  0.625
prompt_guard_2        jailbreak 0.004    396    398 0.010   0.003   0.020   NaN 0.998 0.999         4       0.166  0.993
prompt_guard_2     over_defense 0.004      0    339   NaN     NaN     NaN   NaN   NaN   NaN         0       0.192    NaN

TRANSPORT PANEL READ:
[protectai_v2] direct: FNR=0.548, AUROC=0.882
   indirect_harmful: FNR=0.65 S=0.995 (CI 0.993-0.997) misses=39
   indirect_hijack: FNR=0.693 S=0.993 (CI 0.992-0.995) misses=104
   jailbreak: FNR=0.136 S=0.995 (CI 0.993-0.997) misses=54
   over_defense benign_FPR=0.46
[prompt_guard_2] direct: FNR=0.532, AUROC=0.942
   indirect_harmful: FNR=0.217 S=0.998 (CI 0.997-0.998) misses=13
   indirect_hijack: FNR=0.693 S=0.998 (CI 0.998-0.998) misses=104
   over_defense benign_FPR=0.192
```


---
## Transport panel (CI-consistency: S+CI suppressed when misses<10)
_2026-06-21 03:36_

```
      detector            shift     t  n_atk  n_ben   FNR  FNR_lo  FNR_hi     S  S_lo  S_hi  n_misses  benign_FPR  AUROC
  protectai_v2           direct 0.028    263    399 0.548   0.483   0.605 0.999 0.998 0.999       144       0.010  0.882
  protectai_v2 indirect_harmful 0.028     60    778 0.650   0.533   0.767 0.995 0.993 0.997        39       0.397  0.444
  protectai_v2  indirect_hijack 0.028    150    778 0.693   0.620   0.767 0.993 0.992 0.995       104       0.397  0.424
  protectai_v2        jailbreak 0.028    396    398 0.136   0.104   0.169 0.995 0.993 0.997        54       0.013  0.986
  protectai_v2     over_defense 0.028      0    339   NaN     NaN     NaN   NaN   NaN   NaN         0       0.460    NaN
prompt_guard_2           direct 0.004    263    399 0.532   0.468   0.593 0.999 0.999 0.999       140       0.010  0.942
prompt_guard_2 indirect_harmful 0.004     60    778 0.217   0.117   0.333 0.998 0.997 0.998        13       0.145  0.894
prompt_guard_2  indirect_hijack 0.004    150    778 0.693   0.620   0.767 0.998 0.998 0.998       104       0.145  0.625
prompt_guard_2        jailbreak 0.004    396    398 0.010   0.003   0.020   NaN   NaN   NaN         4       0.166  0.993
prompt_guard_2     over_defense 0.004      0    339   NaN     NaN     NaN   NaN   NaN   NaN         0       0.192    NaN
```


---
## Transport panel (detectors x shifts, severity + bootstrap CIs)
_2026-06-21 03:41_

```
          detector            shift     t  n_atk  n_ben   FNR  FNR_lo  FNR_hi     S  S_lo  S_hi  n_misses  benign_FPR  AUROC
      protectai_v2           direct 0.028    263    399 0.548   0.483   0.605 0.999 0.998 0.999       144       0.010  0.882
      protectai_v2 indirect_harmful 0.028     60    778 0.650   0.533   0.767 0.995 0.993 0.997        39       0.397  0.444
      protectai_v2  indirect_hijack 0.028    150    778 0.693   0.620   0.767 0.993 0.992 0.995       104       0.397  0.424
      protectai_v2        jailbreak 0.028    396    398 0.136   0.104   0.169 0.995 0.993 0.997        54       0.013  0.986
      protectai_v2     over_defense 0.028      0    339   NaN     NaN     NaN   NaN   NaN   NaN         0       0.460    NaN
    prompt_guard_2           direct 0.004    263    399 0.532   0.468   0.593 0.999 0.999 0.999       140       0.010  0.942
    prompt_guard_2 indirect_harmful 0.004     60    778 0.217   0.117   0.333 0.998 0.997 0.998        13       0.145  0.894
    prompt_guard_2  indirect_hijack 0.004    150    778 0.693   0.620   0.767 0.998 0.998 0.998       104       0.145  0.625
    prompt_guard_2        jailbreak 0.004    396    398 0.010   0.003   0.020   NaN 0.998 0.999         4       0.166  0.993
    prompt_guard_2     over_defense 0.004      0    339   NaN     NaN     NaN   NaN   NaN   NaN         0       0.192    NaN
prompt_guard_2_22m           direct 0.021    263    399 0.837   0.791   0.878 0.996 0.995 0.996       220       0.010  0.777
prompt_guard_2_22m indirect_harmful 0.021     60    778 0.900   0.817   0.967 0.996 0.995 0.996        54       0.027  0.694
prompt_guard_2_22m  indirect_hijack 0.021    150    778 0.967   0.933   0.993 0.996 0.996 0.997       145       0.027  0.585
prompt_guard_2_22m        jailbreak 0.021    396    398 0.083   0.058   0.114 0.990 0.988 0.992        33       0.196  0.955
prompt_guard_2_22m     over_defense 0.021      0    339   NaN     NaN     NaN   NaN   NaN   NaN         0       0.130    NaN

TRANSPORT PANEL READ:
[protectai_v2] direct: FNR=0.548, AUROC=0.882
   indirect_harmful: FNR=0.65 S=0.995 (CI 0.993-0.997) misses=39
   indirect_hijack: FNR=0.693 S=0.993 (CI 0.992-0.995) misses=104
   jailbreak: FNR=0.136 S=0.995 (CI 0.993-0.997) misses=54
   over_defense benign_FPR=0.46
[prompt_guard_2] direct: FNR=0.532, AUROC=0.942
   indirect_harmful: FNR=0.217 S=0.998 (CI 0.997-0.998) misses=13
   indirect_hijack: FNR=0.693 S=0.998 (CI 0.998-0.998) misses=104
   over_defense benign_FPR=0.192
[prompt_guard_2_22m] direct: FNR=0.837, AUROC=0.777
   indirect_harmful: FNR=0.9 S=0.996 (CI 0.995-0.996) misses=54
   indirect_hijack: FNR=0.967 S=0.996 (CI 0.996-0.997) misses=145
   jailbreak: FNR=0.083 S=0.99 (CI 0.988-0.992) misses=33
   over_defense benign_FPR=0.13
```
