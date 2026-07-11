# Chuzom clean router — final findings (toward arena > 0.75)

Complete, evidence-backed status. All numbers are real measurements.

## What was built (compliant, validated)

| Component | File | State |
|---|---|---|
| Confidence-gated cascade | `router_core.py` | ✅ validated |
| RA submission adapter | `chuzom_clean_router.py` | ✅ (pool: qwen3-235b + deepseek-v4-flash probes → deepseek-v3.2 escalation) |
| CI template firewall | `ci_template_guard.sh` | ✅ green + negative control fires |
| Provenance manifest | `PROVENANCE.md` | ✅ |
| Synthetic calibration + τ sweep | `synthetic_gen.py`, `calibrate.py` | ✅ (regenerable) |

## The evidence chain

| Test | Result |
|---|---|
| P2 make-or-break: does agreement predict correctness? | **YES** — separation 1.00 on synthetic; cascade 95.8% @ 29% escalation |
| Real-pool calibration (synthetic, OpenRouter) | escalation 17.5%, cost $0.040/1k, deepseek-v3.2 best strong |
| **Real RA sub_10 (official metrics)** | **arena 0.700** (deepseek-v3.2), 69.6% acc, $0.07/1k, 38.7% escalation |
| Strong-model sweep on real RA | grok-4.3 → 72.7% acc but $0.99/1k → arena 0.697 (cost negates gain) |

## Honest conclusion

The confidence cascade is **legitimate, compliant, and cheap**, but the simple
agreement gate with a cheap pool **plateaus at arena ~0.70–0.72 on real RA** —
short of 0.75. Cost is a non-issue; **accuracy is the ceiling** (~70–73%, vs the
~75.5% needed). The hard ~39% of queries (probes disagree) can't be answered both
accurately AND cheaply: grok lifts accuracy but its cost erases the arena gain.

## The two legitimate paths to > 0.75 (real additional work)

1. **Pay for accuracy** — route more traffic to a strong model, accept higher
   cost (cf. vLLM-SR 0.7530 @ $0.30/1k, Sqwish 0.7527 @ $0.18).
2. **A learned confidence head beyond raw agreement** — cf. Nadir 0.7517 with a
   near-identical pool + a fit head trained on RouterBench (external, audited).
   Escalates *smarter* than binary agreement. This is the cost-efficient route
   and is buildable without touching RA data.

## Known measurement caveat

The sub_10 numbers use a quick harness; LiveCodeBench (~6% of prompts) scores 0
because code-execution grading wasn't wired (true accuracy ~+2–3 pts). The
definitive number would come from RA's official evaluator on a full submission.
