# G-F Checkpoint 1 — 0.5866 → 0.6360

Date: 2026-08-15. Doc 22 Step 0 / doc 20 §5 checkpoint. Baseline commit `8678a4b`.

## Result

| set | killed | n | score |
|---|---|---|---|
| TRAIN | 979 | 1518 | 0.6449 |
| VALIDATION | 284 | 468 | 0.6068 |
| **COMBINED** | **1263** | **1986** | **0.6360** (95% LB 0.6148) |

Baseline 1165/1986 = 0.5866. **Delta +98 mutants, +0.0494.** Floor 0.80 → **FAIL**,
gap 0.1640.

Conservative per §4 — 🫥 (77) and ⏰ (89) counted as survivors.

## Preconditions verified before believing the number

    returncode        0        (the previous attempt returned -15, SIGTERM)
    mutant_names_count 1986
    OUTCOME LINES     1986/1986   <- the check that actually matters
    stderr            0 bytes
    setup.cfg         CLEAN

The failed attempt wrote a `run_metadata.json` **and captured zero outcome lines**. A
metadata file is therefore not evidence a run completed; the outcome count is.

## The 74 verified TRAIN kills produced 98 total

Doc 22 said the VALIDATION effect of the 74 individually-verified TRAIN kills was
unmeasured and not predictable from that number. It was real: **24 additional VALIDATION
mutants** died to the same tests. That is the payoff for writing tests against behaviour
rather than against specific mutants.

## Train/validation gap: 0.038 — watch it

TRAIN 0.6449 vs VALIDATION 0.6068. Doc 21 Step 3: a widening gap means overfitting to
train, and the response is to generalise rather than add tests.

0.038 is modest and expected — the tests were written against TRAIN survivors — but it is
the number to check at the next checkpoint. A gap that grows while the score rises means
the score is rising for the wrong reason.

## Category movement

| | baseline | now |
|---|---|---|
| 🫥 no-coverage | 107 | **77** |
| ⏰ timeout | 57 | 89 |
| 🙁 survived | 603 | 557 |

The no-coverage drop tracks the two 100%-uncovered functions that were covered. The
timeout rise is noise-level drift and consistent with `gf_phase3_timeouts.md`: those
mutants neither hang nor die, so which ones happen to trip the limit varies by run and
by machine load — this run competed with a second mutation run on the same machine at
the owner's instruction.

## What remains

Floor 0.80 needs ~326 more kills over 1986. Remaining TRAIN survivors ~540 minus the 98
already landed. Sequencing in `25_MASTER_PLAN.md` W1; per-class detail in doc 22.
