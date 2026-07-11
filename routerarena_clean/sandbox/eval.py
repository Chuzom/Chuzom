# SPDX-License-Identifier: MIT
"""Sandbox eval harness — runs a router over the PROXY and emits all 6 RA metrics.

Metrics (RouterArena's set):
  1. accuracy            mean correctness (RA official grader)
  2. cost_per_1k / arena cost & the Weighted-Harmonic-Mean arena score
  3. optimality          selection / accuracy / cost ratios vs oracle (needs a
                         per-query per-model label table; else reported as null)
  4. robustness          fraction of queries whose routed TIER is stable under
                         paraphrase/typo perturbation
  5. latency             routing overhead proxy = mean model calls per query

The router-under-test is any callable
    route(query, call_fn) -> RouteResult(chosen_model, answer, cost, escalated, n_calls)
so the same harness scores the current cascade AND the coming live-signal rule.

Nothing here reads RouterArena data. Grading is RA's official metrics.py (imported
read-only by grader.py). Only the self-generated proxy is scored.
"""
from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # routerarena_clean/

from grader import Grader, arena_score, optimality_ratios


@dataclass
class RouteResult:
    chosen_model: str
    answer: str
    cost: float
    escalated: bool
    n_calls: int = 1
    per_model: dict = field(default_factory=dict)  # {model: (correct01, cost)} if known


RouteFn = Callable[[str, Callable[[str, str], str]], RouteResult]


# ── Robustness perturbation (typo / whitespace / light paraphrase) ────────────
_PARAPHRASE = [
    (r"\bCompute\b", "Calculate"), (r"\bWhat is\b", "Find"),
    (r"\bHow many\b", "Count how many"), (r"\bAnswer\b", "Respond"),
]


def perturb(prompt: str, rng) -> str:
    """Apply meaning-preserving surface noise: one paraphrase + a typo + spacing."""
    p = prompt
    pat, repl = rng.choice(_PARAPHRASE)
    p = re.sub(pat, repl, p, count=1)
    # inject a single-char typo into a longish alphabetic word
    words = p.split(" ")
    cand = [i for i, w in enumerate(words) if w.isalpha() and len(w) > 5]
    if cand:
        i = rng.choice(cand)
        w = words[i]
        j = rng.randrange(1, len(w) - 1)
        words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2:]  # swap two middle chars
    p = " ".join(words)
    return p


def _tier(model: str) -> str:
    """Coarse tier label for robustness stability (cheap-ship vs escalated)."""
    return "escalated" if model else "cheap"


def evaluate(proxy: list[dict], route: RouteFn, call_fn, *,
             robustness_sample: int = 40, seed: int = 7) -> dict:
    import random
    rng = random.Random(seed)
    g = Grader()

    records = []
    t0 = time.time()
    for item in proxy:
        res = route(item["prompt"], call_fn)
        acc = g.grade_by_metric(res.answer, item["answer"], item["metric"])
        rec = {
            "id": item["id"], "domain": item["domain"], "difficulty": item["difficulty"],
            "metric": item["metric"], "chosen": res.chosen_model, "escalated": res.escalated,
            "cost": res.cost, "n_calls": res.n_calls, "correct": int(round(acc)),
            "acc": acc, "per_model": res.per_model,
        }
        records.append(rec)
    wall = time.time() - t0

    n = len(records)
    accuracy = sum(r["acc"] for r in records) / n
    cost_per_1k = sum(r["cost"] for r in records) / n * 1000
    arena = arena_score(cost_per_1k, accuracy)
    mean_calls = sum(r["n_calls"] for r in records) / n
    esc_rate = sum(r["escalated"] for r in records) / n

    # optimality only if the label table (per_model) was populated by the router
    have_labels = all(r["per_model"] for r in records)
    optim = optimality_ratios(records) if have_labels else {
        "optimal_selection_ratio": None, "optimal_accuracy_ratio": None,
        "optimal_cost_ratio": None}

    # robustness: re-route a perturbed sample, compare escalation tier stability
    sample = records if n <= robustness_sample else rng.sample(records, robustness_sample)
    by_id = {it["id"]: it for it in proxy}
    stable = 0
    for r in sample:
        orig_tier = _tier(r["chosen"]) if r["escalated"] else "cheap"
        pert = perturb(by_id[r["id"]]["prompt"], rng)
        pres = route(pert, call_fn)
        pert_tier = "escalated" if pres.escalated else "cheap"
        stable += int((("escalated" if r["escalated"] else "cheap")) == pert_tier)
    robustness = stable / len(sample)

    return {
        "n": n,
        "accuracy": round(accuracy, 4),
        "cost_per_1k": round(cost_per_1k, 4),
        "arena_score": round(arena, 4),
        "escalation_rate": round(esc_rate, 3),
        "latency_calls_per_query": round(mean_calls, 3),
        "robustness": round(robustness, 3),
        "optimality": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in optim.items()},
        "wall_seconds": round(wall, 1),
        "_records": records,
    }


if __name__ == "__main__":
    # Structural validation on a DETERMINISTIC mock — no API, no spend.
    import json
    import hashlib
    from proxy_gen import generate_proxy

    proxy = generate_proxy(per_stratum=6)
    gold = {it["prompt"]: it["answer"] for it in proxy}

    def mock_call(model: str, prompt: str) -> str:
        """Deterministic stand-in: 'strong' always right; cheap models right on
        easy items, hash-flaky on hard ones (so the cascade escalates realistically)."""
        # strip perturbation back to a base key when possible; fall back to prompt
        ans = gold.get(prompt)
        if ans is None:  # perturbed prompt — approximate by prefix match
            for k, v in gold.items():
                if k[:20] == prompt[:20]:
                    ans = v
                    break
            ans = ans or "0"
        if "strong" in model:
            return fr"\boxed{{{ans}}}"
        h = int(hashlib.sha1(f"{model}|{prompt}".encode()).hexdigest(), 16)
        right = (h % 100) < 78  # cheap models ~78% right
        return fr"\boxed{{{ans}}}" if right else r"\boxed{ZZ}"

    # Minimal cascade router-under-test: 2 cheap probes agree → cheap; else strong.
    from router_core import extract_answer, answers_agree

    CHEAP = ["cheap-a", "cheap-b"]
    STRONG = "strong-x"
    PRICE = {"cheap-a": 0.05, "cheap-b": 0.05, "strong-x": 1.0}

    def route(query, call_fn):
        ans = {m: call_fn(m, query) for m in CHEAP}
        exts = [extract_answer(a) for a in ans.values()]
        unan, _, _ = answers_agree(exts)
        if unan:
            m = CHEAP[0]
            return RouteResult(m, ans[m], PRICE[m] * 0.001, False, n_calls=2)
        a = call_fn(STRONG, query)
        return RouteResult(STRONG, a, PRICE[STRONG] * 0.001, True, n_calls=3)

    report = evaluate(proxy, route, mock_call)
    report.pop("_records")
    print(json.dumps(report, indent=2))
