# SPDX-License-Identifier: MIT
"""Calibrate the escalation threshold τ on self-generated data only.

Runs the cascade over the synthetic corpus, sweeps τ, and picks the value that
maximizes the REAL RouterArena arena-score formula. No RA data is touched.
Pool-agnostic: pass a `call_fn(model, prompt) -> str`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from router_core import Pool, answers_agree, extract_answer  # noqa: F401


def arena_score(cost_per_1k, accuracy, beta=0.1, c_max=200.0, c_min=0.0044):
    """Exact RouterArena formula (llm_evaluation/run.py:compute_arena_score)."""
    cost = max(c_min, min(cost_per_1k, c_max))
    c_i = (math.log2(c_max) - math.log2(cost)) / (math.log2(c_max) - math.log2(c_min))
    return ((1 + beta) * accuracy * c_i) / (beta * accuracy + c_i)


def grade(ext, gold):
    ext = ext.strip().lower()
    try:
        return abs(float(ext) - float(gold)) < 1e-6
    except ValueError:
        return ext == gold.lower()


@dataclass
class CostModel:
    """Values are dollars per 1000 queries; the mean over routed queries IS the
    avg $/1k — do NOT rescale by 1000."""
    per_1k: dict

    def cost(self, model):
        return self.per_1k.get(model, 0.10)


def calibrate(records, call_fn, pool: Pool, costs: CostModel, taus=(1.0,)) -> dict:
    probed = []
    for r in records:
        answers = {m: extract_answer(call_fn(m, r["prompt"])) for m in pool.cheap[:2]}
        probed.append({**r, "answers": answers, "strong": None})

    results = {}
    for tau in taus:
        correct = cost_sum = escalated = 0
        for row in probed:
            vals = list(row["answers"].values())
            unanimous, majority, frac = answers_agree(vals)
            trust = unanimous if tau >= 1.0 else frac >= tau
            if trust:
                chosen = pool.cheap[0]
                ok = grade(row["answers"][chosen], row["answer"])
            else:
                if row["strong"] is None:
                    row["strong"] = extract_answer(call_fn(pool.strong, row["prompt"]))
                chosen = pool.strong
                ok = grade(row["strong"], row["answer"])
                escalated += 1
            correct += ok
            cost_sum += costs.cost(chosen)
        n = len(probed)
        acc = correct / n
        cost_1k = cost_sum / n  # per_1k values already in $/1k; mean is the avg $/1k
        results[tau] = {
            "accuracy": round(acc, 4), "cost_per_1k": round(cost_1k, 4),
            "escalation_rate": round(escalated / n, 3),
            "arena_proxy": round(arena_score(cost_1k, acc), 4),
        }
    return results
