# 20 · Protocol for a legitimate G-F qualification

Status: **PRE-REGISTERED**. Authored 2026-08-13, *before* any remediation work
begins. Sealed by `CRITERIA_MANIFEST.sha256` and checked by G-C in CI, so any
later edit to this document is visible in review.

Design informed by an independent review routed to `codex/gpt-5.5`; sample-size
arithmetic, runtime budget and tooling choices verified against this repository.

---

## 0 · The rule, and why the obvious path is not available

G-F: `score ≥ max(baseline + 0.15, 0.80)`. Baseline is **0.12**, so `+0.15`
gives 0.27 and **the floor dominates: 0.80 absolute.**

The baseline-era sample would now read ~0.50 (B1/B4/B9 closed), and covering
B6/B7/B10 plus correcting B8's test-ownership metadata would put it near 1.00.

**That number would be inadmissible.** It fixes the survivors of the sample it is
graded on. It is the same error as the original frozen ten scoring 1.00 — an
instrument calibrated on the defects the work had just fixed — one level down.
Producing it and calling it a pass would make this document pointless.

**The known survivors are diagnostics, not a checklist.** They name weakness
*classes*: a degraded state reported clean (B6), a persistence path not verified
(B7), a neutral/default state inverted (B10). The work is to cover those classes
across the codebase, not those three lines.

## 1 · Instrument

**Use `mutmut` 3.6.0** — already declared in `pyproject.toml:60` and installed,
and per `scripts/mutation_sample.py`'s own docstring "never wired to anything".
Wiring it is the missing piece.

This replaces hand-authored samples for *scoring*. Hand-authored mutations cannot
reach the sample sizes below, and a human choosing them is the selection bias
this protocol exists to remove.

`scripts/mutation_sample.py` is **retained** for targeted diagnostics — its
behaviour probes, `EQUIVALENT`/`UNVERIFIED` classification and uniqueness
enforcement are useful when investigating one defect. It is **not** the scoring
instrument.

