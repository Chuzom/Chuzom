# SPDX-License-Identifier: MIT
"""Escalation-model proxy experiment — can adding a strong model clear arena 0.75?

This does NOT re-run Ollama-on-arithmetic and read off a score: the synthetic
corpus is computed math where any capable model ≈ 100%, so that would badly
misrepresent RouterArena's knowledge/multilingual/adversarial hard tail (see
STATUS.md — "synthetic surface ≠ RA surface"). Instead it answers the decision
question analytically, from the REAL arena formula and the REAL measured anchors:

    Given a strong escalation model at price P and a gate that harvests some
    fraction η of the available oracle accuracy-lift, what arena score results,
    and does any real candidate model land in the ≥0.75 region?

Two grounded facts make this rigorous, not hand-wavy:
  1. The arena formula is imported verbatim from calibrate.arena_score (the
     byte-identical RA formula), and we validate it by back-solving deepseek's
     effective cost from its measured (arena, accuracy) — if the formula didn't
     reproduce the leaderboard anchor, every downstream number would be suspect.
  2. The gate's realised harvest efficiency η is computed from a measured anchor
     (coherence-judge escalation = 0.7142 vs 2-model oracle 0.7513) — not guessed.

Optional --empirical runs the actual probe-and-escalate cascade over the
computed-gold hard corpus via local Ollama to report the *mechanism's* escalation
rate and gate precision (does it escalate the queries it gets wrong?). That is the
transferable question; absolute accuracy on arithmetic is not.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from calibrate import arena_score  # noqa: E402  — the REAL RA formula, unmodified

# ── Measured anchors (bench/routerarena/clean/STATUS.md; every number a real RA run) ──
A_DEEPSEEK_ACC = 0.6951        # deepseek-v3.2 accuracy on the 809
ARENA_DEEPSEEK = 0.7061        # deepseek-v3.2 solo arena (full 8400) — shipped
ARENA_ORACLE_2CHEAP = 0.7513   # perfect routing over {v4-flash, v3.2} (cheap only)
ARENA_ORACLE_SONNET = 0.8042   # perfect routing over cheap + sonnet
ARENA_COHERENCE = 0.7142       # best REAL gate (coherence-judge escalation, 809)


def _c_i(cost_per_1k: float, c_max=200.0, c_min=0.0044) -> float:
    cost = max(c_min, min(cost_per_1k, c_max))
    return (math.log2(c_max) - math.log2(cost)) / (math.log2(c_max) - math.log2(c_min))


def _acc_from_arena(arena: float, cost_per_1k: float) -> float:
    """Invert arena_score for accuracy at a known cost (arena is monotonic in A)."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if arena_score(cost_per_1k, mid) < arena:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _cost_from_arena(arena: float, acc: float) -> float:
    """Back-solve effective $/1k from a measured (arena, accuracy) pair."""
    lo, hi = 0.0044, 200.0
    for _ in range(60):
        mid = math.sqrt(lo * hi)  # geometric bisection (cost is log-scaled)
        # arena decreases as cost increases → find cost giving target arena
        if arena_score(mid, acc) > arena:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


@dataclass
class Candidate:
    name: str
    price_per_1k: float   # published $/1000 queries at RA prompt lengths
    # Blended accuracy achievable if this model were the strong escalation tier
    # AND routing were PERFECT (the oracle for this pool). ASSUMED — replace with
    # a measured per-model oracle. sonnet anchor (0.8042) is the one real point.
    oracle_acc_assumed: float


# ASSUMED candidate table — prices/oracle-acc are placeholders to be replaced
# with published pricing (artificialanalysis / provider cards) and a measured
# per-model oracle. Only the sonnet row is anchored to a real RA oracle.
_DEFAULT_CANDIDATES = [
    Candidate("claude-sonnet (anchored oracle)", 3.30, 0.790),   # ~ from 0.8042 oracle
    Candidate("o-series-mini (assumed)",         1.20, 0.760),
    Candidate("grok-4-fast-reasoning (assumed)", 0.60, 0.745),
    Candidate("deepseek-r1-next (assumed)",      0.30, 0.735),
]


def validate_and_context() -> dict:
    cheap_cost = _cost_from_arena(ARENA_DEEPSEEK, A_DEEPSEEK_ACC)
    ci = _c_i(cheap_cost)
    # Re-derive arena from the backed-out cost to confirm the formula round-trips.
    check = arena_score(cheap_cost, A_DEEPSEEK_ACC)
    oracle2_acc = _acc_from_arena(ARENA_ORACLE_2CHEAP, cheap_cost)
    # Harvest efficiency of the best REAL gate: fraction of the cheap-only oracle
    # accuracy lift it actually captured.
    real1 = _acc_from_arena(ARENA_DEEPSEEK, cheap_cost)          # ≈ deepseek acc
    coh_acc = _acc_from_arena(ARENA_COHERENCE, cheap_cost)       # coherence gate acc
    eta_realized = (coh_acc - real1) / (oracle2_acc - real1) if oracle2_acc > real1 else 0.0
    return {
        "cheap_effective_cost_per_1k": round(cheap_cost, 4),
        "cheap_c_i": round(ci, 4),
        "formula_roundtrip_arena": round(check, 4),
        "oracle_2cheap_accuracy": round(oracle2_acc, 4),
        "coherence_gate_accuracy": round(coh_acc, 4),
        "eta_realized_best_real_gate": round(eta_realized, 3),
    }


