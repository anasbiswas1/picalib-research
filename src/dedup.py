
"""
dedup.py — cross-dataset near-duplicate audit
=============================================
Gate 1's hard go/no-go. If the same prompt recurs across datasets, an apparent
"transport gap" is an artefact, not a real distribution shift. We use MinHash +
LSH at Jaccard >= 0.8 (the Gate AI protocol, arXiv 2606.02959; cite it — this is
established, not novel) to flag near-duplicates within and ACROSS sources.

Output:
  - within-source duplication (diagonal)  -> internal redundancy
  - cross-source overlap (off-diagonal)    -> the leakage signal
A high off-diagonal between two ATTACK-bearing sources is the red flag.

Dependency: datasketch, pandas, numpy.
"""

import collections
import numpy as np
import pandas as pd
from datasketch import MinHash, MinHashLSH


def _shingles(text, k=3):
    """Word k-grams; falls back to the token set for very short prompts."""
    toks = str(text).lower().split()
    if len(toks) < k:
        return set(toks) if toks else {str(text).lower().strip()}
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def _minhash(text, num_perm=128, k=3):
    m = MinHash(num_perm=num_perm)
    for s in _shingles(text, k):
        m.update(s.encode("utf8"))
    return m


def dedup_audit(df, threshold=0.8, num_perm=128, k=3,
                text_col="text", src_col="source", n_examples=5):
    """Run the near-duplicate audit on a harmonised df.

    Returns a dict:
      overlap_frac : DataFrame [source x source]; entry [A,B] = fraction of A
                     items with >=1 near-dup (Jaccard>=threshold) in B.
                     Diagonal = internal duplication; off-diagonal = leakage.
      overlap_count: same but raw counts.
      examples     : a few cross-source near-duplicate text pairs to eyeball.
      verdict      : 'GO' / 'INVESTIGATE' with a reason.
    """
    df = df.reset_index(drop=True)
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    mh = {}
    for i in df.index:
        m = _minhash(df.at[i, text_col], num_perm, k)
        mh[i] = m
        lsh.insert(str(i), m)

    src_of = df[src_col].to_dict()
    sources = sorted(df[src_col].unique())
    hits = collections.defaultdict(set)         # i -> set of sources it dups into
    cross_pairs = []                            # (text_i, src_i, text_j, src_j)

    for i in df.index:
        for r in lsh.query(mh[i]):
            j = int(r)
            if j == i:
                continue
            hits[i].add(src_of[j])
            if src_of[j] != src_of[i] and len(cross_pairs) < 200:
                if i < j:                       # record each cross pair once
                    cross_pairs.append((df.at[i, text_col], src_of[i],
                                        df.at[j, text_col], src_of[j]))

    totals = collections.Counter(src_of.values())
    count = pd.DataFrame(0, index=sources, columns=sources, dtype=int)
    for i in df.index:
        a = src_of[i]
        for b in hits[i]:
            count.at[a, b] += 1
    frac = count.div(pd.Series(totals).reindex(sources), axis=0).round(4)

    # verdict: any off-diagonal cross-source overlap above 5% is worth a look
    off = frac.where(~np.eye(len(sources), dtype=bool))
    worst = off.max().max()
    if pd.isna(worst) or worst < 0.05:
        verdict = ("GO", f"max cross-source overlap {0 if pd.isna(worst) else worst:.1%} "
                         f"(< 5%) — datasets are distinct enough.")
    else:
        a_b = off.stack().idxmax()
        verdict = ("INVESTIGATE",
                   f"{a_b[0]}->{a_b[1]} overlap {worst:.1%} (>= 5%) — possible "
                   f"shared/near-duplicate prompts inflating transport. Inspect "
                   f"examples; consider swapping a backup source.")

    return {
        "overlap_frac": frac,
        "overlap_count": count,
        "examples": cross_pairs[:n_examples],
        "verdict": verdict,
        "totals": dict(totals),
    }


def print_report(audit):
    """Pretty-print the audit dict."""
    print("Per-source counts:", audit["totals"])
    print("\nCross-source near-duplicate overlap (fraction of ROW source"
          " with a dup in COLUMN source):")
    print(audit["overlap_frac"].to_string())
    print("\nExample cross-source near-duplicate pairs:")
    for a_txt, a_src, b_txt, b_src in audit["examples"]:
        print(f"  [{a_src}] {a_txt[:90]!r}")
        print(f"  [{b_src}] {b_txt[:90]!r}")
        print("  " + "-" * 60)
    v, reason = audit["verdict"]
    print(f"\nVERDICT: {v} — {reason}")
