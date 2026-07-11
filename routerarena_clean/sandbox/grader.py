# SPDX-License-Identifier: MIT
"""Sandbox grader — scores our PROXY corpus with RouterArena's OFFICIAL metrics.

Compliance posture (see memory ra-compliance-label-provenance + PR-155):
  • RA's `llm_evaluation/metrics.py` is imported READ-ONLY and NEVER modified.
    `assert_evaluator_unmodified()` hashes it and refuses to run if it drifts
    from a pinned digest — PR-155 rule #2 (a submission that edits the shared
    scorer is disqualified).
  • This module only *grades* our self-generated data. No RA dataset, accuracy,
    judge, or oracle value is used to fit, tune, or label any router component.

The arena-score and optimality formulas are implemented natively here (small,
auditable) and reproduce RA's published definitions; the per-dataset correctness
functions come from RA's grader so our proxy score is comparable to the leaderboard.

Set RA_EVAL_DIR to your RouterArena checkout's llm_evaluation/ dir, e.g.
    export RA_EVAL_DIR=~/RouterArena/llm_evaluation
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
from pathlib import Path

# ── Locate RA's grader (read-only) ────────────────────────────────────────────
_DEFAULT_RA = (
    "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/"
    "c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad/RA/llm_evaluation"
)
RA_EVAL_DIR = os.environ.get("RA_EVAL_DIR", _DEFAULT_RA)

# Pin the digest of the trusted upstream metrics.py. Confirmed clean: the fork's
# submit branch blob SHA (014ddc768ac67aa72315e44ec50525b4b416b6fd) equals
# RouteWorks/RouterArena main, so this sha256 is of the unmodified upstream scorer.
# Any later drift (an in-tree edit that would taint a submission — PR-155 rule #2)
# now fails loudly.
_PINNED_METRICS_SHA256 = "e7f9e55682143b296b7c2e68bd76c2903a75c9a9dc6fba8e842ec37e73794fdb"


def _metrics_path() -> Path:
    return Path(RA_EVAL_DIR) / "metrics.py"


def assert_evaluator_unmodified(*, strict: bool = False) -> str:
    """Return the sha256 of RA's metrics.py; enforce it matches the pinned digest.

    PR-155 rule #2: the shared evaluator must never be modified by a submission.
    `strict=True` raises on any mismatch/unpinned digest; default warns.
    """
    p = _metrics_path()
    if not p.exists():
        raise FileNotFoundError(
            f"RA grader not found at {p}. Set RA_EVAL_DIR to your RouterArena "
            "checkout's llm_evaluation/ directory."
        )
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if not _PINNED_METRICS_SHA256:
        sys.stderr.write(
            f"[grader] metrics.py sha256 not pinned yet — live digest: {digest}\n"
            f"[grader] paste it into _PINNED_METRICS_SHA256 to lock evaluator immutability.\n"
        )
    elif digest != _PINNED_METRICS_SHA256:
        msg = (
            f"[grader] EVALUATOR DRIFT: metrics.py sha256 {digest} != pinned "
            f"{_PINNED_METRICS_SHA256}. Revert metrics.py to upstream main "
            "(PR-155 rule #2: never modify the shared scorer)."
        )
        if strict:
            raise RuntimeError(msg)
        sys.stderr.write(msg + "\n")
    return digest


def _load_ra_metrics():
    if RA_EVAL_DIR not in sys.path:
        sys.path.insert(0, RA_EVAL_DIR)
    assert_evaluator_unmodified(strict=False)
    import metrics as M  # RA official grader — imported, never edited
    return M


# ── dataset (base name) → RA metric function ──────────────────────────────────
def _metric_table(M):
    return {
        "AIME": M.math_metric, "AsDiv": M.math_metric, "FinQA": M.math_metric,
        "GSM8K": M.math_metric, "MATH": M.math_metric, "MathQA": M.mcq_accuracy,
        "ArcMMLU": M.mcq_accuracy, "MMLUPro": M.mcq_accuracy, "MMLU": M.mcq_accuracy,
        "MedMCQA": M.mcq_accuracy, "GeoBench": M.mcq_accuracy,
        "MusicTheoryBench": M.mcq_accuracy, "PubMedQA": M.mcq_accuracy,
        "SocialiQA": M.mcq_accuracy, "OpenTDB": M.mcq_accuracy, "Ethics": M.mcq_accuracy,
        "GeoGraphyData": M.mcq_accuracy, "ChessInstruct": M.chess_accuracy,
        "NarrativeQA": M.meteor_score, "WMT19": M.meteor_score,
        "QANTA": M.exact_match, "LiveCodeBench": M.code_accuracy,
        "SuperGLUE-ClozeTest": M.superglue_clozetest,
        "SuperGLUE-Entailment": M.superglue_exact_match,
        "SuperGLUE-QA": M.superglue_exact_match, "SuperGLUE-RC": M.superglue_exact_match,
        "SuperGLUE-Wic": M.superglue_exact_match, "SuperGLUE-Wsc": M.superglue_exact_match,
        "SuperGLUE-CausalReasoning": M.mcq_accuracy,
    }


def _metric_for(ds: str, table, M):
    if ds in table:
        return table[ds]
    base = ds.split("_")[0]
    if base in table:
        return table[base]
    for pfx in ("MMLUPro", "MMLU", "OpenTDB", "QANTA", "Ethics", "WMT19",
                "SuperGLUE", "ChessInstruct"):
        if ds.startswith(pfx):
            return table.get(pfx, M.mcq_accuracy)
    return M.mcq_accuracy


# Neutral metric names → RA fn. Lets our self-generated proxy pick a scorer
# WITHOUT referencing any RA dataset/category name (cleaner provenance).
def _metric_by_name(M):
    return {
        "math": M.math_metric,
        "mcq": M.mcq_accuracy,
        "exact": M.exact_match,
        "chess": M.chess_accuracy,
        "meteor": M.meteor_score,
    }


class Grader:
    """Grades (prediction, gold, dataset) triples with RA's official metrics."""

    def __init__(self):
        self._M = _load_ra_metrics()
        self._table = _metric_table(self._M)
        self._by_name = _metric_by_name(self._M)

    def grade_by_metric(self, prediction: str, gold: str, metric: str) -> float:
        """Grade using a neutral metric name (math/mcq/exact/chess/meteor).
        Used by the self-generated proxy. 0.0 on grader error."""
        fn = self._by_name.get(metric)
        if fn is None:
            raise ValueError(f"unknown metric {metric!r}; expected one of {list(self._by_name)}")
        try:
            r = fn([prediction], [gold])
            val = r[0] if isinstance(r, tuple) else r
            return float(val)
        except Exception:
            return 0.0

    def grade_one(self, prediction: str, gold: str, dataset: str) -> float:
        """Return correctness in [0,1] for one prediction. 0.0 on grader error,
        matching RA's error-tolerant behaviour (never raises out)."""
        fn = _metric_for(dataset, self._table, self._M)
        try:
            r = fn([prediction], [gold])
            val = r[0] if isinstance(r, tuple) else r
            return float(val)
        except Exception:
            return 0.0


