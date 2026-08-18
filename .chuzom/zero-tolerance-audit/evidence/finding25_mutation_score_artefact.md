# Finding #25 — the 1.00 mutation score was an artefact of sample selection

Date: 2026-08-13. Owner-approved: author a baseline-era mutation set so G-F has a
computable baseline term.

---

## The two numbers

Same tree, same harness, same day:

| sample | scored | killed | score |
|---|---|---|---|
| original frozen ten (`mutation_sample.py`) | 10 | 10 | **1.00** |
| baseline-era ten, definitive run on the fixed harness | 8 | 1 | **0.12** |

(Earlier baseline-era runs reported 0.14 over 7 scored; they predate the
bytecode fix below. The definitive figure is **0.12 over 8 scored**, which clears
the harness's own "refuse a verdict below 8 scored" floor — the first run of
either sample to do so on a denominator that is comparable across SHAs.)

The original ten were chosen to target the audit's **known blind spots**, and the
remediation then fixed exactly those. **1.00 measured "we fixed what we looked
at", not "these modules are well tested."** I had flagged that as a caveat when
reporting it; this is the measurement that turns the caveat into a finding.

## "The named subset missed it" and "nothing catches it" are different claims

Every mutation names the narrowest test subset that *ought* to own its behaviour.
A survivor there is not yet evidence of missing coverage — it may mean the
coverage is filed somewhere else. Each survivor was therefore re-run against the
**entire suite**, and the survivors split into two genuinely different findings:

| | full suite | verdict |
|---|---|---|
| **B1** — `_host_opus_rates` input/output **inverted** | **green, 0 failures** | **ABSENT coverage** |
| **B4** — registration guard always returns `True` | **green, 0 failures** (verified alone) | **ABSENT coverage** |
| **B8** — pending spend always `0.0` | **red, 3 failures** | **MISFILED coverage** |
| **B7 + B9 + B10** (combined) | **red, 15 failures** | **caught in combination** |
| **B9 alone** — pressure cap `0.5` → `0.05` | **green, 0 failures** | **ABSENT coverage** |
| B7, B10 individually | not measured alone | **unattributed** |

The 15 failures spanned eight files — `test_tq007_daily_cap_downgrade` (4),
`test_quality_escalation` (3), `test_router` (2), `test_exhaustion_floor` (2),
and one each in `test_red2_02_downgrade_observable`, `test_precision_tier_routing`,
`test_finalize_failopen`, `test_a01_attempt_failed_ledger`. That shape is
consistent with B10 (neutral budget state inverted to *maximum* pressure, which
perturbs every downgrade/escalation path) and B7 (ledger reading a different
file, which empties `test_a01_attempt_failed_ledger`).

**Combined attribution is not per-mutation attribution.** A red combined run
proves at least one is caught, not which — so B9 was measured alone, and it is
**green**: the budget pressure cap can be cut tenfold and the entire suite
passes. That is a third absent-coverage finding, and it was the one the failing
test names would have led me to write off, since the 15 failures all looked like
B10's pressure inversion and B7's ledger path.

**B7 and B10 are left UNATTRIBUTED rather than inferred.** They are caught in
combination; which one (or both) does the catching was not measured. Naming a
culprit from the failing test names is exactly the inference B8 already punished.

Three absent-coverage findings stand: **B1, B4, B9** — one per area
(money / routing / verification).

**B1 is the most serious.** `_host_opus_rates` returns the baseline rates that
*every savings figure in the system* is computed against. Swapping input and
output — output tokens cost five times input — makes every counterfactual wrong
by a large factor, and **the entire test suite passes.**

This claim is **independent of the post-hoc selection caveat below**. How the
mutation was chosen has no bearing on whether the suite catches it. It is a fact
about the tests.

**B4 is the most pointed.** A guard that cannot answer "no" is *exactly* blind
spot Q3(c) — the one the audit recorded as CLOSED on the strength of
`unregistered()` checking tier constants against `_TIERS`. Verified alone,
because a combined run can mask.