**Target modules** (the gate's stated scope), with current size:

| area | modules | loc |
|---|---|---|
| money | `cost.py`, `savings.py`, `execution_ledger.py` | 4,323 |
| routing | `router.py`, `tool_surface.py`, `classify.py` | 6,215 |
| verification | `budget.py`, `coverage.py` | 716 |

## 2 · Three-way split, sealed

Generate the full mutmut universe over those eight modules at a frozen SHA, then
split it **deterministically** before any test is written:

```
seed = sha256("chuzom-gf-v1" + baseline_sha + universe_manifest_sha)
shuffle(universe, seed) → 60% TRAIN · 20% VALIDATION · 20% HOLDOUT
```

Stratify by `(module, operator)` so the holdout cannot end up dominated by one
file or one mutation kind.

- **TRAIN** — inspect freely. This is where the work happens.
- **VALIDATION** — score periodically. Feedback on whether improvements
  generalise beyond train.
- **HOLDOUT** — **scored exactly once, at the end.** Never inspected.

**Sealing.** Commit only `holdout_manifest.sha256` and the seed inputs — not the
holdout mutant IDs. G-C already fails CI on manifest drift, so the seal is
tamper-evident without new machinery. The encrypted-secret approach the routed
review suggested is over-engineering for a single-maintainer repo; the property
that matters is that a later edit is *visible*, and G-C gives that.

## 3 · Sample size, with the arithmetic

A pass must survive its own error bars. For a binary killed/survived proportion,
`SE = sqrt(p(1−p)/n)`, and the gate should require the **95% lower bound** ≥ 0.80,
not the point estimate.

| holdout n | at p=0.85 | at p=0.90 |
|---|---|---|
| 120 | lower bound **0.786** ✗ | lower bound 0.846 ✓ |
| 150 | 0.793 ✗ | 0.852 ✓ |
| 200 | **0.800** ✓ | 0.858 ✓ |

**Decision: holdout n ≥ 150, and the gate requires the 95% lower bound ≥ 0.80.**
That forces a true score near 0.88+ rather than a bare 0.80 — which is the
correct direction for a floor that exists to be hard.

A universe of ~750 gives 450 train / 150 validation / 150 holdout. If mutmut
yields more, keep the proportions and cap the holdout at 250.

**Runtime is affordable.** Measured here: ~36s per mutation against narrow test
subsets; mutmut runs a targeted subset per mutant. 150 holdout mutants ≈ **1.5
hours**; the full 750 ≈ 7.5 hours, i.e. one overnight background run. This is the
main reason n≥150 is practical at all.

## 4 · Scoring rule — conservative, decided in advance

```
score = killed / total_scored          # equivalents and unverified count as SURVIVORS
```

At this scale, per-mutation behaviour probes are not written, so equivalent
mutants cannot be individually excluded. **Counting them as survivors biases the
score DOWN.** That is the safe direction: it can only make the gate harder to
pass, never easier.

If the conservative score lands within 0.03 of the bar, and only then, a
documented equivalence review may be run — each exclusion requiring the mutant
diff, the reason no valid test could observe it, and a written justification in
the artefacts. **Never as a way to reach the bar after missing it.**

## 5 · Stopping rule — fixed now, so it cannot be adjusted later

1. Work proceeds against **TRAIN** survivors and ordinary coverage reasoning.
2. **VALIDATION** may be scored after each batch of test work.
3. Stop when validation ≥ **0.88** on two consecutive runs *and* its 95% lower
   bound ≥ 0.80.
4. Run **HOLDOUT once**. No fixes between the stopping condition and that run.
5. If holdout fails: the attempt is **recorded as failed**. The holdout is then
   burned — a new round requires a **new universe, new seed, new holdout**.
   Re-running a seen holdout is the thing this whole protocol prevents.

## 6 · Order of work

**Phase 0 — trust the instrument (do first).**
Wire mutmut into a reproducible script; record commit SHA, command line,
environment and universe hash in every result. Correct B8's test-ownership
metadata in the legacy sample (`tests/test_t2_m1_budget_key.py`, not
`tests/test_budget.py`) — misattribution corrupts diagnostics. Make CI fail on
manifest drift (already true via G-C).

**Phase 1 — freeze and split.** Generate the universe, derive the seed, split,
seal, commit hashes. Score the baseline at the frozen SHA on train + validation
only. **Do not touch holdout.**

**Phase 2 — classify, don't checklist.** Group train survivors into weakness
classes. The three known ones — degraded-state-reported-clean, persistence-path
unverified, neutral/default inverted — are almost certainly systemic, not local.
Expect new product defects to fall out, as B1 did.

**Phase 3 — write behavioural tests.** Assert externally meaningful behaviour:
money invariants and boundaries, ledger read/write path correctness, routing
decisions, tier resolution, budget state transitions, degraded/empty/error
states. **Do not write tests that encode an implementation detail purely to kill
a known mutant** — that passes train and moves validation not at all, which is
exactly the signal to watch for.

**Phase 4 — verdict.** Stopping rule met → holdout once → record.

## 7 · What invalidates the result

Any one of these voids the qualification:

- the protocol was edited after work began (G-C makes this visible);
- holdout contents were inspected, or holdout was scored more than once;
- tests were added between the stopping condition and the holdout run;
- the sample was regenerated after seeing a failing score;
- equivalence exclusions were used to cross the bar rather than reviewed on
  principle;
- the score is reported without its confidence bound.

## 8 · Honest effort estimate

**Phase 0–1: half a day** plus one overnight run. **Phase 2–3: the real work.**
On 11,254 lines across eight modules with a true score near 0.12, expect
**several days to a couple of weeks** of test writing, and expect it to surface
further product defects — the last sample of ten surfaced a P0.

**This is not a formality that can be closed in a session.** If the release is
time-critical, the alternative is not a faster pass; it is an explicit, recorded
decision to amend or waive G-F's 0.80 floor — a criteria change, which is the
owner's to make and must be recorded as an amendment, never as a pass.
