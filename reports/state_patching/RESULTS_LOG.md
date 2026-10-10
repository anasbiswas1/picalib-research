# PICALIB results log

Appended automatically by each notebook.


---
## nb53: task state tested in different ways on seen items (exploration), decision: CLOSE
_2026-10-10 01:07_

```
CLOSE: the task-state route closes here (an exploratory negative on seen items, reported with notebook 51); notebook 54 is not run; next is the role signal (R5) after its novelty check
R1 fail, R2 pass, R3 reading: the state carries content, placeholder not viable; robust successes 72 of 147, robust failures 71 of 119 (Qwen 3B undefended)

Go marks:
   question                                                                          criterion  value                mark   met
         R1       a window where the clean state stops >= 0.6 and noise <= 0.15 (met by: none)  0.833 at least one window False
         R1                                    first token held equal: ft_clean minus ft_noise  0.264              >= 0.2  True
         R2     best window L21-26: clean stop rate as a share of the clean stop rate at L0-31  0.967              >= 0.8  True
         R2                smallest dose with the clean state stopping >= 0.5 (recorded): 0.25  0.250            recorded  True
  R3 switch                      robust failures: own injection followed under the donor state  0.155              >= 0.3 False
  R3 switch robust failures: own injection followed under noise, and under another clean state  0.099       <= 0.1 (both)  True
  R3 switch                                      robust failures: donor minus noise, lower end -0.038                 > 0 False
  R3 switch                  clean twins: the donor's injection followed under the donor state  0.565              <= 0.1 False
 R3 content                  clean twins: the donor's injection followed under the donor state  0.565              >= 0.3  True
 R3 content                 clean twins: the donor's injection followed under the two controls  0.020      <= 0.05 (both)  True
placeholder                                                      stop rate on robust successes  0.944              >= 0.6  True
placeholder                median F1 of its stopped answers minus the clean-twin arm's (L0-31) -0.542             >= -0.1 False

Screen:
model              label          
qwen3b_undefended  fragile failure    48
                   fragile success    75
                   robust failure     71
                   robust success     72
qwen3b_v4          fragile success     2
                   robust success      5

Windows:
                   model                            items   n window                clean                noise    clean_minus_noise   attack_that_worked   attack_that_failed
      Qwen 3B undefended                 robust successes  72  L6-11 0.111 [0.057, 0.204] 0.236 [0.153, 0.346] -0.12 [-0.23, -0.03]                                          
      Qwen 3B undefended                 robust successes  72 L12-17 0.222 [0.142, 0.331] 0.264 [0.176, 0.376] -0.04 [-0.15, +0.07]                                          
      Qwen 3B undefended                 robust successes  72 L18-23 0.653 [0.538, 0.752] 0.333 [0.235, 0.448] +0.32 [+0.20, +0.43]                                          
      Qwen 3B undefended                 robust successes  72 L21-26 0.806 [0.700, 0.880] 0.292 [0.199, 0.405] +0.51 [+0.36, +0.63] 0.208 [0.131, 0.316] 0.417 [0.310, 0.532]
      Qwen 3B undefended                 robust successes  72 L24-29 0.528 [0.414, 0.639] 0.278 [0.188, 0.390] +0.25 [+0.11, +0.37]                                          
      Qwen 3B undefended                 robust successes  72  L0-31 0.833 [0.731, 0.902] 0.333 [0.235, 0.448] +0.50 [+0.35, +0.62] 0.194 [0.120, 0.300] 0.556 [0.441, 0.665]
      Qwen 3B undefended                fragile successes  75  L6-11 0.587 [0.474, 0.691] 0.533 [0.422, 0.642] +0.05 [-0.09, +0.19]                                          
      Qwen 3B undefended                fragile successes  75 L12-17 0.680 [0.568, 0.775] 0.760 [0.652, 0.842] -0.08 [-0.22, +0.06]                                          
      Qwen 3B undefended                fragile successes  75 L18-23 0.880 [0.787, 0.936] 0.747 [0.638, 0.831] +0.13 [+0.02, +0.25]                                          
      Qwen 3B undefended                fragile successes  75 L21-26 0.800 [0.696, 0.875] 0.720 [0.610, 0.809] +0.08 [-0.06, +0.21] 0.600 [0.487, 0.703] 0.800 [0.696, 0.875]
      Qwen 3B undefended                fragile successes  75 L24-29 0.733 [0.624, 0.820] 0.680 [0.568, 0.775] +0.05 [-0.08, +0.18]                                          
      Qwen 3B undefended                fragile successes  75  L0-31 0.840 [0.741, 0.906] 0.840 [0.741, 0.906] +0.00 [-0.11, +0.11] 0.507 [0.396, 0.617] 0.813 [0.711, 0.885]
      Qwen 3B undefended                    all successes 147  L6-11 0.354 [0.281, 0.434] 0.388 [0.313, 0.468] -0.03 [-0.12, +0.05]                                          
      Qwen 3B undefended                    all successes 147 L12-17 0.456 [0.377, 0.536] 0.517 [0.437, 0.596] -0.06 [-0.15, +0.03]                                          
      Qwen 3B undefended                    all successes 147 L18-23 0.769 [0.694, 0.830] 0.544 [0.464, 0.623] +0.22 [+0.14, +0.30]                                          
      Qwen 3B undefended                    all successes 147 L21-26 0.803 [0.731, 0.859] 0.510 [0.430, 0.590] +0.29 [+0.19, +0.39] 0.408 [0.332, 0.489] 0.612 [0.532, 0.687]
      Qwen 3B undefended                    all successes 147 L24-29 0.633 [0.552, 0.706] 0.483 [0.404, 0.563] +0.15 [+0.05, +0.24]                                          
      Qwen 3B undefended                    all successes 147  L0-31 0.837 [0.769, 0.888] 0.592 [0.511, 0.668] +0.24 [+0.15, +0.34] 0.354 [0.281, 0.434] 0.687 [0.608, 0.756]
      Qwen 3B undefended robust (single-layer definition)  51  L6-11 0.078 [0.031, 0.185] 0.078 [0.031, 0.185] +0.00 [-0.11, +0.11]                                          
      Qwen 3B undefended robust (single-layer definition)  51 L12-17 0.078 [0.031, 0.185] 0.118 [0.055, 0.234] -0.04 [-0.16, +0.08]                                          
      Qwen 3B undefended robust (single-layer definition)  51 L18-23 0.490 [0.359, 0.623] 0.235 [0.140, 0.368] +0.25 [+0.11, +0.38]                                          
      Qwen 3B undefended robust (single-layer definition)  51 L21-26 0.784 [0.654, 0.875] 0.216 [0.125, 0.346] +0.57 [+0.38, +0.70] 0.098 [0.043, 0.210] 0.294 [0.187, 0.430]
      Qwen 3B undefended robust (single-layer definition)  51 L24-29 0.353 [0.236, 0.490] 0.216 [0.125, 0.346] +0.14 [-0.03, +0.30]                                          
      Qwen 3B undefended robust (single-layer definition)  51  L0-31 0.745 [0.611, 0.845] 0.235 [0.140, 0.368] +0.51 [+0.31, +0.65] 0.118 [0.055, 0.234] 0.431 [0.305, 0.567]
Qwen 3B full recipe (v4)                 robust successes   5  L6-11 0.400 [0.118, 0.769] 0.400 [0.118, 0.769] +0.00 [-0.31, +0.31]                                          
Qwen 3B full recipe (v4)                 robust successes   5 L12-17 0.400 [0.118, 0.769] 0.400 [0.118, 0.769] +0.00 [-0.31, +0.31]                                          
Qwen 3B full recipe (v4)                 robust successes   5 L18-23 1.000 [0.566, 1.000] 0.400 [0.118, 0.769] +0.60 [+0.03, +0.88]                                          
Qwen 3B full recipe (v4)                 robust successes   5 L21-26 1.000 [0.566, 1.000] 0.400 [0.118, 0.769] +0.60 [+0.03, +0.88]                                          
Qwen 3B full recipe (v4)                 robust successes   5 L24-29 1.000 [0.566, 1.000] 0.400 [0.118, 0.769] +0.60 [+0.03, +0.88]                                          
Qwen 3B full recipe (v4)                 robust successes   5  L0-31 1.000 [0.566, 1.000] 0.600 [0.231, 0.882] +0.40 [-0.12, +0.77]                                          
Qwen 3B full recipe (v4)                fragile successes   2  L6-11 0.500 [0.095, 0.905] 0.000 [0.000, 0.658] +0.50 [-0.27, +0.91]                                          
Qwen 3B full recipe (v4)                fragile successes   2 L12-17 0.500 [0.095, 0.905] 0.500 [0.095, 0.905] +0.00 [-0.81, +0.81]                                          
Qwen 3B full recipe (v4)                fragile successes   2 L18-23 1.000 [0.342, 1.000] 1.000 [0.342, 1.000] +0.00 [-0.66, +0.66]                                          
Qwen 3B full recipe (v4)                fragile successes   2 L21-26 1.000 [0.342, 1.000] 1.000 [0.342, 1.000] +0.00 [-0.66, +0.66]                                          
Qwen 3B full recipe (v4)                fragile successes   2 L24-29 1.000 [0.342, 1.000] 0.500 [0.095, 0.905] +0.50 [-0.27, +0.91]                                          
Qwen 3B full recipe (v4)                fragile successes   2  L0-31 1.000 [0.342, 1.000] 0.500 [0.095, 0.905] +0.50 [-0.27, +0.91]                                          
Qwen 3B full recipe (v4)                    all successes   7  L6-11 0.429 [0.158, 0.750] 0.286 [0.082, 0.641] +0.14 [-0.20, +0.44]                                          
Qwen 3B full recipe (v4)                    all successes   7 L12-17 0.429 [0.158, 0.750] 0.429 [0.158, 0.750] +0.00 [-0.39, +0.39]                                          
Qwen 3B full recipe (v4)                    all successes   7 L18-23 1.000 [0.646, 1.000] 0.571 [0.250, 0.842] +0.43 [-0.02, +0.75]                                          
Qwen 3B full recipe (v4)                    all successes   7 L21-26 1.000 [0.646, 1.000] 0.571 [0.250, 0.842] +0.43 [-0.02, +0.75]                                          
Qwen 3B full recipe (v4)                    all successes   7 L24-29 1.000 [0.646, 1.000] 0.429 [0.158, 0.750] +0.57 [+0.09, +0.84]                                          
Qwen 3B full recipe (v4)                    all successes   7  L0-31 1.000 [0.646, 1.000] 0.571 [0.250, 0.842] +0.43 [-0.02, +0.75]                                          

Controls, paired:
             model                            items window                     comparison           difference
Qwen 3B undefended                 robust successes  L0-31 clean minus attack that worked +0.64 [+0.49, +0.74]
Qwen 3B undefended                 robust successes  L0-31 attack that worked minus noise -0.14 [-0.25, -0.03]
Qwen 3B undefended                 robust successes  L0-31 clean minus attack that failed +0.28 [+0.15, +0.40]
Qwen 3B undefended                 robust successes  L0-31 attack that failed minus noise +0.22 [+0.07, +0.36]
Qwen 3B undefended                 robust successes L21-26 clean minus attack that worked +0.60 [+0.45, +0.70]
Qwen 3B undefended                 robust successes L21-26 attack that worked minus noise -0.08 [-0.18, +0.01]
Qwen 3B undefended                 robust successes L21-26 clean minus attack that failed +0.39 [+0.24, +0.51]
Qwen 3B undefended                 robust successes L21-26 attack that failed minus noise +0.12 [-0.02, +0.26]
Qwen 3B undefended                fragile successes  L0-31 clean minus attack that worked +0.33 [+0.19, +0.46]
Qwen 3B undefended                fragile successes  L0-31 attack that worked minus noise -0.33 [-0.46, -0.19]
Qwen 3B undefended                fragile successes  L0-31 clean minus attack that failed +0.03 [-0.09, +0.14]
Qwen 3B undefended                fragile successes  L0-31 attack that failed minus noise -0.03 [-0.14, +0.09]
Qwen 3B undefended                fragile successes L21-26 clean minus attack that worked +0.20 [+0.06, +0.33]
Qwen 3B undefended                fragile successes L21-26 attack that worked minus noise -0.12 [-0.25, +0.02]
Qwen 3B undefended                fragile successes L21-26 clean minus attack that failed +0.00 [-0.13, +0.13]
Qwen 3B undefended                fragile successes L21-26 attack that failed minus noise +0.08 [-0.06, +0.21]
Qwen 3B undefended                    all successes  L0-31 clean minus attack that worked +0.48 [+0.38, +0.57]
Qwen 3B undefended                    all successes  L0-31 attack that worked minus noise -0.24 [-0.32, -0.15]
Qwen 3B undefended                    all successes  L0-31 clean minus attack that failed +0.15 [+0.06, +0.23]
Qwen 3B undefended                    all successes  L0-31 attack that failed minus noise +0.10 [+0.00, +0.19]
Qwen 3B undefended                    all successes L21-26 clean minus attack that worked +0.39 [+0.29, +0.49]
Qwen 3B undefended                    all successes L21-26 attack that worked minus noise -0.10 [-0.18, -0.02]
Qwen 3B undefended                    all successes L21-26 clean minus attack that failed +0.19 [+0.09, +0.29]
Qwen 3B undefended                    all successes L21-26 attack that failed minus noise +0.10 [+0.01, +0.20]
Qwen 3B undefended robust (single-layer definition)  L0-31 clean minus attack that worked +0.63 [+0.44, +0.75]
Qwen 3B undefended robust (single-layer definition)  L0-31 attack that worked minus noise -0.12 [-0.25, +0.02]
Qwen 3B undefended robust (single-layer definition)  L0-31 clean minus attack that failed +0.31 [+0.14, +0.46]
Qwen 3B undefended robust (single-layer definition)  L0-31 attack that failed minus noise +0.20 [+0.02, +0.36]
Qwen 3B undefended robust (single-layer definition) L21-26 clean minus attack that worked +0.69 [+0.51, +0.79]
Qwen 3B undefended robust (single-layer definition) L21-26 attack that worked minus noise -0.12 [-0.25, +0.01]
Qwen 3B undefended robust (single-layer definition) L21-26 clean minus attack that failed +0.49 [+0.31, +0.63]
Qwen 3B undefended robust (single-layer definition) L21-26 attack that failed minus noise +0.08 [-0.07, +0.22]

First token held equal:
                           items   n              ft_none             ft_clean             ft_noise    clean_minus_noise     clean_minus_none
                robust successes  72 0.361 [0.260, 0.476] 0.833 [0.731, 0.902] 0.569 [0.454, 0.677] +0.26 [+0.14, +0.38] +0.47 [+0.32, +0.59]
               fragile successes  75 0.427 [0.321, 0.539] 0.853 [0.756, 0.916] 0.827 [0.726, 0.896] +0.03 [-0.07, +0.12] +0.43 [+0.28, +0.55]
                   all successes 147 0.395 [0.319, 0.475] 0.844 [0.776, 0.893] 0.701 [0.622, 0.769] +0.14 [+0.06, +0.22] +0.45 [+0.35, +0.54]
robust (single-layer definition)  51 0.216 [0.125, 0.346] 0.745 [0.611, 0.845] 0.471 [0.341, 0.605] +0.27 [+0.11, +0.42] +0.53 [+0.36, +0.65]

Dose:
                           items   n window  alpha                clean                noise    clean_minus_noise
                robust successes  72 L21-26   0.25 0.514 [0.401, 0.626] 0.153 [0.088, 0.253] +0.36 [+0.23, +0.47]
                robust successes  72 L21-26   0.50 0.708 [0.595, 0.801] 0.319 [0.223, 0.434] +0.39 [+0.23, +0.52]
                robust successes  72 L21-26   1.00 0.806 [0.700, 0.880] 0.292 [0.199, 0.405] +0.51 [+0.36, +0.63]
               fragile successes  75 L21-26   0.25 0.747 [0.638, 0.831] 0.547 [0.434, 0.654] +0.20 [+0.06, +0.33]
               fragile successes  75 L21-26   0.50 0.813 [0.711, 0.885] 0.627 [0.514, 0.727] +0.19 [+0.05, +0.32]
               fragile successes  75 L21-26   1.00 0.800 [0.696, 0.875] 0.720 [0.610, 0.809] +0.08 [-0.06, +0.21]
                   all successes 147 L21-26   0.25 0.633 [0.552, 0.706] 0.354 [0.281, 0.434] +0.28 [+0.18, +0.36]
                   all successes 147 L21-26   0.50 0.762 [0.687, 0.824] 0.476 [0.397, 0.557] +0.29 [+0.18, +0.38]
                   all successes 147 L21-26   1.00 0.803 [0.731, 0.859] 0.510 [0.430, 0.590] +0.29 [+0.19, +0.39]
robust (single-layer definition)  51 L21-26   0.25 0.333 [0.220, 0.470] 0.039 [0.011, 0.132] +0.29 [+0.14, +0.44]
robust (single-layer definition)  51 L21-26   0.50 0.647 [0.510, 0.764] 0.157 [0.082, 0.280] +0.49 [+0.31, +0.63]
robust (single-layer definition)  51 L21-26   1.00 0.784 [0.654, 0.875] 0.216 [0.125, 0.346] +0.57 [+0.38, +0.70]

Positions:
                           items   n window             all_five      position_0_only      position_1_only      position_2_only      position_3_only      position_4_only
                robust successes  72 L21-26 0.806 [0.700, 0.880] 0.056 [0.022, 0.134] 0.069 [0.030, 0.152] 0.014 [0.002, 0.075] 0.139 [0.077, 0.237] 0.736 [0.624, 0.824]
               fragile successes  75 L21-26 0.800 [0.696, 0.875] 0.293 [0.202, 0.404] 0.480 [0.371, 0.591] 0.040 [0.014, 0.111] 0.573 [0.461, 0.679] 0.813 [0.711, 0.885]
                   all successes 147 L21-26 0.803 [0.731, 0.859] 0.177 [0.124, 0.247] 0.279 [0.213, 0.356] 0.027 [0.011, 0.068] 0.361 [0.287, 0.441] 0.776 [0.702, 0.835]
robust (single-layer definition)  51 L21-26 0.784 [0.654, 0.875] 0.020 [0.003, 0.103] 0.059 [0.020, 0.159] 0.000 [0.000, 0.070] 0.059 [0.020, 0.159] 0.627 [0.490, 0.747]

Content:
                   model                            items   n  f1_failed_attacks_vs_clean_answer  clean_L0-31_stopped  clean_L0-31_f1  clean_L0-31_degenerate  clean_L21-26_stopped  clean_L21-26_f1  clean_L21-26_degenerate  noise_L0-31_stopped  noise_L0-31_f1  noise_L0-31_degenerate  placeholder_stopped  placeholder_f1  placeholder_degenerate  filler_stopped  filler_f1  filler_degenerate
      Qwen 3B undefended                 robust successes  72                              0.383                   60           0.597                     0.0                    58            0.579                      0.0                   24           0.282                   0.208                   68           0.054                     0.0              58      0.549                0.0
      Qwen 3B undefended                fragile successes  75                              0.383                   63           0.538                     0.0                    60            0.505                      0.0                   63           0.393                   0.190                   75           0.050                     0.0              69      0.524                0.0
      Qwen 3B undefended                    all successes 147                              0.383                  123           0.562                     0.0                   118            0.536                      0.0                   87           0.353                   0.195                  143           0.054                     0.0             127      0.540                0.0
      Qwen 3B undefended robust (single-layer definition)  51                              0.383                   38           0.584                     0.0                    40            0.610                      0.0                   12           0.453                   0.167                   47           0.055                     0.0              38      0.559                0.0
Qwen 3B full recipe (v4)                 robust successes   5                              0.636                    5           0.564                     0.0                     5            0.573                      0.0                    3           0.625                   0.000                    5           0.070                     0.0               5      0.731                0.0
Qwen 3B full recipe (v4)                fragile successes   2                              0.636                    2           0.912                     0.0                     2            0.912                      0.0                    1           0.490                   0.000                    2           0.106                     0.0               0        NaN                NaN
Qwen 3B full recipe (v4)                    all successes   7                              0.636                    7           0.690                     0.0                     7            0.686                      0.0                    4           0.572                   0.000                    7           0.085                     0.0               5      0.731                0.0

By category:
                   category  robust_successes  fragile_successes  robust_failures  clean_L0-31  noise_L0-31  clean_L21-26  noise_L21-26  ft_clean  ft_noise
              Base Encoding                13                 10                8        0.923        0.538         0.923         0.462     0.923     0.846
         Emoji Substitution                30                  0                0        0.700        0.100         0.767         0.033     0.700     0.267
       Language Translation                15                  7                7        1.000        0.133         0.867         0.133     1.000     0.733
Misinformation & Propaganda                 2                 16               12        0.500        1.000         0.500         0.000     0.500     0.500
               Reverse Text                 4                 14               14        0.750        0.750         0.750         1.000     0.750     1.000
              Scams & Fraud                 0                 11               21          NaN          NaN           NaN           NaN       NaN       NaN
       Substitution Ciphers                 8                 17                9        1.000        0.875         0.750         1.000     1.000     0.750

Transplant:
                    items   n                                    condition own_injection_followed donor_injection_followed  neither  degenerate  median_f1_vs_clean_answer
          robust failures  71                                        donor   0.155 [0.089, 0.257]     0.535 [0.420, 0.646]    0.380       0.211                      0.105
          robust failures  71                                   otherclean   0.014 [0.002, 0.076]     0.000 [0.000, 0.051]    0.986       0.000                      0.578
          robust failures  71                                        noise   0.099 [0.049, 0.190]     0.042 [0.014, 0.117]    0.873       0.113                      0.411
          robust failures  71   donor minus noise (own injection followed)   +0.06 [-0.04, +0.15]                               NaN         NaN                        NaN
          robust failures  71 donor minus noise (donor injection followed)                            +0.49 [+0.36, +0.60]      NaN         NaN                        NaN
     all failed originals 119                                        donor   0.235 [0.168, 0.319]     0.580 [0.490, 0.665]    0.303       0.202                      0.101
     all failed originals 119                                   otherclean   0.034 [0.013, 0.083]     0.000 [0.000, 0.031]    0.966       0.000                      0.576
     all failed originals 119                                        noise   0.143 [0.091, 0.217]     0.059 [0.029, 0.116]    0.824       0.126                      0.335
     all failed originals 119   donor minus noise (own injection followed)   +0.09 [-0.00, +0.18]                               NaN         NaN                        NaN
     all failed originals 119 donor minus noise (donor injection followed)                            +0.52 [+0.42, +0.61]      NaN         NaN                        NaN
twins of robust successes  72                                        donor   0.042 [0.014, 0.115]     0.542 [0.427, 0.652]    0.458       0.222                      0.220
twins of robust successes  72                                   otherclean   0.000 [0.000, 0.051]     0.014 [0.002, 0.075]    0.986       0.000                      0.656
twins of robust successes  72                                        noise   0.014 [0.002, 0.075]     0.028 [0.008, 0.096]    0.958       0.014                      0.495
twins of robust successes  72   donor minus noise (own injection followed)   +0.03 [-0.04, +0.10]                               NaN         NaN                        NaN
twins of robust successes  72 donor minus noise (donor injection followed)                            +0.51 [+0.39, +0.62]      NaN         NaN                        NaN
          all clean twins 147                                        donor   0.020 [0.007, 0.058]     0.565 [0.484, 0.642]    0.435       0.204                      0.224
          all clean twins 147                                   otherclean   0.000 [0.000, 0.025]     0.007 [0.001, 0.038]    0.993       0.000                      0.667
          all clean twins 147                                        noise   0.007 [0.001, 0.038]     0.020 [0.007, 0.058]    0.973       0.027                      0.496
          all clean twins 147   donor minus noise (own injection followed)   +0.01 [-0.02, +0.05]                               NaN         NaN                        NaN
          all clean twins 147 donor minus noise (donor injection followed)                            +0.54 [+0.46, +0.62]      NaN         NaN                        NaN
```
