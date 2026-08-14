# 21 · Execution plan for a qualified G-F

Written 2026-08-14, after the suite was made order-independent (`63cbc8c`). This is the
working plan; doc 20 remains the pre-registered protocol and outranks it. Where they
disagree, doc 20 wins and this file is wrong.

## The arithmetic, stated once

`score ≥ max(baseline + 0.15, 0.80)`. Baseline `c2c2882` = 0.12, HEAD = 0.12, delta 0.00.
The binding constraint is therefore **the 0.80 floor**, not the +0.15 delta.

At 0.12, roughly 88% of mutants survive. Reaching 0.80 across 2436 mutants in eight
modules (11,254 lines) means killing on the order of **1,650 more mutants**. That is
test-writing work. Doc 20 §8 already says so: "several days to a couple of weeks", and
"not a formality that can be closed in a session."

**Nothing in this plan makes that number smaller.** Any step that appears to is a bug in
the plan.

---

## Step 1 — Baseline (attempt 12)

First attempt that can plausibly complete: eleven failed on defects now fixed.

    .venv/bin/python scripts/gf_mutmut.py --out .chuzom/gf/baseline \
      --names-file .chuzom/zero-tolerance-audit/gf/train.txt \
      --names-file .chuzom/zero-tolerance-audit/gf/validation.txt

Run it in the BACKGROUND. A foreground call dies at the 2-minute limit, and a killed run
skips its `finally` — that is how setup.cfg was stranded once already.

**Before believing any number, verify all three.** Each has been individually wrong:

| check | why |
|---|---|
| `mutant_names_count == 1986` | zsh collapsed 1986 names into 1 on attempt 6 |
| `git diff --quiet setup.cfg` | a killed run left the G-F scope stranded |
| stats AND clean-test stages clean | mutmut marks a mutant KILLED when the suite fails, so an environmental failure INFLATES the score |

**Acceptance:** a tally line `N/1986 🎉 killed 🫥 no-coverage ⏰ timeout 🤔 suspicious 🙁 survived`.

**Then compute** the conservative score per doc 20 §4 — 🫥/🤔/⏰ all count as SURVIVORS —
and report TRAIN (1518) and VALIDATION (468) separately and combined. The split is
stratified, so a large train/validation gap is itself a finding.

**Also record** measured throughput from `elapsed_sec`. §3's 14.13 mutations/sec is NOT
established. If the full universe turns out unaffordable, that is an OWNER DECISION and a
third amendment — never a quiet reintroduction of sampling.

**Stop condition:** if attempt 12 fails, diagnose by BISECTION, not by reading code. That
method went 3/3 on this codebase; reasoning from source went 0/5, including two
conclusions announced as "confirmed" and retracted.

## Step 2 — Classify survivors into weakness CLASSES

Not a checklist of 1,650 mutants. Group the TRAIN survivors by what is missing:

- behaviours with no test at all (B1, B4, B9 are known instances — expect families)
- behaviours tested only through a mock that cannot fail
- arithmetic/boundary conditions no test exercises
- error paths no test drives

**Acceptance:** a written taxonomy with a mutant count per class, in
`evidence/gf_phase2_classes.md`. A class with 200 mutants and one root cause is worth
more than 200 individual fixes.

**Do NOT look at validation or holdout here.** Inspecting validation to choose what to fix
converts it into a second training set and destroys its purpose.

## Step 3 — Write behavioural tests, iteratively

Per class, highest mutant-count first. For each test:

- RED before, GREEN after — and PROVE the red by reverting the fix. A test that goes green
  immediately after a signature fix may never have exercised the defect.
- Assert on BEHAVIOUR, not source text. A test that greps source is excluded by Amendment
  1 and cannot legitimately kill a mutant anyway.
- Never re-implement production logic in the test body and assert on the copy.

**Score TRAIN after each class** to measure progress. **Score VALIDATION only at
checkpoints** (suggested: every third class). A widening train/validation gap means
overfitting to train — stop and generalise the tests rather than adding more.

**Expected shape:** this is the bulk of the work — days to weeks, not hours. Report
progress as "class X closed, train score moved A → B", never as effort spent.

## Step 4 — Stopping rule (doc 20 §5, fixed in advance)

Stop writing tests when TRAIN and VALIDATION both clear the threshold with the validation
score's 95% lower bound above 0.80. Do not stop on train alone.

## Step 5 — Holdout, once

`.chuzom/gf/holdout.txt` (gitignored; only its sha256 is committed). Score it EXACTLY
ONCE. Report with its confidence bound. Scoring it twice, or after seeing a failing
number, voids the qualification under §7.

---

## What would make this fail honestly

Recorded now so it is not rationalised later:

1. **The floor is not reachable in the time available.** Then the honest output is an
   owner decision to amend or waive the 0.80 floor — recorded as an amendment, never as a
   pass. A staged floor (e.g. 0.50 now with a ratchet) is more defensible than a blanket
   waiver.
2. **The campaign accumulates too many deviations.** Two amendments and a patched
   instrument already exist. Each is recorded and argued, but an auditor may reasonably
   weigh the total. If a third amendment becomes necessary, that is a signal to reassess
   the instrument rather than to keep amending.
3. **The score improves for the wrong reason.** Any jump not attributable to a specific
   class of tests written should be treated as suspect and investigated before it is
   reported. The frozen sample's bogus 1.00 is the precedent.

## Open items NOT in this plan, needing an owner decision

- **agno budget pressure** reads `total_cost_usd`, which includes unattributed spend —
  $3.62 of the last 30 days' $39.79 (9.1%). A deployment could downshift early on spend
  that never happened. `attributed_cost_usd` is exposed so the call can be made on
  numbers. Behaviour deliberately unchanged.
- **`#32`: `lint_fail_open` cannot detect a fail-open that logs.** Measured: with the
  original fail-open restored, adding `redaction_routing.py` to its PROTECTED set yields
  0 violations. WP-13 ("fail-open triage", marked complete) used that gate as its
  instrument, so its clean result covers less than the title implies.
- **precision-tier**: 21 firings logged, but only 2 of 18 objective held-out prompts
  recorded gpt-4o-mini as the final model. Never instrumented; still open, not closed.
