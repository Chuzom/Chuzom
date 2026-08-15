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
