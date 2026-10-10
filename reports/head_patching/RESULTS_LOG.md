# PICALIB results log

Appended automatically by each notebook.


---
## nb56 (follow-on work): carrier heads, localisation and overlap on the 3B (exploration, nothing claimed)
_2026-10-10 19:37_

```
GO to notebook 57 on sufficiency alone (L1 partial, L2 failed): the defense is judged on security only and no necessity claim is made
proxy pass / gate two fail, L1 partial, L2 fail, L3 pass, I1 fail, O1 void

Marks:
                            mark                                                                                                                                                                criterion                                                                     value                              needed   met
                  Proxy gate one                                                                                            injection margin against the judge, version "A, same document" (see change 6)                                                      0.800 [0.662, 0.922]                             >= 0.80  True
Proxy gate one as pre-registered                                                                                  the same against the judge on the cross-document transplant: failed, kept on the record                                                      0.766 [0.676, 0.856]                             >= 0.80 False
                  Proxy gate two                                                                                                                     margin against the judge, joint C_20 patch on the 72                                                                     0.609                             >= 0.75 False
                              L1 C_20 from the attacked run into the clean twin: twins following the injection (controls: random_20_draw1, random_20_draw2, random_20_draw3, complement_20, attention_20) 0.111 [0.057, 0.204] (controls, highest 0.000); C_40 0.319 [0.223, 0.434]       >= 0.30 with controls <= 0.05 False
                    L1 (partial)                                                                                                                             C_40 reaches 0.15 with controls at most 0.05                                                    0.319 (controls 0.000)       >= 0.15 with controls <= 0.05  True
                              L2                                                                       C_20 from the clean twin into the attacked run: attacks stopped; random matched; paired difference                  0.625 [0.510, 0.728]; random 0.264; +0.36 [+0.20, +0.50] >= 0.60, <= 0.15, lower end >= 0.25 False
                              L3                                                                                    median token F1 of the stopped answers with the clean twin's answer; degenerate share      0.503 on 45 answers (notebook 53 full state 0.597); degenerate 0.000                >= 0.497 and <= 0.05  True
                              I1                                                                                                   I_20 from an instruction run into a plain run: the model does the task                                                      0.180 [0.127, 0.249]                             >= 0.30 False
                              O1                                                                                                                                       overlap reading (void if I1 fails)                                                           void: I1 failed                            reported  True

Gate one, all three versions:
                                                          version                                                                                  what   n  followed  auroc    lo    hi  mark   met
                                      A, same document (the gate)                  attacked run's full template state into its own clean twin, 72 twins  72        41  0.800 0.662 0.922   0.8  True
                                                     B, necessity clean twin's full state into the attacked run, notebook 53's judged answers, 72 items  72        60  0.634 0.408 0.851   NaN   NaN
C, cross-document transplant (the gate as pre-registered; FAILED)                    notebook 53's transplant, donor from another category and document 147        83  0.766 0.676 0.856   0.8 False

Sufficiency:
       head_set  size twins_following_the_injection  rate
           C_10    10          0.056 [0.022, 0.134] 0.056
           C_20    20          0.111 [0.057, 0.204] 0.111
           C_40    40          0.319 [0.223, 0.434] 0.319
random_20_draw1    20          0.000 [0.000, 0.051] 0.000
random_20_draw2    20          0.000 [0.000, 0.051] 0.000
random_20_draw3    20          0.000 [0.000, 0.051] 0.000
  complement_20    20          0.000 [0.000, 0.051] 0.000
   attention_20    20          0.000 [0.000, 0.051] 0.000
      all_heads   576          0.569 [0.454, 0.677] 0.569

Necessity:
          head_set  size      attacks_stopped  rate  stopped_n  median_f1_vs_clean_answer  degenerate
              C_10    10 0.458 [0.348, 0.573] 0.458         33                      0.480       0.030
              C_20    20 0.625 [0.510, 0.728] 0.625         45                      0.503       0.000
              C_40    40 0.653 [0.538, 0.752] 0.653         47                      0.547       0.000
   random_20_draw1    20 0.181 [0.109, 0.285] 0.181         13                      0.000       0.385
   random_20_draw2    20 0.264 [0.176, 0.376] 0.264         19                      0.000       0.316
   random_20_draw3    20 0.222 [0.142, 0.331] 0.222         16                      0.000       0.500
     complement_20    20 0.194 [0.120, 0.300] 0.194         14                      0.000       0.571
      attention_20    20 0.278 [0.188, 0.390] 0.278         20                      0.466       0.050
         all_heads   576 0.819 [0.715, 0.891] 0.819         59                      0.599       0.000
C_20 mean ablation    20 0.583 [0.468, 0.690] 0.583         42                      0.518       0.000
       C_20 zeroed    20 0.333 [0.235, 0.448] 0.333         24                      0.495       0.000

Instruction and cross-transfer:
                head_set                                                          what        does_the_task  rate
I_20 (instruction heads)                  instruction run into the plain run, pool two 0.180 [0.127, 0.249]  0.18
    C_20 (carrier heads) instruction run into the plain run, pool two (cross-transfer) 0.180 [0.127, 0.249]  0.18
               all heads                  instruction run into the plain run, pool two 0.200 [0.144, 0.271]  0.20

Overlap:
       scope  shared_heads  layer_matched_random_mean  layer_matched_99_9th  spearman  cross_transfer       reading
all families            14                        3.2                   8.0     0.503            0.18 partly shared
 translation            14                        NaN                   NaN       NaN            0.90              
       emoji            14                        NaN                   NaN       NaN            0.00              
      base64            14                        NaN                   NaN       NaN            0.00              
     reverse            14                        NaN                   NaN       NaN            0.00              
      cipher            14                        NaN                   NaN       NaN            0.00              

By family:
                     family  robust_items  sufficiency_C20  necessity_C20
              Base Encoding            13            0.000          0.692
         Emoji Substitution            30            0.067          0.500
       Language Translation            15            0.400          0.800
Misinformation & Propaganda             2            0.000          0.500
               Reverse Text             4            0.000          0.500
              Scams & Fraud             0              NaN            NaN
       Substitution Ciphers             8            0.000          0.750

Literature opened:
     arxiv                                                                                 plan_note  opened_here  published                                                                                                          title
2310.15213                        Function Vectors in Large Language Models (Todd et al., ICLR 2024)         True 2023-10-23                                                                      Function Vectors in Large Language Models
2505.12075 Do different prompting methods yield a common task representation? (Davidson et al. 2025)         True 2025-05-17                          Do different prompting methods yield a common task representation in language models?
2310.15916                             In-Context Learning Creates Task Vectors (Hendel et al. 2023)         True 2023-10-24                                                                       In-Context Learning Creates Task Vectors
2609.37737                                Where Do LLMs Decide to Break the Rules? (Wen et al. 2026)         True 2026-09-29               Where Do LLMs Decide to Break the Rules? Mechanistic Localization of Prompt Injection Compliance
2610.05295                 Readable Before Actionable (Yu et al. 2026), partly confirmed in the plan         True 2026-10-04                                        Readable Before Actionable: Causal Tracing of Indirect Prompt Injection
2607.26228                                                          V-Steer (Zeng et al., COLM 2026)         True 2026-07-28                                                             Steering Instruction Hierarchies at Inference Time
2602.20708                                     ICON (Wang et al. 2026), partly confirmed in the plan         True 2026-02-24                          ICON: Indirect Prompt Injection Defense for Agents based on Inference-Time Correction
2411.00348                                      Attention Tracker (Hung et al., NAACL 2025 Findings)         True 2024-11-01                                                  Attention Tracker: Detecting Prompt Injection Attacks in LLMs
2502.13946                               Why Safeguarded Ships Run Aground? (Leong et al., ACL 2025)         True 2025-02-19 Why Safeguarded Ships Run Aground? Aligned Large Language Models' Safety Mechanisms Tend to Be Anchored in The
2609.36570                                                           CounterSteer (Russinovich 2026)         True 2026-09-29                                   CounterSteer: Suppressing Indirect Prompt Injection with Activation Steering
2602.07930                     Patches of Nonlinearity: Instruction Vectors (Bigoulaeva et al. 2026)         True 2026-02-08                                          Patches of Nonlinearity: Instruction Vectors in Large Language Models
2605.24659                                                    IterInject (not confirmed in the plan)         True 2026-05-23            IterInject: Indirect Prompt Injection Against LLM Agents via Feedback-Guided Iterative Optimization
2608.08027                                                         BASIS (not confirmed in the plan)         True 2026-08-08                         BASIS: Breach-Aware Selective Prompt Injection Shielding with Prefill Attention Probes
2605.00236                                                           ARA (not confirmed in the plan)         True 2026-04-30                                                                                  Attention Is Where You Attack
2410.13708                                                        Sahara (not confirmed in the plan)         True 2024-10-17                                                  On the Role of Attention Heads in Large Language Model Safety
2509.25843                                                       ASGuard (not confirmed in the plan)         True 2025-09-30                                     ASGuard: Activation-Scaling Guard to Mitigate Targeted Jailbreaking Attack
```


