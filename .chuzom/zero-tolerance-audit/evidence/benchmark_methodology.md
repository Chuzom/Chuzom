# Evidence — benchmark methodology (Gate 16, quality non-inferiority)

## Finding A: the 0.5 margin WAS pre-registered — claim EXONERATED

Source: Docs/correctness-reset/03_RELEASE_GATES.md:29-30, :102

- The 0.5 non-inferiority margin was in force BEFORE the passing result existed.
- With that margin, the first formal audit **FAILED** Gate 16 at delta -0.58 ("outside the
  0.5 margin"), and the release was marked **NOT QUALIFIED** (commit 3923098,
  "docs(audit): record Pass-1 finding - Gate 16 not robust; verdict RELEASE NOT QUALIFIED").
- Quote (03_RELEASE_GATES.md:102): "the audit did its job and halted rather than certify a
  non-robust pass."

=> The margin was NOT selected after seeing -0.21. A pre-registered threshold that actually
   rejected a release is strong methodological evidence IN THE PROJECT'S FAVOUR.
   Audit suspicion 01_PRODUCT_CONTRACT.md B.1 (post-hoc margin) is WITHDRAWN.

## Finding B: the FIX was developed against the evaluation corpus — overfitting risk

Source: Docs/correctness-reset/03_RELEASE_GATES.md:87

Sequence:
1. Gate 16 fails at -0.58.
2. Root cause recorded as: "short objective prompts where cheap-local-first returns
   confident-**wrong** terse answers the runtime heuristic can't catch (`mod-07`/`mod-12`)".
3. Fix #220 "precision-tier routing" introduced, which "fronts the reliable cheap metered
   `gpt-4o-mini` for exact-answer prompts (arithmetic / code-output / precise count),
   removing those misses."
4. Re-measured on the SAME corpus -> -0.18 / -0.21 / -0.21 / +0.00, "Variance collapsed".

Problems:
- Corpus is 33 prompts (moderate+hard). The fix was designed to address the SPECIFIC prompts
  (mod-07, mod-12) that caused the failure, then evaluated on the corpus containing them.
  This is fitting to the test set. "Variance collapsed" is the expected symptom.
- The robustness claim ("held across 4 independent runs") is therefore measured on a corpus
  the fix was tuned against. Runs are repeated measurements of the same 33 prompts, not
  independent samples of the prompt population. README presents this as "Robustness".
- No held-out corpus is used to confirm the fix generalizes.

## Finding C: the quality gate was partly passed by SPENDING MORE

The fix moves exact-answer prompts from FREE LOCAL to METERED gpt-4o-mini.
Quality improved partly by routing away from the free tier toward a paid tier.
=> Gate 16 (quality) and Gate 15 (savings) are coupled: the quality fix consumes savings.
   Both are reported as independently passing. The tradeoff is not disclosed in README.

## Finding D: Pass-2 quality delta is exactly +0.00
03_RELEASE_GATES.md:98 - "Pass 2 - mechanical PASS; benchmark NET +$0.02722, quality delta +0.00".
An exact 0.00 delta across a judged corpus warrants inspection (judge granularity / ties /
identical routing on both arms). NOT TESTED here - flagged for RED-2.