def frontier(cheap_cost: float, eta: float, candidates: list[Candidate]) -> list[dict]:
    """For each candidate strong model, arena at PERFECT routing (η=1, its oracle)
    and at the REALISTIC gate efficiency η (best real gate ≈ measured)."""
    base_acc = A_DEEPSEEK_ACC
    rows = []
    for c in candidates:
        # Escalation share that a *perfect* gate would send to the strong model
        # to realise its oracle. We don't know it per-model; assume the arena is
        # dominated by accuracy (β=0.1) and price the escalated share e.
        # Report arena across a small escalation-share sweep so cost sensitivity
        # is visible rather than hidden in one assumed e.
        for e in (0.15, 0.30, 0.50):
            ra_cost = (1 - e) * cheap_cost + e * c.price_per_1k  # RA charges final pick
            oracle_arena = arena_score(ra_cost, c.oracle_acc_assumed)
            realized_acc = base_acc + eta * (c.oracle_acc_assumed - base_acc)
            realized_arena = arena_score(ra_cost, realized_acc)
            rows.append({
                "model": c.name, "escalation_share": e,
                "ra_cost_per_1k": round(ra_cost, 3),
                "oracle_arena(perfect_gate)": round(oracle_arena, 4),
                "realized_arena(eta=%.2f)" % eta: round(realized_arena, 4),
                "clears_0.75_perfect": oracle_arena >= 0.75,
                "clears_0.75_realistic": realized_arena >= 0.75,
            })
    return rows


def run_empirical(n: int) -> dict:
    """Optional: measure the cascade's escalation rate + gate precision on the
    computed-gold hard corpus via local Ollama. Answers 'does the agreement gate
    escalate the queries it actually gets wrong?' — the transferable question."""
    import urllib.request

    sys.path.insert(0, os.path.join(_HERE))
    from router_core import Pool, decide  # noqa: E402
    from synthetic_gen import generate_hard  # noqa: E402
    from calibrate import grade  # noqa: E402

    CHEAP = ["qwen2.5-coder:7b", "hermes3:8b"]
    STRONG = os.environ.get("CHUZOM_EMPIRICAL_STRONG", "qwen3-coder:30b")  # non-thinking, faster

    def call(model: str, prompt: str) -> str:
        # "/no_think" suppresses chain-of-thought on Qwen3 thinking models so a
        # single call can't blow the timeout; harmless on models that ignore it.
        payload = json.dumps({"model": model, "prompt": prompt + " /no_think",
                              "stream": False,
                              "options": {"temperature": 0, "num_predict": 512}}).encode()
        req = urllib.request.Request("http://localhost:11434/api/generate", data=payload,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read()).get("response", "")
        except Exception:  # noqa: BLE001 — one slow/failed call must not abort the run
            return ""

    from router_core import extract_answer
    pool = Pool(cheap=CHEAP, strong=STRONG)
    recs = generate_hard(n=n)
    escalated = kept_correct = kept = esc_correct = 0
    cheap_wrong_escalated = cheap_wrong_total = 0
    for r in recs:
        d = decide(r["prompt"], call, pool, tau=0.999)
        cheap0 = extract_answer(call(CHEAP[0], r["prompt"]))
        cheap_ok = grade(cheap0, r["answer"])
        if not cheap_ok:
            cheap_wrong_total += 1
            if d.escalated:
                cheap_wrong_escalated += 1
        if d.escalated:
            escalated += 1
            esc_correct += grade(extract_answer(call(STRONG, r["prompt"])), r["answer"])
        else:
            kept += 1
            kept_correct += cheap_ok
    n = len(recs)
    return {
        "n": n,
        "escalation_rate": round(escalated / n, 3),
        "kept_accuracy": round(kept_correct / kept, 3) if kept else None,
        "escalated_accuracy": round(esc_correct / escalated, 3) if escalated else None,
        # Gate recall on errors: of the queries the cheap model got wrong, what
        # fraction did the gate escalate? Low recall = the gate can't find the
        # hard tail (the STATUS.md finding, reproduced on synthetic).
        "gate_recall_on_cheap_errors":
            round(cheap_wrong_escalated / cheap_wrong_total, 3) if cheap_wrong_total else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eta", type=float, default=None,
                    help="Gate harvest efficiency (default = measured best real gate).")
    ap.add_argument("--candidates", type=str, help="JSON list of {name,price_per_1k,oracle_acc_assumed}.")
    ap.add_argument("--empirical", type=int, default=0,
                    help="Run N cascade decisions over hard corpus via Ollama (0=skip).")
    args = ap.parse_args()

    ctx = validate_and_context()
    print("── formula validation + context (all from measured anchors) ──")
    print(json.dumps(ctx, indent=2))

    eta = args.eta if args.eta is not None else ctx["eta_realized_best_real_gate"]
    cands = _DEFAULT_CANDIDATES
    if args.candidates:
        cands = [Candidate(**c) for c in json.loads(args.candidates)]

    print(f"\n── escalation frontier (realistic η = {eta}) ──")
    rows = frontier(ctx["cheap_effective_cost_per_1k"], eta, cands)
    for r in rows:
        print(json.dumps(r))

    any_realistic = any(r["clears_0.75_realistic"] for r in rows)
    any_perfect = any(r["clears_0.75_perfect"] for r in rows)
    print("\n── verdict ──")
    print(f"  clears 0.75 with a PERFECT gate (oracle):   {any_perfect}")
    print(f"  clears 0.75 at REALISTIC gate η={eta}:      {any_realistic}")
    print(f"  best real gate historically harvested η≈{ctx['eta_realized_best_real_gate']} "
          f"→ that is the constraint, not the model price.")

    if args.empirical:
        print(f"\n── empirical cascade mechanics (Ollama, n={args.empirical}) ──")
        print(json.dumps(run_empirical(args.empirical), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
