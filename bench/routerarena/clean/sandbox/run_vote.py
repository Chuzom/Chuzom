# SPDX-License-Identifier: MIT
"""Step 2 — diverse-vote router.

The 2-model oracle (qwen3-235b OR deepseek-v3.2 correct) = 0.791, far above what
either scores alone (~0.72). That headroom is cross-model DIVERSITY: they miss
different queries. This router harvests it —

  • 3 diverse INSTRUCT voters answer; if >=2 agree → ship the cheapest agreeing
    model's answer (consensus is very likely correct).
  • 3-way split (the genuinely hard queries) → defer to a REASONING model
    (deepseek-r1), whose miss-pattern differs again.

Compliant: models chosen for published diversity/capability, voting is content-
agnostic, tiebreak rule is first-principles. No RA-outcome tuning. Cost follows
RA precedent (only the final chosen model's tokens are charged).
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_ra_mechanism import run, cost_of, robust_extract, RA_PRICE  # noqa: E402

VOTERS = ["qwen/qwen3-235b-a22b-2507", "deepseek/deepseek-v3.2", "deepseek/deepseek-v4-flash"]
TIEBREAK = "deepseek/deepseek-r1"  # reasoning model for hard splits


def route_and_answer(query, call, key):
    ans = []
    for m in VOTERS:
        msg, pt, ct, err = call(m, query, key)
        ans.append((m, msg, robust_extract(msg), pt, ct))
    exts = [a[2] for a in ans if a[2]]
    top, cnt = (Counter(exts).most_common(1)[0] if exts else (None, 0))
    if cnt >= 2:  # majority consensus among diverse voters
        agreeing = [a for a in ans if a[2] == top]
        agreeing.sort(key=lambda a: RA_PRICE.get(a[0], (1, 1))[1])  # cheapest agreeing
        c = agreeing[0]
        return {"chosen_model": c[0], "raw": c[1], "cost": cost_of(c[0], c[3], c[4]),
                "escalated": False, "n_calls": len(VOTERS)}
    # genuine 3-way split → reasoning-model tiebreak
    msg, pt, ct, err = call(TIEBREAK, query, key, max_tokens=2500)
    return {"chosen_model": TIEBREAK, "raw": msg, "cost": cost_of(TIEBREAK, pt, ct),
            "escalated": True, "n_calls": len(VOTERS) + 1}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    run("vote_diverse", route_and_answer, n=a.n, workers=a.workers)
