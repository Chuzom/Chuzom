# G-F Step 3, class C1 — fail-open sites now assert what they record

Date: 2026-08-14. Class defined in `gf_phase2_classes.md` §3 (C1, 40 mutants, 11 codes).
This closes the three router sites; eight remain.

## Result

`tests/test_gf_c1_failopen_codes.py`, 9 tests, against the three router fail-open sites:

| | killed | total |
|---|---|---|
| **fail-open family — the actual target** | **11** | **11** |
| everything else in those functions (collateral) | 7 | 30 |
| combined | 18 | 41 |

Verified per-mutant by name with a no-mutant control passing first, so the kills are
attributable rather than inferred from a total.

## The first pass looked complete and was not

The initial six tests killed **11 of 41**. There are also exactly **11 fail-open mutants**
in those three functions. Reported as a total, that reads as full coverage of the target.

By name it was **7 of 11 on target, 4 of 30 collateral**. A third of the class was
untouched, and the number that would have been reported could not tell the difference
between that and complete success.

The instrument was at fault too, in the way this campaign keeps rediscovering:
`verify_kills.py` reports kills by mutation KIND and hardcodes `accumulator` as the aimed
class — correct for C6, meaningless here. It printed *"0 of the 0 accumulator mutants
aimed at"*: a probe answering a question nobody asked, formatted as a result.
`verify_family.py` resolves membership by call site instead.

## What the four survivors had in common

All four dropped or nullified the **exception**, never the code:

    failopen.record("CHZ-FO-ROUTER-BASELINE-ESTIMATE", )        # default removed
    failopen.record("CHZ-FO-ROUTER-PRICE-TABLE-VERSION", None)  # exc -> None
    failopen.record("CHZ-FO-ROUTER-PROVIDER-PARSE", None, detail=...)
    failopen.record("CHZ-FO-ROUTER-PROVIDER-PARSE", detail=...)

`record()` writes `payload["e"] = type(exc).__name__` **only when `exc` is not None**, and
`FailOpenCounts.by_code` aggregates by code alone. So a record that has lost its exception
is invisible through the public API, and every assertion in the first six tests still
passed.

It matters for the same reason the code does. *"CHZ-FO-ROUTER-BASELINE-ESTIMATE fired 40
times"* says a site degraded. *"…40 times, all ConnectionError"* says why. Without the
type the record names a symptom and stops.

Adding one assertion class — the recorded exception type — took the family from 7/11 to
**11/11** and the collateral from 4/30 to 7/30.

## FINDING — Amendment 1's exclusion rule fires on PROSE, not just invocation

This file's docstring explained the relation to finding #32 by naming the repo's
fail-open linter. Rule B in `scripts/gf_excluded_tests.py` matches a gate script's name
as a plain substring anywhere in the module-level segment:

    hit = sorted({g for g in _GATE_SCRIPTS if g in segment})

So the mention — in a docstring, written to explain why the tests exist — classified the
**entire file** as excluded from the G-F run. A deselected test cannot kill anything, so
the sentence describing the work would have silently cancelled it. The failure surfaced
only because `test_gf_exclusions_derived.py` compares the derived set against the config
and refused to match.

This is the Phase 1 defect inverted. There it was *a guard a comment can satisfy is a
guard that cannot fail*; here a comment TRIGGERS an exclusion. Same root cause: a rule
matching text where it means to match behaviour.

**The rule is NOT changed here.** The failing test's own message says to amend protocol
doc 20 before changing the rule, and doc 21 records that a third amendment is a signal to
reassess the instrument rather than keep amending. The file now refers to the linter by
description; the rule's weakness is recorded instead of worked around silently.

**Left for the owner:** eight test files mention a gate-script name. Which of those
invoke one and which merely mention it has not been audited, so it is unknown whether any
currently-excluded test is excluded for a reason that is only textual. If some are, the
qualification is being measured with real tests removed from it.

## FINDING — an order-dependence I introduced, of the class 63cbc8c removed

