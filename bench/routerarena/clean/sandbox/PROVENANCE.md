# Sandbox provenance & compliance posture

This directory is the **offline refinement sandbox** for the Chuzom RouterArena
submission. Its entire purpose is to let us tune and measure the router **without
ever fitting on RouterArena data** — the line that disqualified PR-155 (see the
maintainer `yl231`'s review, and `.claude` memory `ra-compliance-label-provenance`).

## The three hard rules (each independently disqualifying in PR-155)

1. **Label provenance.** No router component may be fit/tuned on RA-derived
   supervision (per-dataset accuracy, gpt-4o-mini judge scores, oracle entries).
2. **Evaluator immutability.** `llm_evaluation/metrics.py` (and
   `compare_router_accuracy.py`) must never be modified by a submission.
3. **No RA-outcome routing table.** No per-query/per-category routing table chosen
   from RA outcomes.

## How this sandbox satisfies them

| File | Role | Compliance |
|---|---|---|
| `grader.py` | scores predictions | **imports** RA `metrics.py` read-only; `assert_evaluator_unmodified()` pins its sha256 (`e7f9e556…`, verified == RouteWorks/main blob `014ddc76`) and fails on drift. Arena + optimality math is native and reproduces RA's official arena to 4 dp (0.7424, 0.698). |
| `proxy_gen.py` | the refinement corpus | **100% self-generated, computed answers.** No RA split, no RA's 23 source datasets, no RouterBench, no RA accuracy/judge/oracle. Ground truth is owned by us. Seeded + regenerable. |

## Proxy corpus (`proxy_gen.generate_proxy`)

- Regenerate: `python3 proxy_gen.py` (seed `20260706`).
- Shape mirrors RA **structurally** (general domains × 3 Bloom difficulties ×
  metric types {math, mcq, exact}) so proxy-arena tracks RA-arena — **without
  copying** any RA content. Domain labels are our own 9-axis taxonomy, NOT RA's
  44 categories.
- **Documented gaps (not hidden):**
  - Free-text generation / translation (METEOR) is under-covered — a computed
    gold reference can't be self-generated for it. The live-signal escalation
    rule is domain-general, so threshold calibration doesn't depend on it.
  - Domain balance is uneven and some MCQ distractors are weak — realism
    refinements tracked for v2, not compliance issues.

## Refinement discipline

- The router is tuned **only** against proxy metrics from `grader.py`.
- The real RA set is a **locked one-shot test** (`measure_ra_once.py`, P0.4):
  touched exactly once to produce the submission prediction file; never in a
  tune-measure-retune loop.
- Before any resubmission: `git checkout upstream/main -- llm_evaluation/metrics.py
  router_inference/compare_router_accuracy.py` (the latter is currently modified
  on the fork and must be reverted — PR-155 rule #2).