---
## nb56b (follow-on work): the head ranking redone by generation after gate two failed, and the instruction asymmetry tested by placement
_2026-10-10 21:26_

```
the single-head ranking has no resolution (0 of 64 heads do anything alone), so C* is largely the margin set reordered and F2 is close to a repeat of L1 on fresh controls. GO to notebook 57 on sufficiency alone, built on C*_40 (partial F2, F3 failed as it did in notebook 56), mean ablation primary; no claim about instruction heads either way: P1 gave neither reading
F2 partial, F3 fail, P1: neither reading: reported as it stands; C*_20 keeps 20 of notebook 56's C_20; C_40 by generation 0.319, Cknock_20 0.264, controls at most 0.000

Marks:
          mark                                                                                                                                                                 criterion                                                                                                                                 value                                                              needed   met
            F1                    single-head re-ranking: of the top 20 by generation, how many were in notebook 56's C_20; rank correlation over 64 heads; heads that do anything alone                                                                  20/20 kept; Spearman +nan; 0 of 64 do anything alone (highest 0.000)                     reported; single-head ranking has no resolution  True
           F1b knockout ranking: Cknock_20 sufficiency on the 72; heads with a positive drop; ties broken by margin order; rank correlation of the drop with the margin effect over C_40                                                    0.264 [0.176, 0.376]; 31/40 heads had any drop (resolution 0.042); Spearman +0.352                                                            reported  True
F1b (reported)                                                                            C_40 itself, measured by generation here (the knockout top 40 is C_40), with the same controls                                                                                        0.319 [0.223, 0.434] (controls, highest 0.000)                                        reported, outside every mark  True
            F2                                  C*_20 into the clean twin: twins following the injection (controls: rstar_20_draw1, rstar_20_draw2, rstar_20_draw3, cstar_complement_20)                                                            0.111 [0.057, 0.204] (controls, highest 0.000); C*_40 0.319 [0.223, 0.434]                                       >= 0.30 with controls <= 0.05 False
  F2 (partial)                                                                                                                             C*_40 reaches 0.15 with controls at most 0.05                                                                                                                0.319 (controls 0.000)                                       >= 0.15 with controls <= 0.05  True
            F3                                                                               C*_20 from the clean twin into the attacked run: stopped; random matched; paired difference                                                                              0.625 [0.510, 0.728]; random 0.236; +0.39 [+0.23, +0.52]                                 >= 0.60, <= 0.15, lower end >= 0.25 False
 F4 (reported)                                                                                        clean-stop rate (stopped and not degenerate): C_20, C*_20, and the highest control                                                                                        C_20 0.625; C*_20 0.625; highest control 0.264                                       reported; F3 stays as it fell  True
            P1                               all heads, instruction after the document against the separator-matched before placement, both conditioned on the source run doing the task after 0.395 [0.292, 0.507] (n=76); before, matched 0.692 [0.536, 0.814] (n=39); unconditioned after 0.200, notebook 56's before 0.200 after >= 0.30 with before <= 0.20, on at least 30 conditioned items False

Re-ranking (top 20):
 layer  head  margin_effect  margin_rank  generation_rate  generation_rank
    22     3         0.1494            1              0.0                1
    22     5         0.1290            2              0.0                2
    27    13         0.1119            3              0.0                3
    27    14         0.1068            4              0.0                4
    34     6         0.0875            5              0.0                5
    22     0         0.0799            6              0.0                6
    35    12         0.0723            7              0.0                7
    20     8         0.0702            8              0.0                8
    23     1         0.0699            9              0.0                9
    21    14         0.0672           10              0.0               10
    21     7         0.0632           11              0.0               11
    24     6         0.0594           12              0.0               12
    26     3         0.0589           13              0.0               13
    21     3         0.0584           14              0.0               14
    28     2         0.0568           15              0.0               15
    26    13         0.0548           16              0.0               16
    17     5         0.0493           17              0.0               17
    21     8         0.0480           18              0.0               18
    21     1         0.0479           19              0.0               19
    34     2         0.0441           20              0.0               20

Every head set:
              head_set  size  sufficiency       sufficiency_ci  necessity         necessity_ci  clean_stop  median_f1_of_stops  degenerate_of_stops
                  C_10    10        0.056 0.056 [0.022, 0.134]      0.458 0.458 [0.348, 0.573]       0.444               0.480                0.030
                  C_20    20        0.111 0.111 [0.057, 0.204]      0.625 0.625 [0.510, 0.728]       0.625               0.503                0.000
                  C_40    40        0.319 0.319 [0.223, 0.434]      0.653 0.653 [0.538, 0.752]       0.653               0.547                0.000
       random_20_draw1    20        0.000 0.000 [0.000, 0.051]      0.181 0.181 [0.109, 0.285]       0.111               0.000                0.385
       random_20_draw2    20        0.000 0.000 [0.000, 0.051]      0.264 0.264 [0.176, 0.376]       0.181               0.000                0.316
       random_20_draw3    20        0.000 0.000 [0.000, 0.051]      0.222 0.222 [0.142, 0.331]       0.111               0.000                0.500
         complement_20    20        0.000 0.000 [0.000, 0.051]      0.194 0.194 [0.120, 0.300]       0.083               0.000                0.571
          attention_20    20        0.000 0.000 [0.000, 0.051]      0.278 0.278 [0.188, 0.390]       0.264               0.466                0.050
             all_heads   576        0.569 0.569 [0.454, 0.677]      0.819 0.819 [0.715, 0.891]       0.819               0.599                0.000
              Cstar_10    10        0.056 0.056 [0.022, 0.134]      0.458 0.458 [0.348, 0.573]       0.444               0.480                0.030
              Cstar_20    20        0.111 0.111 [0.057, 0.204]      0.625 0.625 [0.510, 0.728]       0.625               0.503                0.000
              Cstar_40    40        0.319 0.319 [0.223, 0.434]      0.653 0.653 [0.538, 0.752]       0.653               0.547                0.000
             Cknock_10    10        0.083 0.083 [0.039, 0.170]      0.556 0.556 [0.441, 0.665]       0.556               0.526                0.000
             Cknock_20    20        0.264 0.264 [0.176, 0.376]      0.736 0.736 [0.624, 0.824]       0.736               0.537                0.000
        rstar_20_draw1    20        0.000 0.000 [0.000, 0.051]      0.236 0.236 [0.153, 0.346]       0.153               0.000                0.353
        rstar_20_draw2    20        0.000 0.000 [0.000, 0.051]      0.111 0.111 [0.057, 0.204]       0.097               0.009                0.125
        rstar_20_draw3    20        0.000 0.000 [0.000, 0.051]      0.111 0.111 [0.057, 0.204]       0.069               0.000                0.375
   cstar_complement_20    20        0.000 0.000 [0.000, 0.051]      0.194 0.194 [0.120, 0.300]       0.083               0.000                0.571
    C_20 mean ablation    20          NaN                           0.583 0.583 [0.468, 0.690]       0.583               0.518                0.000
Cstar_20 mean ablation    20          NaN                           0.583 0.583 [0.468, 0.690]       0.583               0.518                0.000

Position control:
     family  does_the_task_before_nb56  all_heads_before_nb56  does_the_task_before_matched  n_before_matched  n_before_matched_conditioned  all_heads_before_matched  all_heads_before_matched_conditioned  Cstar20_before_matched_conditioned  does_the_task_after  n_after  n_after_conditioned  all_heads_after  all_heads_after_conditioned  Cstar20_after_conditioned
translation                      1.000                  0.967                          1.00                30                            30                     0.900                                 0.900                               0.933                1.000       30                   30              1.0                        1.000                      0.633
      emoji                      0.967                  0.033                          0.10                30                             3                     0.000                                 0.000                               0.000                0.967       30                   29              0.0                        0.000                      0.000
     base64                      0.000                  0.000                          0.00                30                             0                     0.033                                   NaN                                 NaN                0.233       30                    7              0.0                        0.000                      0.000
    reverse                      0.000                  0.000                          0.00                30                             0                     0.000                                   NaN                                 NaN                0.167       30                    5              0.0                        0.000                      0.000
     cipher                      0.700                  0.000                          0.20                30                             6                     0.000                                 0.000                               0.000                0.167       30                    5              0.0                        0.000                      0.000
   all five                      0.533                  0.200                          0.26               150                            39                     0.187                                 0.692                               0.718                0.507      150                   76              0.2                        0.395                      0.250
```