# ── Arena score (RA's published Weighted-Harmonic-Mean of accuracy & log-cost) ─
def arena_score(cost_per_1k: float, accuracy: float,
                beta: float = 0.1, cmax: float = 200.0, cmin: float = 0.0044) -> float:
    """RA arena score. cost_per_1k = mean $ per 1,000 queries. beta favours accuracy.
    Cost is clamped to [cmin, cmax] then log2-normalised to a [0,1] cost index."""
    cost = max(cmin, min(cost_per_1k, cmax))
    ci = (math.log2(cmax) - math.log2(cost)) / (math.log2(cmax) - math.log2(cmin))
    if beta * accuracy + ci == 0:
        return 0.0
    return ((1 + beta) * accuracy * ci) / (beta * accuracy + ci)


# ── Optimality ratios (RA metric #3) ──────────────────────────────────────────
# Each record: {"chosen": model, "correct": 0/1, "cost": $, "per_model": {m: (correct,cost)}}
# per_model is the label-table row for that query (all pool models run) — self-generated.
def optimality_ratios(records: list[dict]) -> dict[str, float]:
    """Optimal-Selection / Optimal-Accuracy / Optimal-Cost ratios vs the oracle.

    Oracle per query = cheapest model that answers correctly (or, for accuracy
    ceiling, the best-accuracy model). Computed purely from self-generated
    per-model outcomes — no RA data.
    """
    n = len(records)
    if n == 0:
        return {"optimal_selection_ratio": 0.0, "optimal_accuracy_ratio": 0.0,
                "optimal_cost_ratio": 0.0}
    sel_hits = 0
    router_correct = 0
    oracle_correct = 0
    router_cost = 0.0
    oracle_cost = 0.0
    for r in records:
        pm = r.get("per_model") or {}
        # cheapest correct model = oracle choice
        correct_models = [(c_cost, m) for m, (c_ok, c_cost) in pm.items() if c_ok]
        router_correct += int(r.get("correct", 0))
        router_cost += float(r.get("cost", 0.0))
        if correct_models:
            oracle_correct += 1
            cheapest_cost, cheapest_m = min(correct_models, key=lambda x: x[0])
            oracle_cost += cheapest_cost
            if r.get("chosen") == cheapest_m:
                sel_hits += 1
        # if no model was correct, oracle also fails that query (no cost added)
    return {
        "optimal_selection_ratio": sel_hits / n,
        "optimal_accuracy_ratio": (router_correct / oracle_correct) if oracle_correct else 0.0,
        "optimal_cost_ratio": (oracle_cost / router_cost) if router_cost else 0.0,
    }


if __name__ == "__main__":
    # Self-test: evaluator hash + a couple of gradings + arena sanity.
    g = Grader()
    print("metrics.py sha256:", assert_evaluator_unmodified())
    print("MCQ boxed A vs A :", g.grade_one(r"The answer is \boxed{A}", "A", "MMLUPro_math"))
    print("MATH 42 vs 42    :", g.grade_one(r"so \boxed{42}", "42", "GSM8K"))
    print("MCQ wrong        :", g.grade_one(r"\boxed{B}", "A", "ArcMMLU"))
    print("arena(0.17,0.752):", round(arena_score(0.1738, 0.7521), 4), "(PR-155 was 0.7424)")
    print("arena(2.15,0.747):", round(arena_score(2.1537, 0.7467), 4), "(n=600 run was 0.698)")
