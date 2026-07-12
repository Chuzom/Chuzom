# SPDX-License-Identifier: MIT
"""Approach #2 — self-consistency deferral.

Sample the cheap base model K times (temp>0). If its own answers agree (majority)
→ ship cheap; else escalate to the stronger model. Same-model sampling makes the
agreement signal format-consistent (fixes the cross-model extraction failure).

Cost follows RA precedent: only the FINAL chosen answer's tokens are charged
(the extra samples are production-only, disclosed). Compliant: base/strong chosen
from published general benchmarks; threshold is first-principles (majority).
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_ra_mechanism import run, cost_of, robust_extract, MECH_BASE, MECH_STRONG  # noqa: E402

K = 3


def route_and_answer(query, call, key):
    samples = []
    for _ in range(K):
        msg, pt, ct, err = call(MECH_BASE, query, key, temperature=0.7)
        samples.append((msg, robust_extract(msg), pt, ct))
    exts = [e for _, e, _, _ in samples if e]
    agree, top = False, None
    if exts:
        top, cnt = Counter(exts).most_common(1)[0]
        agree = cnt >= (K // 2 + 1)  # majority of K
    if agree:
        shipped = next(s for s in samples if s[1] == top)
        return {"chosen_model": MECH_BASE, "raw": shipped[0],
                "cost": cost_of(MECH_BASE, shipped[2], shipped[3]),
                "escalated": False, "n_calls": K}
    msg, pt, ct, err = call(MECH_STRONG, query, key, temperature=0.0)
    return {"chosen_model": MECH_STRONG, "raw": msg,
            "cost": cost_of(MECH_STRONG, pt, ct), "escalated": True, "n_calls": K + 1}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    run("selfconsistency_2", route_and_answer, n=a.n, workers=a.workers)
