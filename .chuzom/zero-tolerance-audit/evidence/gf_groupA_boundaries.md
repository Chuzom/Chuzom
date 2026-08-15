# G-F Group A — boundary, default and env-override classes

Date: 2026-08-15. Doc 22 W1 Step 1. Two new files, **28 kills of 62 targeted mutants**,
each verified per mutant with a no-mutant control passing first.

## Result

| file | tests | kills |
|---|---|---|
| `test_gf_c7_boundaries.py` | 33 | **15 / 40** |
| `test_gf_c2c3_defaults_and_env.py` | 23 | **13 / 22** |

Per function:

    budget.reserve_for                     1/1    cost.format_spend_for_display   1/1
    budget.release_for                     1/2    router._stable_task_offset      1/2
    budget._get_pending_pressure_offset    1/2    router._needs_precise_answer    1/3
    router._format_subprocess_chain_error  5/10   cost._validate_routing_insert   4/19
    tool_surface.active_slim               2/2    tool_surface.tool_for_task      3/3
    cost._get_gemini_baseline_for_task     4/5    cost._get_codex_baseline_for_task 2/3
    classify.classify_signals              2/6    classify.apply_complexity_floor 0/2
    tool_surface.registered_tools          0/1

## THREE tests passed and killed NOTHING

The point of per-mutant verification, in three concrete cases. Each required reading the
mutant to find the input that separates it — none was reachable by reasoning about the
function alone.

**`budget.release_for`** — `if cost_usd <= 0` → `< 0`. Four sensible boundary tests all
passed against the mutant: releasing 0.0 from an entry of 1.0 leaves 1.0 either way, since
the guard returns early *or* the arithmetic subtracts nothing and rewrites the same value.
The behaviours diverge only on an entry of **exactly 0.0**, where `< 0` falls through,
computes `max(0, 0 - 0) == 0.0`, and **deletes the key**.

**`budget._get_pending_pressure_offset`** — `<= 0` → `<= 1`. Zero pending tokens and 2,500
pending tokens both pass under either spelling. Only **`pending == 1`** separates them: the
mutant swallows the smallest real backlog and reports zero pressure for a provider that
has work outstanding.

**`cost._get_codex_baseline_for_task`** — the original test asserted the fallback was "a
non-empty string". That assertion cannot fail. It killed 0 of 3, because every mutant lives
in the *override* path the test never exercised. Replaced with real override cases
(valid / case-and-whitespace / unpriced), now 2 of 3.

The third is the sharpest: a test that reads sensibly, passes, and is worth nothing.
Verification is the only thing that tells it apart from a real one.

## Two further PROVEN equivalent mutants

Added to the five in `gf_equivalent_mutants_proven.md`; total now **7**.

* `tool_surface.registered_tools`: `_TIERS.get(tier, None)` → `_TIERS.get(tier)`.
  **Identical** — `dict.get(k)` already returns `None`. Unkillable by construction.
* `budget.release_for`: `pop(key, None)` → `pop(key, )`. The call sits inside
  `if key in _pending_spend_by_key`, so the default is unreachable and the missing-key
  branch cannot be entered.

## A test-design note: asserting a property, not a magic number

`classify_signals`'s confidence boundary (`best_score >= _CONFIDENCE_THRESHOLD`) cannot be
pinned by finding a prompt that scores exactly the threshold — that would hardcode the
scoring weights and become a change-detector the first time a keyword is added.

Instead the test asserts the *relationship* over six prompts:

    assert s.confident is (s.score >= classify._CONFIDENCE_THRESHOLD)

which fails the moment `>=` becomes `>` and any prompt lands on the boundary, without
depending on which prompt does.

## Signature errors in the drafts, and why they happened

Both files were drafted while a mutation run held the machine, so nothing could be
executed. Four assumptions were wrong: `_validate_routing_insert` takes
`(final_model, final_provider, cost_usd)`; `calc_savings` takes `tokens_used`
positionally and has no `baseline` kwarg; `classify_signals` takes a **prompt string**,
not a score map; `apply_complexity_floor` takes `(complexity, task_type)` and clamps *up*
to a task's floor.

The last changed the test's meaning, not just its call — it was written as "unknown
complexity ranks zero" and is really "unknown *task type* has no floor, so complexity
passes through". Drafting without execution is workable; shipping without it is not.

## Largest remaining gap in this class

`cost._validate_routing_insert` at 4 of 19. The tests cover the cost-plausibility guard;
the model-name and provider validation paths are untouched.

---

## Suite verification blocked by an unrelated finding: the gateway holds 47 FDs on usage.db

The full-suite run reported 14 failures. None are caused by these files — they fail
identically when run alone, with:

    sqlite3.OperationalError: database is locked
    fail_open code=CHZ-FO-COST-MIGRATE-ALTER exc=OperationalError

Traced with `lsof`:

    PID 31892  elapsed 04:02:14
    /Users/yaliandrona/Projects/Chuzom/.venv/bin/python -m chuzom.gateway
    47 open file descriptors on ~/.chuzom/usage.db

**Forty-seven concurrent descriptors on one SQLite file from a single long-running
process** is not ordinary connection use — it is connections being opened and never
closed. Over four hours it accumulated enough to starve other writers, which is what the
suite hit.

This is the same shape as `audit_37_state_root_inventory.md`: the gateway resolves its own
database path, opens its own connections, and nothing coordinates between it and anything
else that writes there.

**Not acted on.** Killing a running service the user started is their decision, not an
audit's. Recorded here and left for the owner. The Group A files themselves pass — the
failures are environmental and reproduce without them.

Suite verification for this change is therefore **incomplete**: the two new files pass in
isolation and per-mutant verification is complete, but a clean full-suite run needs the
gateway stopped first.
