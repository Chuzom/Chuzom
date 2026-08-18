# G-F Checkpoint 2 — after Groups A, B and C

Run: `.chuzom/gf/checkpoint/`, commit `abf25ef`, 2026-08-16T06:13:47Z, elapsed 2467s.

## Preconditions — all four verified before reading any number

| # | check | result |
|---|---|---|
| 1 | `mutant_names_count == 1986` | 1986 |
| 2 | `git diff --quiet setup.cfg` | clean |
| 3 | stats + clean-test stages | `mutmut_stderr.txt` empty, returncode 0 |
| 4 | outcome lines == 1986 | 1986 lines, 1986 DISTINCT mutants |

Precondition 4 exists because a previous Step 0 attempt wrote a well-formed
`run_metadata.json` while capturing ZERO outcome lines. Metadata alone is not evidence
that a run happened.

## Score — conservative, doc 20 section 4 (no-coverage / suspicious / timeout = SURVIVORS)

| split | n | killed | raw | 95% LB | delta vs checkpoint 1 |
|---|---|---|---|---|---|
| TRAIN | 1518 | 1138 | 0.7497 | 0.7273 | +159 |
| VALIDATION | 468 | 329 | 0.7030 | 0.6601 | +45 |
| COMBINED | 1986 | 1467 | 0.7387 | 0.7189 | +204 |

Outcome breakdown: killed 1467, survived 348, timeout 121, no-coverage 50.

## Stopping rule (doc 20 section 5) — NOT MET

Thresholds computed BEFORE the result was read:

    VALIDATION n=468: k >= 392 (raw 0.8376) -> Wilson LB 0.8015  PASSES
                      k =  391 (raw 0.8355) -> Wilson LB 0.7992  FAILS

Actual 329. **Gap: 63 kills.**

Worth stating because it is routinely conflated: raw 0.80 on validation gives a Wilson
lower bound of only 0.7605. The rule requires the LOWER BOUND above 0.80, so the raw score
must reach 0.8376 — 392 kills, not 374.

## The pre-registered prediction, and how it did

Recorded in `gf_checkpoint_prediction.md` while the run was in flight, before any result.

| quantity | predicted | actual | verdict |
|---|---|---|---|
| TRAIN | 1150–1170 | 1138 | below range by 12 |
| VALIDATION | 330–360 (point 344) | 329 | below range by 1 |
| COMBINED | 1480–1530 | 1467 | below range by 13 |

**All three landed just below the predicted range — systematically optimistic by ~1%.**
Spillover came in at 45/159 = 28.3% against the 32.4% extrapolated from the single prior
measurement. Recorded rather than rounded away: the bias has a consistent direction, so
future estimates should be shaded down.

## The finding: 11 mutants REGRESSED from killed to not-killed

Per-mutant diff against checkpoint 1 (1986 mutants common to both runs):

| transition | count |
|---|---|
| survived -> killed | 182 |
| no_coverage -> killed | 25 |
| timeout -> killed | 8 |
| **killed -> timeout** | **9** |
| **killed -> survived** | **2** |
| timeout -> survived | 3 |
| no_coverage -> survived | 2 |

Net +204, which reconciles exactly with 1263 -> 1467.

Only tests were ADDED between the two runs; no production source changed. A mutant moving
from killed to not-killed is therefore not a code regression — it is the INSTRUMENT moving.

**killed -> timeout (9).** 8 in `router._apply_routing_policy`, 1 in
`_task_aware_default_order`. Total timeouts across the run went 57 -> 121. The mechanism:
~190 added tests enlarge each mutant's covering-test set, and a set that exceeds the 300s
budget is scored a survivor regardless of whether it would have been killed.

**This means test-writing DEPRESSES the measured score.** The direction is the safe one
(deflation, not the inflation doc 20 was written to prevent), but 121 mutants — 32 of them
in VALIDATION, against a 63-kill gap — are now counted as survivors on a timer rather than
on evidence.

Note this does NOT contradict `gf_phase3_timeouts.md`, which established that the original
38 timeout-marked mutants do not hang and are genuine survivors. That finding was about
those 38. The 64 NEW timeouts arrived with the new tests and have a different cause.

**killed -> survived (2).** `tool_surface.x_resolve__mutmut_51` (`task =
_DOOR_TASK_ARG.get(candidate)` -> `task = None`) and `__mutmut_83`
(`floor = next(iter(sorted(reg)))` -> `floor = next(None)`, which raises TypeError if
reached). Neither can be explained by timing. Under investigation; NOT closed here.

Ruled out already: my `test_gf_resolve_paths.py` only READS the door registry
(`registered_tools(tier)`) and never mutates it, so this is not a reappearance of the
process-wide-state class fixed in 63cbc8c.

## A mistake made while investigating, recorded because it is instructive

First verification attempt ran the two mutants under the REPO's pytest config (30s
timeout) rather than the harness's (300s). `test_source_lint_passes` — a source-scanning
test that takes ~28s in the 33x-larger mutants tree — hit the timeout and FAILED, and a
failing test reads as a KILL. I briefly concluded both mutants were killed.

That is precisely the false-kill mechanism Amendment 2 raised the timeout to 300s to
prevent, and methodology (b) warns about in general. I walked into it while investigating
it. The conclusion was retracted before it was reported as a result.

## Consequence for the plan

Group D (#46) is required. Before grinding the long tail, the 121 timeouts deserve
attention: they are the cheapest available kills if any fraction of them are killable, and
they will keep growing as more tests are added — a mechanism that makes the campaign
progressively harder to finish the more work is done on it.