**B8 is the counterexample that keeps the rest honest.** Its three failures were
all in `tests/test_t2_m1_budget_key.py`. The behaviour *is* tested; I named
`tests/test_budget.py` + `tests/economics/` as the owner and was wrong. Coverage
filed where a reader looking for it would not go — the same shape as the M7 note
in the original sample. **Because B8 exists, no per-mutation "absent coverage"
claim is made without its own full-suite run.**

## The honest weakness of this sample

**The ten were chosen AFTER seeing the remediation** — precisely the post-hoc
selection the frozen-sample design exists to prevent. Two things limit it,
neither of which eliminates it:

1. Selection was **mechanical**: a script listed lines identical and unique in
   both trees within the money/routing/verification modules. I did not check
   which mutations the remediation would happen to kill before choosing.
2. Each targets an **invariant** — a swapped rate, a guard that always passes, a
   degradation reported as clean — rather than "the thing that was fixed here".

Treat the delta as **weaker evidence than a pre-registered sample**. The
full-suite survivals (B1, B4) do not depend on it.

## Three probe failures, all mine

The harness excluded B2, B3 and B6 as `EQUIVALENT`. **All three were probe
defects, not equivalent mutants:**

- **B2, B3** mutate lines inside `async def log_usage`. My probes called
  `_claude_cost`, which never touches them. They are now recorded **UNPROBEABLE
  by this harness**: a correct probe needs a temp DB and several statements,
  while the probe contract is a single expression. The proper fix is a
  `probe_file` option — **deliberately not bolted on mid-measurement, because
  changing a measuring instrument while reading its output is how a result stops
  being trustworthy.**
- **B6** passed `slim='minimal'`, which is **not a tier** (`_TIERS` holds
  core/routing/consolidated/off). The lookup fell back to `None`, meaning *every
  tool is registered*, so `resolve()` never took the degraded branch and the
  probe returned `False` both ways. **It failed OPEN into a false `EQUIVALENT`** —
  the worst direction for a guard. Now `resolve('llm_generate','core').degraded`.

And a wording defect in the harness itself, which I wrote: `EQUIVALENT` reported
*"the mutation changes no observable behaviour"* when all it had measured was
that **the probe** saw no difference. A claim about the mutation, made on evidence
about the probe — **wrong three times out of three here.** Corrected to state the
weaker, true claim and to tell the reader to check which.

## The 10-vs-10, at last: the delta is ZERO

The owner's instruction was to author a baseline-era set so G-F would have a
computable baseline term. It now does — same ten mutations, same eight scored,
same harness, both SHAs:

| | scored | killed | score |
|---|---|---|---|
| baseline `c2c2882` (pre-remediation) | 8 | 1 | **0.12** |
| HEAD (post-remediation) | 8 | 1 | **0.12** |
| **delta** | | | **0.00** |

Not merely the same score — **the same per-mutation results**. B5 killed at both
SHAs; B1, B4, B6, B7, B8, B9, B10 survived at both. The remediation moved none of
them.

G-F: *"mutation score ≥ mutation_baseline + 0.15, floor 0.80."*
Required: ≥ 0.27 **and** ≥ 0.80. Measured: **0.12**. **G-F FAILS on both terms.**

### What this does and does not mean

It does **not** mean the remediation achieved nothing. Every fix in it was real
and verified RED-before-GREEN, and this session alone found and fixed a P0
(AUD-06 surviving in twelve surfaces) plus its sibling in the broadcast path.

It means something narrower and quite specific: **on a set of invariants chosen
independently of the work, the remediation produced no measurable change in
mutation coverage.** Those invariants were never in its scope — it fixed the
defects the audit had found, and the audit's own sample was drawn from those same
defects. The two sets barely intersect.

That is precisely why the original 1.00 was uninformative. The frozen sample and
the remediation were drawn from one pool; this sample was drawn from another, and
it shows **no improvement at all** in the money/routing/verification invariants it
happens to cover.

## What this does to G-F

