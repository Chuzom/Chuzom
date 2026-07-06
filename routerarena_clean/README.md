# Chuzom clean router — RouterArena submission (benchmark-agnostic)

A confidence-gated cascade that routes on **live model behaviour**, not on
RouterArena prompt templates. Built to clear **arena score > 0.75** with **zero**
use of RouterArena data or the academic benchmarks it is assembled from.

## Why this exists

Every prior Chuzom RA submission (legacy v0.5.2 and the withdrawn PR #158) was
rejected/withdrawn for fitting to RouterArena's injected prompt templates. This
is a clean-break redesign: it never inspects prompt wrappers.

## How it routes

```
query → probe 2 cheapest models → answers AGREE?  ── yes → ship cheapest
                                          │
                                          └─ no  → escalate to strong model
```

The gate is **label-free**: cross-model agreement predicts correctness with no
ground-truth labels. Validated on self-generated synthetic data — separation
`P(correct|agree) − P(correct|disagree) = 1.00`, cascade accuracy 95.8% at 29%
escalation (71% of traffic stays on the cheapest model).

## Files

| File | Role | Ships to RA? |
|------|------|:---:|
| `router_core.py` | pure cascade logic: structural classifier, generic extractor, confidence gate | ✅ |
| `chuzom_clean_router.py` | thin `BaseRouter` adapter + OpenRouter `call_fn` | ✅ |
| `synthetic_gen.py` | self-generated calibration corpus (computed ground truth) | dev |
| `calibrate.py` | τ sweep vs the real arena-score formula | dev |
| `ci_template_guard.sh` | **fails CI** if any RA-template literal appears in shipped source | CI |
| `PROVENANCE.md` | data-source manifest + compliance claims | PR |

## Compliance in one line

The only tunable (escalation threshold τ) is fit on self-generated data; the
routing decision uses live model agreement; `ci_template_guard.sh --strict`
structurally forbids RA-template literals in the shipped router. See
[`PROVENANCE.md`](./PROVENANCE.md).

## To produce a submission (requires `OPENROUTER_API_KEY`)

1. `bash ci_template_guard.sh --strict` — must be green.
2. `python calibrate.py` against the real pool → freeze τ in `chuzom_clean_router.py`.
3. Generate RA predictions in ONE cold pass (no score-peeking).
4. SHA-256 contamination audit: 0 overlap vs RA's 8400+420 prompts.
5. Confirm `metrics.py` / `compare_router_accuracy.py` byte-identical to `origin/main`.
6. Open PR, post `/evaluate`. **Do not** iterate against the returned score.
