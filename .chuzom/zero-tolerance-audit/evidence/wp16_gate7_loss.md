# WP-16 item 1 — Gate 7 must assert that a loss survives

Date: 2026-08-13.

Plan scope item: *"Fix Gate 7 — it certified AUD-06. Gate 7 must now assert that
a loss can be represented and displayed."*

---

## Why Gate 7 certified AUD-06

Gate 7's bar is **"a defensible number exists"**, checked by
`tests/soak/realized_savings_soak.py`.

**A clamped zero is a number, and it looks defensible.** The gate asked whether a
figure was produced; it never asked whether an *unfavourable* figure could
survive being produced. `max(0.0, total_base - total_cost)` satisfies it
perfectly while rendering every overspend as "$0.00 saved".

## What was already covered, and what was not

`tests/economics/test_savings_sign.py` (WP-04, immutable) pins the **source**
arithmetic — session-end's total is a signed subtraction.

Nothing pinned the rest of the chain. A signed subtraction feeding a clamped mean
is still a lie to the operator, and a loss can be laundered into zero at four
later points. `tests/soak/test_gate7_loss_representable.py` covers each:

| layer | what a clamp there would do |
|---|---|
| `soak/ci.py` `bootstrap_ci` | every downstream figure reads break-even; the gate cannot tell a loss from a no-op |
| `soak/report.py` `_aggregate_headline` | N losing runs aggregate to zero |
| `conservative_ci_lower` | the **worst case** rounds toward favourable — the one direction a conservative bound must never move |
| the printer | negative in JSON, "0.00" on screen. RED2-02 was a display-layer failure, not an arithmetic one |

A sub-cent case is included deliberately: routing losses are sub-cent by nature,
and `-0.0001` is exactly the magnitude a clamp or a stray `round()` eats without
anyone noticing. At that size **the sign is the entire finding**.

## Verified to fire — and the first attempt to verify was itself broken

Every assertion passed on first write. That is the state a can't-fail test is
born in, so each layer got an AUD-06-style clamp injected:

| injection | result |
|---|---|
| `bootstrap_ci` point clamped | **CAUGHT** (2 tests) |
| aggregator `point_median` clamped | **CAUGHT** (2 tests) |
| `conservative_ci_lower` clamped | **CAUGHT** (1 test) |
| label rule `> 0` → `>= 0` | **CAUGHT** (1 test) |
| printer wrapped in `max(0, …)` | **CAUGHT** (1 test) |
| control, no injection | green |
| tree after all five | clean |

**The first run of that verification reported three of the five as NOT CAUGHT.**
The script decided the outcome by `grep -q "failed"` on the last three lines of
pytest output — which contained `FAILED` in uppercase, and no count line at all.
Case mismatch, so real catches read as misses.

Had I trusted it, I would have concluded my own tests were vacuous and rewritten
working tests to chase a defect that did not exist. It was caught only by
injecting one clamp **by hand** and seeing two tests fail — contradicting the
script.

The script now decides on the **pytest exit code**. String-matching an outcome
you could read from an exit status is a probe that can misreport, and a probe
that can misreport is worse than no probe: it launders a guess into a result.

This is the **seventh** time in this remediation that an injection-and-observe
harness has misled me, and the second where the harness reported a *clean* result
while measuring nothing (after the f-string that printed "0/6 reproductions").
The pattern is stable enough to state as a rule: **when a harness and a hand
check disagree, believe the hand check until the harness explains itself.**

One anchor also matched **0 sites** (`median = _r(_percentile(values, 50))` — the
real code is `point_median = _r(statistics.median(points))`). That one announced
itself, because the injector refuses to proceed unless an anchor matches exactly
once. The uniqueness check earned its keep again.

## Two source-level tests, and the limitation stated plainly

The label rule and the printer are asserted by **reading the shipped source**,
not by calling it: both live inline inside functions that run the entire soak
pipeline, so neither is callable in isolation.

That is weaker than executing them, and it is recorded here rather than hidden.
The alternative was worse: my first draft of both tests **re-implemented the
logic in the test body and asserted on my own copy** — exercising no production
code whatsoever and passing forever regardless of what shipped. I caught that on
re-reading my own work, which is the same defect class as
`tool_surface.unregistered()` validating tier constants against `_TIERS`.

Reading what ships is weaker than calling it, and much stronger than testing a
duplicate of it. Both injections confirm the source-level assertions do fire.

## A separate finding: Gate 7 contains a test that cannot fail

`realized_savings_soak.py::test_subscription_quota_tokens_are_non_negative` is a
bare `assert quota >= 0` with no docstring.

Measured: `realized_quota_tokens_saved` is accumulated in
`execution_ledger.py:619` as a **sum of token counts**, each added only when
`quota` is truthy and positive. The ledger's own comment records that the old
`baseline_tokens − actual_tokens` formula was removed as "a structural tautology".

So the quantity is non-negative **by construction**. The assertion cannot fail —
it is not guarding a clamp, it is guarding nothing. Left in place (it is
harmless and inside Gate 7's existing file), but recorded because **G4, the
repo's own "no new can't-fail tests" ratchet, currently passes with this inside a
release gate.** A ratchet that grandfathers its predecessors reports clean about
the code it was built to police.