G-F: *"mutation score ≥ mutation_baseline + 0.15, floor 0.80."*

Measured on the same denominator at both SHAs: **0.12 → 0.12, delta 0.00**,
against a requirement of ≥ 0.27 and a floor of 0.80. **G-F FAILS**, and it now
fails on a computable baseline rather than being unevaluable.

Three behaviour-changing defects — B1 (money), B4 (routing), B9 (verification) —
survive the **entire** suite, each verified by its own dedicated run.

The framing — whether this sample supersedes the frozen one, or sits alongside it
as a second measurement — is the owner's call, not mine. What is no longer open
is whether G-F can be recorded PASS. It cannot.

## Why it matters beyond the gate

The remediation's own regression tests are real and were verified RED-before-GREEN.
This finding is not that they are fake. It is narrower and worse:

**Coverage was measured with an instrument calibrated on the same defects the
work had just fixed.** A perfect score from such an instrument is close to
uninformative, and it read as reassurance. The correction is not "write more
tests" — it is that a coverage measurement must be *independent of the work it
grades*, in the same way `test_env_registry.py`'s scan had to be independent of
the registry it validates.

## A non-determinism in my own harness — and a rejection I got wrong

Two runs of the **same sample against the same code** disagreed about B10:
`'0.0' → '1.0'` (SURVIVED) then `'0.0'` both (EQUIVALENT). Isolated and repeated
three times with B10 as the *only* mutation, it flipped again — SURVIVED, then
EQUIVALENT, then EQUIVALENT — so no interaction with B9 or B6 was involved.

**The cause is stale bytecode. I had recorded that hypothesis as REJECTED, and
that rejection was wrong.**

`pressure=0.0` → `pressure=1.0` is the **same byte length**. Python validates a
cached `.pyc` against the source's `(mtime, size)` — both recorded as integers,
mtime to the second. When a same-size write lands in the same integer second as
the mtime recorded in an existing `.pyc`, the stale bytecode is served.

Measured, three rapid apply/restore cycles:

| | cycle 1 | cycle 2 | cycle 3 |
|---|---|---|---|
| caching **on** (harness default) | clean `0.0` → mutated `1.0` | clean **`1.0`** → mutated `1.0` | clean **`1.0`** → mutated `1.0` |
| `PYTHONDONTWRITEBYTECODE=1` | clean `0.0` → mutated `1.0` | clean `0.0` → mutated `1.0` | clean `0.0` → mutated `1.0` |

From the second cycle the **clean source reads as mutated**, so
`clean_probe == mutated_probe` and the harness reports `EQUIVALENT` for a
mutation that changes behaviour perfectly well.

### How I got the rejection wrong

I tested the hypothesis **once**. That single run happened to straddle a second
boundary, returned `1.0` both with and without `__pycache__`, and I recorded
"tested and REJECTED" — even propagating it into the standing instructions as a
correction. **One measurement of a timing-dependent effect measures the timing,
not the effect.** It is the same error this audit keeps finding in other people's
work: a favourable single observation promoted to a settled conclusion.

The tell was available and I walked past it: the flips followed a *pattern* —
first run after a pause detected the change, rapid successive runs did not. A
timing pattern is a signal to test timing, not to declare the timing hypothesis
dead.

### Fix, and what it does and does not invalidate

`_run` now sets `PYTHONDONTWRITEBYTECODE=1` for every subprocess it launches.
B10 then reports `SURVIVED` on three consecutive runs.

**The three absent-coverage findings are unaffected.** B1, B4 and B9 were each
measured by a *dedicated full-suite script* in which one mutation is written and
`pytest` starts seconds later, minutes after any previous write — so the `.pyc`
mtime always differed and the mutated source was always compiled. The failure
mode requires sub-second apply/restore cycling, which only the in-harness probe
loop does.

**What it does invalidate:** any `EQUIVALENT` verdict this harness produced for a
same-byte-length mutation before the fix. B1's mutation (swapped identifiers) is
also same-length, so its *probe* readings were at risk even though its full-suite
result was not.
