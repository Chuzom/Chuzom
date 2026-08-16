# Pre-registered prediction for the checkpoint — written BEFORE the result

Written while the run is in flight (elapsed ~3 min of ~39). Recorded so the outcome is
falsifiable and so I cannot rationalise it afterwards. Doc 21's honest-failure criterion 3
says a score that improves for reasons not attributable to specific tests is SUSPECT; a
prediction made in advance is the only way to tell the two cases apart.

## Inputs

Last measured (Step 0, before Groups A/B/C):

    TRAIN       979 / 1518 = 0.6449
    VALIDATION  284 /  468 = 0.6068   Wilson LB 0.5619
    COMBINED   1263 / 1986 = 0.6360

Since then: ~190 mutants killed, each verified per-mutant against a no-mutant control.
All targets were chosen from TRAIN only (validation was never inspected — doing so would
make it a second training set).

## The spillover rate, measured once

At the Group A checkpoint, 74 verified TRAIN kills produced 98 total kills — so 24 landed
on VALIDATION mutants that no one targeted. Spillover = 24/74 = 32.4%.

This is the only measurement of the rate that exists. n=1, so treat it as an estimate with
wide error bars, not a constant.

## Predictions

    TRAIN       ~1150 - 1170  (raw 0.758 - 0.771)
    VALIDATION  ~ 330 -  360  (raw 0.705 - 0.769)  point estimate 344 (0.735)
    COMBINED    ~1480 - 1530  (raw 0.745 - 0.770)

Point estimate for VALIDATION: 284 + (190 x 0.324) = 284 + 62 = 346, rounded to ~344 for
the modest overlap expected with mutants already killed.

## What the stopping rule requires (computed before the result, Wilson 95%)

    VALIDATION n=468: k >= 392  (raw 0.8376)  -> LB 0.8015   PASSES
                      k =  391  (raw 0.8355)  -> LB 0.7992   FAILS
    HOLDOUT    n=450: k >= 377  (raw 0.8378)  -> LB 0.8009   PASSES

Note the gap between the two thresholds people conflate: raw 0.80 on validation gives a
Wilson LB of only 0.7605. The rule demands the LOWER BOUND above 0.80, so the raw score
must reach 0.8376. That is 392 kills, not 374.

## Therefore, predicted verdict

**The stopping rule will NOT be met.** Predicted validation ~344 against a required 392 —
short by roughly 48 kills. Group D (#46) will be required, and the honest framing is
"how far into the long tail does the floor force us", not "are we nearly there".

## What would falsify this, and what each outcome means

- VALIDATION >= 392 -> prediction WRONG, rule met. Before celebrating, check the run was
  clean (stats + clean-test stages), because an environmental failure INFLATES the score
  (methodology (b)) and a jump of 108 unaimed kills from 190 aimed ones would imply a
  spillover rate of 57% against a measured 32%. Investigate BEFORE reporting.
- VALIDATION 330-360 -> prediction CORRECT. Proceed to Group D.
- VALIDATION < 320 -> prediction WRONG in the other direction; spillover is lower than
  measured, the long tail is more independent than assumed, and Group D is bigger than
  the ~199 mutants currently scoped.
- TRAIN rising while VALIDATION stalls -> OVERFITTING. Doc 21 step 3 is explicit: a
  widening train/validation gap means generalise, do NOT add more tests. Current gap is
  0.6449 - 0.6068 = 0.038. If the gap exceeds ~0.08, stop adding tests and reassess.

## Preconditions to verify before believing ANY of these numbers

1. run_metadata.json mutant_names_count == 1986
2. git diff --quiet setup.cfg
3. stats AND clean-test stages CLEAN
4. outcome lines == 1986 (the failed Step 0 attempt wrote metadata while capturing zero
   outcomes, so metadata alone is not evidence the run happened)
