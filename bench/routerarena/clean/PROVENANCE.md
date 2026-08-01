# Data provenance & compliance manifest — Chuzom clean router

**Claim:** no component of this router is trained, fit, tuned, or keyed on
RouterArena data, on the academic benchmarks RouterArena is assembled from, or on
any per-query/per-category RouterArena outcome. The router's one tunable (the
escalation threshold τ) is calibrated exclusively on self-generated data.

## Allowed data sources (the only inputs to any router parameter)

| # | Source | Used for | Why it's clean |
|---|--------|----------|----------------|
| 1 | **Self-generated synthetic prompts** (`synthetic_gen.py`) | calibrating τ, validating classifier | authored/owned by us; regenerable |
| 2 | **Published model metadata** (artificialanalysis.ai, model cards, `model_cost.json`) | pool selection, cost accounting | public knowledge *about models* |
| 3 | **Live per-query model behaviour** (cross-model agreement, self-consistency) | the routing decision itself | computed at inference time; no training data |

## Explicitly EXCLUDED

- RouterArena (any split) and **RouterBench**.
- The academic benchmarks RA is built from, incl. HF mirrors: MMLU, ARC, GSM8K,
  MATH, SQuAD, HumanEval/MBPP, TriviaQA, NarrativeQA, ChessInstruct, WMT,
  SuperGLUE, FinQA, PubMedQA, QANTA, peers.
- Any per-dataset accuracy table, judge/oracle score, or RA prompt template string.

## Note on measurement vs training

Measuring the FROZEN router's accuracy on the public `sub_10` split (which ships
gold answers, per RA's README local-testing workflow) is evaluation, not tuning —
τ was frozen on self-generated data BEFORE any RA prompt was seen and was NOT
adjusted based on sub_10 results. The prohibited act is *fitting a component* to
RA data, which this router does not do.

## Enforcement

1. **`ci_template_guard.sh --strict`** — fails CI on any RA-template literal.
2. **SHA-256 contamination audit** (at submission) — 0 overlap between
   self-generated calibration prompts and RA's 8400+420 (0 by construction).
3. **Shared-evaluator invariance** — `metrics.py`, `compare_router_accuracy.py`,
   `model_inference.py` byte-identical to `origin/main`.
4. **No RA-derived lineage** in policy/registry comments or values.
