# G-F Group B — `_aggregate` and `resolve` (iterations 1–2)

Date: 2026-08-15. Loop scope: one Group B function per iteration.

## Results

| function | combined kills | note |
|---|---|---|
| `execution_ledger._aggregate` | **25 / 51 (49%)** | with C6; this file added 14 net |
| `tool_surface.resolve` | written, 20 tests | **7 of its 37 mutants are unreachable** |

Baseline for the loop: with the gateway stopped, the full suite is **0 failures**. Any
failure from here is mine, which is a stricter bar than the "no new failures" rule the
owner approved.

## Finding: `resolve`'s `cand_door` branch is unreachable

The branch handles a chain entry reachable only through a door. Enumerated across every
tier × logical name, **respecting chain order, zero inputs reach it**: for every name,
either it is registered, its own door is registered (step 2 returns first), or an earlier
chain entry is directly registered.

Those 7 mutants are equivalent by construction. Running total of proven-equivalent
mutants: **14** (5 in `localize`, 2 in Group A, 7 here).

The test now asserts the UNREACHABILITY itself, so a future table change that makes the
branch live fails the test and someone writes real coverage. A comment would not.

### Two wrong turns getting there

1. The first test used `llm_analyze`, which HAS a registered door — so `resolve` returns
   at step 2 and step 3 never runs. The test claimed to cover the branch, passed, and
   killed none of the seven. The assertion was also an `or`, satisfied by either half.
2. The corrected enumeration **ignored chain order** and proposed `llm_classify`.
   `llm_route` comes first in that chain and IS registered, so resolution stops there.
   Only after walking the chain in order did the count come out zero.

Both were caught by running the thing, not by reading it.

## Finding: assertions that constrain shape but not value

`_aggregate`'s surviving mutants are dominated by `numeric_literal` (9). The cause is in
my own tests: the hook-overhead cases assert `> 0.0` and relative ordering
(`out_only > in_only`). Those kill the LOGICAL mutants — the metered-only guard, an
input/output swap — and leave every arithmetic constant alive. `/ 1_000_000` could become
`/ 100_000` and all of them still pass.

Closed with a test computing the expected dollar figure from the rates the ledger itself
publishes, so it is not a hardcoded number that goes stale.

**Fifth instance today of one shape**: an assertion that constrains the *shape* of an
answer but not its *value* — alongside `"a non-empty string"` for the codex baseline and
`"free (local)" in out` for the substring match.

## A tooling gap this iteration exposed

`verify_kills.py` takes ONE test file. Two files now target `_aggregate` (C6 closed the
accumulator class; this one closed the untouched branches), and neither number alone
describes what the suite catches. Added `verify_combined.py`, which takes several files.
Without it every future split-coverage function would have been misreported.

## Also caught: two concurrent verifications

Both copy test files into the shared `mutants/` tree and would clobber each other — a
hazard recorded in doc 22's own parallelism section this morning, then walked into
anyway. Stopped and re-run serially.

## Remaining in `_aggregate` (26)

    3x route_actual_tokens.get(rid, 0)        quota tested on realized routes only
    3x btok = r.get("baseline_tokens")        never set in any fixture
    2x host_mode = ...get(rid, "unknown")     no route with mixed host modes
    2x final_provider = ...get(rid, "")       covered empty, not carry-forward

---

# Iterations 3–5

| function | kills | note |
|---|---|---|
| `router._extract_retry_after` | **26/27 (96%)** | last survivor provably equivalent |
| `cost._validate_routing_insert` | **16/19 (84%)** | 3 unkillable — a DUPLICATE in the source |
| `coverage.snapshot` | **8/19 (42%)** | most survivors structurally unkillable |

## `_extract_retry_after` — the kill that took reading the mutant

`getattr(exc.http_response, 'headers', {})` looked equivalent: both spellings return None
when only the first exception shape exists. They diverge only on an exception carrying a
**headerless `http_response` AND a valid `_response`** — with the default the lookup falls
through and finds the second header; without it, `AttributeError` aborts and the
provider's actual backoff instruction is discarded. One test, 93% → 96%.

The remaining survivor is the same `getattr` on the LAST branch, where `{}` (key missing →
`return None`) and `AttributeError` (caught → `return None`) are observably identical.

This function decides how long to wait before retrying a rate-limited provider, and it
had **zero tests**. Returning None where a header existed means retrying too early and
burning more quota.

## `_validate_routing_insert` — a duplicate makes 3 mutants unkillable

    'claude_subscription', 'subscription', 'anthropic',
    'perplexity', 'groq', 'deepseek', 'cc',
    'anthropic', 'claude'  # variations

**`'anthropic'` appears twice.** In a frozenset the second occurrence is a no-op, so
mutating either copy leaves the other and the set is unchanged.

Not removed. Deleting the duplicate is a one-word source change that would make three
mutants killable — a production change motivated by a mutation score, which this campaign
treats as the wrong reason. The test asserts the duplicate EXISTS, with a message saying
that if it is ever removed, those mutants became killable and the test should be replaced
with real coverage.

