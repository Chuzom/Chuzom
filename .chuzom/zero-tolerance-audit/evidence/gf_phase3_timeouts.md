# G-F Step 3.1 — the ⏰ mutants do not hang

Date: 2026-08-14. Opened by `gf_phase2_classes.md` §4, which recorded the 57 timeouts as
OPEN and refused to guess a cause.

## Result

**All 38 timeout-marked mutants in the two main functions were re-run individually. Every
one completed in 5.8–7.8 seconds with every covering test passing.** None hangs. None is
killed.

| function | ⏰ mutants | re-run verdict |
|---|---|---|
| `router._task_aware_default_order` | 22 | 22/22 complete, all covering tests pass |
| `router._reorder_for_agent_context` | 16 | 16/16 complete, all covering tests pass |

Method: `MUTANT_UNDER_TEST=<name>` activates a single mutant through mutmut's trampoline;
each was run against exactly the covering tests mutmut's own `mutmut-stats.json` records
for that function (64 and 131 tests, 6.1s and 8.4s at baseline).

## What follows, and what does not

**The score is unaffected and doc 20 §4 was right.** These mutants are genuine survivors —
the suite does not detect them — so counting them as survivors is correct. 0.5866 stands.

**The planning consequence is real.** Phase 2 filed ⏰ as a distinct class needing special
handling for loop hazards. It is not one. These are 57 ordinary survivors in functions
already on the Step 3 work list, and they need ordinary behavioural tests. The class
disappears; the mutants stay.

**The direction of any instrument error here is the safe one.** mutmut marks a mutant
KILLED when the suite fails. A spurious ⏰ inflates the SURVIVOR count, never the kill
count, so if anything 0.5866 is a slight under-estimate. That is the opposite of the
failure mode this protocol exists to prevent, and it is why this finding does not require
re-running the baseline.

## A hypothesis, refuted — recorded so it is not re-run

*"⏰ tracks how expensive a mutant is to evaluate rather than a hang."* Refuted by
measurement: the timeout functions rank **49th–77th of 145** by covering-test wall cost,
and the ten costliest functions have **zero** timeout mutants.

**The cause of the ⏰ marking remains UNEXPLAINED.** Nineteen further timeouts in six
other functions were not re-run, so the finding is stated over the 38 tested rather than
all 57. Leaving a cause open is preferable to closing it with the best-sounding story;
this campaign has already retracted three diagnoses that were reasoned rather than
measured.

## A probe error worth recording

The first run of this probe reported `pass=0 fail=0` for every mutant and classified all
38 as UNCLEAR. `pyproject`'s `addopts` already carries `-q`, so the probe's own `-q` made
pytest **double-quiet** and it omitted the "N passed" summary line the probe was parsing.

The verdict now comes from the **exit code**, which is what pytest actually reports. This
is the ninth time in this campaign an outcome was taken from parsed text instead of an
exit status, and the second time the fix was to stop parsing and read `returncode`.
