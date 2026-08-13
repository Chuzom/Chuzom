# 19 · Remediation verdict — WP-16 item 2

Date: 2026-08-13. Branch `fix/wp04-savings-sign`, HEAD `48a2607`.

WP-16 item 2 requires re-running the audit at the shipping SHA. Acceptance
(immutable): *"Two consecutive clean passes at one frozen SHA, zero new P0/P1, no
'not reached' sections."*

---

## Verdict: **NOT QUALIFIED** — G-F fails on a computable baseline

One hard gate fails. Hard gates are **disqualifiers, not deductions** — the plan
is explicit that they exist "so the score cannot be gamed by closing many cheap
findings while leaving an expensive one open". No amount of P0/P1 closure
overrides one.

## Gate status

| gate | rule | status |
|---|---|---|
| **G-A** | any open P0 → FAIL | **PASS** — all 24 findings raised in this remediation are closed |
| **G-B** | a regression test not RED before its fix → not closed | **PASS** for every fix landed here |
| **G-C** | acceptance-criteria hash mismatch → WP FAILS | **PASS** — implemented in this remediation; it did not exist before, so it could never fire |
| **G-D** | suite green on the built wheel | **PASS** |
| **G-E** | re-qualification at the shipping SHA | **SATISFIABLE** — the audit artefacts are now tracked and have a SHA; they did not before |
| **G-F** | mutation score ≥ baseline + 0.15, floor 0.80 | **FAIL — 0.12** |

## Why G-F fails, measured

Ten mutations whose anchors were each verified to appear exactly once in **both**
the pre-remediation tree (`c2c2882`) and HEAD. Same sample, same harness, eight
scored at both SHAs:

| | scored | killed | score |
|---|---|---|---|
| baseline `c2c2882` | 8 | 1 | **0.12** |
| HEAD | 8 | 1 | **0.12** |
| **delta** | | | **0.00** |

Required: **≥ 0.27** *and* **≥ 0.80**. Not merely the same score — **the same
per-mutation results**. B5 killed at both SHAs; B1, B4, B6, B7, B8, B9 and B10
survived at both. The remediation moved none of them.

Three of those survive the **entire test suite**, each verified by its own
dedicated full-suite run:

- **B1 (money)** — `_host_opus_rates` input/output rates **inverted**. This is the
  baseline constant every savings figure in the system is computed against;
  output tokens cost five times input, so every counterfactual would be wrong by
  a large factor. **The whole suite passes.**
- **B4 (routing)** — the registration guard made to always answer `True`. This is
  blind spot **Q3(c)'s exact shape** — the one the original audit recorded as
  CLOSED on the strength of `unregistered()` checking tier constants against
  `_TIERS`.
- **B9 (verification)** — the budget pressure cap cut tenfold, uncaught.

**B8 is the counterexample that keeps the rest honest**: it *is* caught, by
`tests/test_t2_m1_budget_key.py`. Its coverage was merely filed where a reader
would not look. Because B8 exists, no "absent coverage" claim above was made
without its own full-suite run.

## The finding behind the finding

The **original** frozen ten score **1.00** on this same tree.

Those ten were chosen to target the audit's *known blind spots*, which the
remediation then fixed. **Coverage was measured with an instrument calibrated on
the same defects the work had just fixed.** A perfect score from such an
instrument is close to uninformative — and it read as reassurance.

The correction is not "write more tests". It is that **a coverage measurement
must be independent of the work it grades**, in the same way
`test_env_registry.py`'s scan had to be independent of the registry it validates,
and in the way `unregistered()` was not.

### The honest weakness of the replacement sample

The baseline-era ten were chosen **after** seeing the remediation — the post-hoc
selection the frozen-sample design exists to prevent. Limited, not eliminated, by
mechanical selection (a script listed lines identical and unique in both trees; I
did not check which the remediation would kill before choosing) and by targeting
invariants rather than diffs.

**The three full-suite survivals do not depend on that caveat.** How a mutation
was chosen has no bearing on whether the suite catches it.

## Why two consecutive clean passes were not run

They cannot change the verdict. G-F is a disqualifier and fails on a measured,
same-denominator comparison; two green passes would produce a QUALIFIED-looking
record next to a failing hard gate.

The project's own rule is *"a gate that is not proven is FAIL, and the release
fails explicitly rather than weakening the bar."* Running passes whose outcome
cannot matter is the weakening.

**This is a decision the owner may reverse.** If the passes are wanted as evidence
of stability rather than as a qualification, they can be run on request.

## What this verdict does not say

It does **not** say the remediation achieved nothing. Every fix was real and
verified RED-before-GREEN, and this phase alone found and closed:

- **a P0** — AUD-06's clamp surviving in twelve surfaces including the
  Slack/Discord broadcast, fixed structurally rather than site-by-site;
- **RED2-02 in that same broadcast path** — a failed ledger read published as
  "$0.00 saved";
- **G-C**, which had no implementation and could never fire;
- **two CI gates red at HEAD** from this session's own commits;
- **a benchmark reporter** that rendered a run where all 24 prompts failed as a
  complete scorecard with a quality delta.

It says something narrower and harder: **on invariants chosen independently of
the work, test coverage of the money, routing and verification modules did not
measurably improve.**

## Held-out benchmark (item 3), for the record

| router | quality | cost/prompt | success |
|---|---|---|---|
| static-chain | 4.50 | $0.042m | 24/24 |
| always-premium | 4.50 | $0.816m | 24/24 |
| **chuzom** | **4.17** | $0.032m | 24/24 |
| always-cheap | 2.42 | $0.000m | 9/24 |

Held-out delta **−0.33**, against tuned runs of −0.18 / −0.21 / −0.21 / +0.00 —
**worse than every tuned run**, still inside the 0.5 non-inferiority margin, so
Gate 16's bar holds. **Chuzom is not the champion on unseen prompts.** #220's
precision-tier fix generalises only partially: both objective failures were the
`mod-07`/`mod-12` shape it was built to prevent.

## Item 5 — the badge

**Not restored.** It is conditioned on score > 95% with zero P0. The score cannot
exceed 95% with a hard gate failing.

## What would change this verdict

Raise real coverage of the money/routing/verification invariants until a
sample chosen *independently of the fixes* clears 0.80. Starting points, all
measured here: `_host_opus_rates`' rate ordering, the registration guard's
ability to answer "no", and the budget pressure cap.

**A pre-registered sample authored before the next remediation begins** would
also restore G-F's design intent, which no sample authored afterwards can.
