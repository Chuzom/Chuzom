# SPDX-License-Identifier: MIT
"""Approach #4 — abstention/hedge-triggered escalation.

The cheap base answers once. If it HEDGES (refuses, says it's unsure, returns
empty, or gives no usable answer) → escalate to the stronger model; else ship
cheap. A cheap model that can't do a task often hedges, so this catches silent
failures without any calibration data.

Compliant: base/strong from published general benchmarks; the hedge patterns are
generic self-doubt phrases, not RA-specific. Cost = final chosen model's tokens.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_ra_mechanism import run, cost_of, robust_extract, MECH_BASE, MECH_STRONG  # noqa: E402

_HEDGE = re.compile(
    r"\bi'?m not sure\b|\bi am not sure\b|\bi cannot\b|\bi can'?t\b|\bas an ai\b|"
    r"\bi don'?t (?:have|know)\b|\bunable to\b|\bnot enough (?:information|context)\b|"
    r"\bcannot determine\b|\binsufficient (?:information|data)\b|\bit depends\b|"
    r"\bno (?:clear |definitive )?answer\b|\bcould not\b", re.I)


def is_hedge(msg: str) -> bool:
    if not msg or not msg.strip():
        return True
    if _HEDGE.search(msg):
        return True
    # no extractable answer at all → treat as a silent failure worth escalating
    if not robust_extract(msg):
        return True
    return False


def route_and_answer(query, call, key):
    msg, pt, ct, err = call(MECH_BASE, query, key)
    if err or is_hedge(msg):
        msg2, pt2, ct2, err2 = call(MECH_STRONG, query, key)
        return {"chosen_model": MECH_STRONG, "raw": msg2,
                "cost": cost_of(MECH_STRONG, pt2, ct2), "escalated": True, "n_calls": 2}
    return {"chosen_model": MECH_BASE, "raw": msg,
            "cost": cost_of(MECH_BASE, pt, ct), "escalated": False, "n_calls": 1}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    run("hedge_4", route_and_answer, n=a.n, workers=a.workers)
