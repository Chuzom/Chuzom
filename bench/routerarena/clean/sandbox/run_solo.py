# SPDX-License-Identifier: MIT
"""Single-model baseline over RA sub_10 / full — route EVERYTHING to one model.

No routing, no classifier, zero fitted components → nothing for a maintainer to
challenge (the lowest-risk compliant submission shape). Motivated by the measured
finding that qwen3-235b is the highest arena-VALUE model in the pool.

Usage: python run_solo.py <n> <labels_file> <workers> <model>
       (defaults: full sub_10, qwen/qwen3-235b-a22b-2507)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_ra_mechanism import cost_of, run  # noqa: E402

_MODEL = "qwen/qwen3-235b-a22b-2507"


def _make(model):
    def route_and_answer(query, call, key):
        msg, pt, ct, _err = call(model, query, key)
        return {"chosen_model": model, "raw": msg, "cost": cost_of(model, pt, ct),
                "escalated": False, "n_calls": 1}
    return route_and_answer


def _load_env() -> None:
    p = Path.home() / ".chuzom" / ".env"
    if p.is_file():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


if __name__ == "__main__":
    _load_env()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    labels_file = sys.argv[2] if len(sys.argv) > 2 else "sub10_labels.json"
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    model = sys.argv[4] if len(sys.argv) > 4 else _MODEL
    name = "solo-" + model.split("/")[-1]
    run(name, _make(model), n=n, workers=workers, labels_file=labels_file)