Two of these tests passed alone and failed in the full suite: `FileNotFoundError` on the
fail-open store, i.e. no record was written, i.e. the error path never ran.

`from chuzom import calibration` tries `getattr(chuzom, "calibration")` first. Once any
earlier test has imported the submodule it is bound as an attribute of the package, that
getattr succeeds, `sys.modules` is never consulted, no exception is raised, and the
fail-open path is not entered. Setting only the `sys.modules` entry is therefore
order-dependent by construction.

Fixed by deleting the package attribute as well. Verified with a control that forces the
breaking order — `test_calibration.py` then this file — which now passes 24/24.

Worth stating plainly: `63cbc8c` made this suite order-independent, and a test added
afterwards reintroduced the same class. Order-independence is not a state the suite
reaches once; it is a property every new test can break. Running the new file alone
showed nothing.

## Three mistakes in writing these tests, all caught by measurement

1. **Asserted formatted JSON.** `'"e": "ValueError"' in raw_text` failed on all three
   cases: the store serialises with `separators=(",", ":")`, so the bytes carry no space.
   Now parses the JSONL, which states the claim (*this exception type was recorded*)
   rather than a claim about whitespace — and keeps the test clear of the serialisation
   format, itself a place where mutants are equivalent by construction.
2. **Missing import.** ruff, not the tests.
3. **Expected the wrong exception.** A `None` entry in `sys.modules` raises
   `ModuleNotFoundError`, not `ImportError`. The test was right and the expectation was
   wrong; it now pins the concrete type, which is what an operator reads.

## Relation to open finding #32

`lint_fail_open` cannot detect a fail-open that logs, so adding these modules to its
PROTECTED set yields zero violations — it is blind here by construction, and WP-13
("fail-open triage") used it as its instrument.

These tests are the independent check that gate cannot be: they assert observable
behaviour — the recorded code, the recorded exception type, the degraded return value —
rather than source shape. #32 stays open; its scope is now better understood, not closed.

## What is asserted, and why it is behavioural

Each site is driven through its real error path and checked on three observable facts:

| site | code | degraded return |
|---|---|---|
| `router._baseline_cost` | `CHZ-FO-ROUTER-BASELINE-ESTIMATE` | `0.0` — reads as "saved nothing", not a crash |
| `router._price_table_version` | `CHZ-FO-ROUTER-PRICE-TABLE-VERSION` | `"unknown"` |
| `router._model_tier` | `CHZ-FO-ROUTER-PROVIDER-PARSE` | tier `2` — mid external API, the conservative assumption |

Plus: the offending model is carried in `detail` (without it an operator knows a model
failed to parse but not which one), two different sites record two different codes, and
repeated failures at one site increment that site. The last two exist because a test
asserting merely "something was recorded" passes under a mutant that swaps one site's
code for another's.

## Remaining in C1

Eight of the eleven codes are untouched: `CHZ-FO-COST-BUDGET-ALERT`,
`CHZ-FO-COST-COVERAGE-COUNTS`, `CHZ-FO-COST-IDENTITY`, `CHZ-FO-COST-PRICING-REFRESH`,
`CHZ-FO-LEDGER-HOST-RATES`, `CHZ-FO-ROUTER-DESKTOP-NOTIFY`, `CHZ-FO-ROUTER-LEDGER-EMIT`,
`CHZ-FO-ROUTER-LEDGER-TERMINAL` — roughly 29 mutants.

`CHZ-FO-ROUTER-DESKTOP-NOTIFY` sits inside `router._native_notify`, one of the two
notification shims held for an owner decision in `gf_phase2_classes.md` §5. The fail-open
record there is worth asserting on its own terms even if the argv is not.

## What this does not claim

The score is unchanged until a full mutation run measures it: 18 kills across TRAIN and
VALIDATION would move the combined figure by roughly a point, and an estimate is not a
measurement. **G-F remains NOT QUALIFIED at 0.5866.**
