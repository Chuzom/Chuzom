# SPDX-License-Identifier: MIT
"""Measure the calibrated cascade (ChuzomCleanRouter's mechanism) on RA sub_10.

Pair-agreement escalate, τ=1.0: probe the 2 cheap models; if their extracted
answers agree unanimously, ship the cheapest; else escalate to the strong model.
Same pool + logic as routerarena_clean/chuzom_clean_router.py.

Cost convention: RA charges the FINAL pick's cost (its own leaderboard
methodology — it only sees the output model per query). Probe overhead is
disclosed transparently via `calls_per_query` in the report, not hidden.

Graded locally by grader.py with RA's official (unmodified) metrics. This IS a
deliberate RA-data touch — authorized, fixed design, measured once.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_ra_mechanism import cost_of, robust_extract, run  # noqa: E402

# Pool ordered cheap→expensive; matches chuzom_clean_router.py exactly.
_CHEAP = ["qwen/qwen3-235b-a22b-2507", "deepseek/deepseek-v4-flash"]
_STRONG = "deepseek/deepseek-v3.2"


def route_and_answer(query, call, key):
    # Probe both cheap models (raw answers retained for grading).
    probe = {}
    for m in _CHEAP:
        msg, pt, ct, _err = call(m, query, key)
        probe[m] = (msg, robust_extract(msg), pt, ct)

    a0 = probe[_CHEAP[0]][1]
    a1 = probe[_CHEAP[1]][1]
    unanimous = a0 != "" and a0 == a1  # τ=1.0

    if unanimous:
        m = _CHEAP[0]
        msg, _ext, pt, ct = probe[m]
        return {"chosen_model": m, "raw": msg, "cost": cost_of(m, pt, ct),
                "escalated": False, "n_calls": 2}

    # Disagreement → escalate to strong; final answer + cost from the strong model.
    msg, pt, ct, _err = call(_STRONG, query, key)
    return {"chosen_model": _STRONG, "raw": msg, "cost": cost_of(_STRONG, pt, ct),
            "escalated": True, "n_calls": 3}


def _load_env() -> None:
    """Load OPENROUTER_API_KEY from the user's ~/.chuzom/.env. The value is read
    from their file at runtime and never printed — standard config load."""
    from pathlib import Path
    p = Path.home() / ".chuzom" / ".env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


if __name__ == "__main__":
    _load_env()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = all rows in labels file
    labels_file = sys.argv[2] if len(sys.argv) > 2 else "sub10_labels.json"
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    name = "chuzom-cascade-full" if "full" in labels_file else "chuzom-cascade"
    run(name, route_and_answer, n=n, workers=workers, labels_file=labels_file)