## `coverage.snapshot` — a DEFECT found by the tests

`json.loads` succeeds on a JSON array or string, but the `try/except` wraps **only the
parse**. `event.get("k")` then raises `AttributeError` on a non-dict and escapes the loop
entirely, so ONE such line discards the whole store instead of counting itself malformed.

That contradicts the module's own comment: *"Partial corruption still reports, because a
partial count beats no count as long as the total is not silently understated."*

Caller impact is a silent degrade, not a crash — `cost._coverage_counts` catches it and
records `CHZ-FO-COST-COVERAGE-COUNTS`, so coverage reports zeros and every rate downstream
renders Unknown.

Marked `xfail(strict=True)` rather than asserting the buggy behaviour as correct: encoding
a defect as the contract is a documented antipattern in this campaign (lesson (l)), and
`strict=True` means the test FAILS the moment a guard is added, prompting real coverage.

### Why 42% is the honest ceiling here

Most survivors cannot be killed behaviourally:

* **5× `malformed += 1`** — `malformed` is a LOCAL whose value never escapes. The only
  reader is `if malformed and observed == 0 and unobserved == 0`, which tests truthiness.
  `+= 1` and `= 1` are indistinguishable because the count is never exposed on `Coverage`.
* **1× `lines: list[str] = []`** — reassigned immediately inside the `try`; the `except`
  returns early. The initialiser is dead.

Exposing `malformed` on `Coverage` would make five mutants killable and is arguably a
better design (an operator seeing "3 malformed lines" learns more than a boolean). It is
still a production change driven by a score, so it is recorded, not made.

## Running total of PROVEN-EQUIVALENT mutants: ~23

5 `localize` · 2 Group A · 7 `resolve` · 1 `_extract_retry_after` · 3
`_validate_routing_insert` · ~6 `coverage.snapshot`. Doc 20 §4 counts these as survivors
by design; at ~1% of 1986 they do not threaten the floor, but they do mean 1.00 is not
achievable and the practical ceiling is lower than the arithmetic suggests.

---

# Iteration 6 — `router._emit_ledger_attempt`: 19/22 (86%), and 19/19 of what is killable

All three survivors are the SAME equivalence pattern — a `getattr` default immediately
neutralised by an `or`:

    model=getattr(response, "model", "") or model        default "" -> None: `or model` either way
    provider=getattr(response, "provider", "") or ""     default "" -> None: `or ""` either way
    measured_cost_usd=float(getattr(..., 0.0) or 0.0)    default 0.0 -> None: `or 0.0` either way

**A `getattr` default followed by `or <equivalent fallback>` makes the default
unobservable.** Worth naming as a class: it appears three times in one function and once
more in `_extract_retry_after`, and it will appear wherever this defensive idiom is used.

## Why this function's fields were worth 18 tests

It records EVERY billable attempt — accepted, gate-rejected, quality-rejected — because
`cost.log_usage` runs only for the winner and structurally omits the rest. The aggregation
layer derives route and session totals from these rows, so a wrong field is a wrong number
on the dashboard, never a crash. The whole function is fail-open by design, so the emitted
row is the ONLY thing that can catch a mutation.

`route_id = ledger_route_id or correlation_id or ""` is the subtlest: when the hook minted
a route_directive_id, the billable row must use it so the ledger join with the adoption row
fires. Reversing that precedence leaves both rows present and never matching — realized
savings silently collapse to zero.

# GROUP B COMPLETE — 6 of 6 functions

| function | kills | note |
|---|---|---|
| `execution_ledger._aggregate` | 25/51 (49%) | with C6 |
| `tool_surface.resolve` | — | 7 of 37 UNREACHABLE |
| `router._extract_retry_after` | 26/27 (96%) | last survivor equivalent |
| `cost._validate_routing_insert` | 16/19 (84%) | 3 unkillable: a duplicate in the source |
| `coverage.snapshot` | 8/19 (42%) | ~6 structurally unkillable |
| `router._emit_ledger_attempt` | 19/22 (86%) | all 3 survivors equivalent |

Full suite 0 failures against a 0-failure baseline at every commit.

## Three production defects found, NONE fixed

Each would have moved the score with a one-line edit. Changing shipped code to improve a
mutation number is the motivation this campaign treats as disqualifying, so all three are
recorded for the owner instead:

1. **`coverage.snapshot` crashes on non-dict JSON** — `event.get("k")` raises
   AttributeError outside the try, so ONE array line discards the whole store. Marked
   `xfail(strict=True)` so it fails the moment a guard is added.
2. **`'anthropic'` is in the provider allowlist twice** — the duplicate makes both copies
   unkillable.
3. **`malformed` is counted but never exposed** — only its truthiness is read, so 5
   accumulator mutants cannot be distinguished. Exposing it on `Coverage` would arguably
   be better design (an operator seeing "3 malformed lines" learns more than a boolean).
