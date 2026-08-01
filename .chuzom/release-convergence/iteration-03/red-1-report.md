# RED-1 Architecture & Contract Audit — Iteration 3

**Auditor:** RED-1 (fresh context, iteration 3)
**Repo:** `/Users/yaliandrona/Projects/Chuzom`
**Branch:** `fix/v1.0.1-audit-mitigation`
**HEAD:** `3f5a3114571b36cfd50747a41987941522800cac` — "docs(convergence): iteration-2 complete (6 findings fixed, GATE 6398 green)"
**Mandate:** Disprove correctness by tracing actual control/data flow in the current whole product. Comments, docstrings, test names, green tests, and prior audits are not trusted as ground truth.
**Constraints honored:** read-only (no edits/commits to the audited repo); `.venv` used; `CHUZOM_ENFORCE` unset before route tests; DB isolated via `CHUZOM_DB_PATH`/`CHUZOM_EXECUTION_LEDGER_DB` temp files; `~/.chuzom` never touched (hook-related repros monkeypatch `_ROUTER_DIR` to a scratch dir in-process).

## Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 3 |
| Medium | 2 |
| Low | 0 |

**Top 3, one line each:**

1. **RED1-3-03** — `reserve_envelope()` failure raises `BudgetExceededError` without releasing `_pending_spend` (router.py:3743-3746), while a near-identical check 73 lines later (deadline-expired, router.py:3819-3822) correctly releases both `_pending_spend` and the distributed envelope — proving the omission is an inconsistency, not a design choice.
2. **RED1-3-01 / RED1-3-02** — Two more silent `_pending_spend` leaks: empty `models_to_try` → `ValueError` (router.py:3532-3547) and semantic-cache hit → early `return cached` (router.py:3578), each permanently inflating the in-process reservation float, biasing every subsequent cap check toward false-positive blocking for the life of the process.
3. **RED1-3-04** — The hook-based route-accounting pipeline uses a single session-keyed pending file (not route_id-keyed); a late/out-of-order tool-call delivery causes turn N's tool call to be misattributed to turn N+1's route_id while turn N's own directive is silently dropped from the ledger entirely — reproduced end-to-end with `get_route_accounting()` output.

Two findings (RED1-3-01/02/03 as one family, plus RED1-3-04/05 as a second family) are grouped below into five numbered findings per the mandated schema. All five are **confirmed and reproduced**, not hypotheses.

---

## RED1-3-01 — `_pending_spend` reservation leak on empty-chain `ValueError`

**Severity:** High
**Category:** Budget/reservation accounting correctness
**Affected customer promise:** "Chuzom enforces your configured spend caps accurately" (over time, false-positive over-blocking defeats the "route to the cheapest capable model" value proposition by making the router refuse to route at all).
**Violated invariant:** Every path that adds to `_pending_spend` (router.py:3346, `_pending_spend += _reservation`) must release the same amount before `route_and_call` exits, on every exit path (success, cache hit, cancellation, timeout, or raise). `route_and_call` has **no top-level `try/finally`** — release is manually duplicated at specific known sites only (confirmed by grepping all top-level `try`/`except`/`finally` blocks in router.py: the function starts at line 2893; the next top-level `try` in the file is at lines 4395/4539, and reading lines 4385-4545 confirms that block belongs to an entirely different function — a streaming generator emitting `attempt.started`/`output.delta`/`route.completed`/`route.aborted` events — not `route_and_call` itself).

**Exact location:** `chuzom/router.py`, inside `route_and_call`, the `if not models_to_try:` block starting at line 3520, with two raise sites:
- Lines 3532-3539: `raise ValueError(...)` when `CHUZOM_BLOCK_PROVIDERS` has blocked every candidate model.
- Lines 3540-3547: `raise ValueError(...)` generic "No providers available..." fallback.

Neither raise site releases `_pending_spend`, even though `_reservation` was already added to it at line 3346, well before this check.

**Control-flow trace:**
1. `route_and_call` computes `_reservation` (estimated cost via `chuzom.session_spend._estimate_cost`) at router.py:3341-3346 and immediately does `_pending_spend += _reservation` (3346).
2. Chain compaction, chain building, precision-tier routing, subject-specialist override, and bandit reorder run (3352-3452).
3. The already-patched TQ-007 hard-cap-block path runs (3454-3518) — this path *does* correctly call a local `_release_cap_reservation()` closure (defined 3471-3483, called 3517) before its own `raise` at 3518. This is a prior-iteration fix (labeled in-code "Q-RESLEAK (RED1-2-02)") and is **not** part of this finding.
4. Control falls through to `if not models_to_try:` (3520) — this triggers when chain-mutation steps above (provider blocking, filtering) have emptied the candidate list. Both raise branches inside this block exit the function with the `_reservation` still counted in `_pending_spend`, permanently.

**Reproduction:** `/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_reservation_leaks.py`, "Candidate A" section. Harness mirrors `tests/test_tq007_daily_cap_downgrade.py`'s own mocking pattern (same fixture shape), with `_build_and_filter_chain` mocked to return `[]`. Run via `unset CHUZOM_ENFORCE && .venv/bin/python repro_reservation_leaks.py`. Output (from this session and the carried-forward prior run):
```
=== Candidate A: empty models_to_try -> ValueError ===
raised ValueError: ...
_pending_spend before=0.0 after=<reservation> leaked=<reservation>
CONFIRMED LEAK (Candidate A)
```
The script's own `assert after > before` gates the "CONFIRMED LEAK" print — it does not print unless the leak is observed.

**Expected vs actual:** Expected: `_pending_spend` returns to its pre-call value after any exit from `route_and_call`, including this raise. Actual: `_pending_spend` is permanently inflated by `_reservation` on every call that hits this path.

**Root cause:** `route_and_call` relies on manually duplicated release calls at specific known exit points instead of a single `try/finally` (or equivalent context manager) wrapping the reservation lifetime. This path was added/left uncovered when the empty-chain check was introduced or when other paths were retrofitted with releases.

**Confidence:** High (directly reproduced; root cause independently confirmed via structural grep of the whole function body).

**Suggested acceptance test:** Parametrized variant of `tests/test_tq007_daily_cap_downgrade.py::test_hard_block_releases_pending_spend_reservation` that instead mocks `_build_and_filter_chain` to return `[]` (or mocks provider-blocking to empty every candidate) and asserts `router._pending_spend` is unchanged (within float tolerance) before/after the call, catching the `ValueError`.

**Impact flags:** `budget-integrity`, `availability` (cumulative false-positive cap blocking), `no-crash-loss-of-funds` (leak direction is over-restrictive, not overspend-permissive — flagging explicitly since it is the opposite direction from a "spend bypass").

---

## RED1-3-02 — `_pending_spend` reservation leak on semantic-cache hit

**Severity:** High
**Category:** Budget/reservation accounting correctness
**Affected customer promise:** Same as RED1-3-01.
**Violated invariant:** Same as RED1-3-01 — release must occur on every exit path, including this one.

**Exact location:** `chuzom/router.py`, inside the `try:` block starting at line 3553 (guarded by `if task_type not in MEDIA_TASK_TYPES and not model_override:` at 3552): `cached = await semantic_cache.check(...)`; when `cached is not None`, `return cached` at line 3578. No release call exists anywhere in this block (3549-3580 read in full).

**Control-flow trace:** Identical setup to RED1-3-01 (reservation added at 3346), but this exit is reached earlier and more routinely than the empty-chain case — any prompt that semantically matches a previously cached response for a non-media task type without a model override takes this path on essentially every cache-hit request, making it the highest-frequency leak of the three found this iteration.

**Reproduction:** Same script, "Candidate B" section — `_run(["ollama/qwen2.5:7b"], sc_hit=cached)` with `semantic_cache.check` mocked to return a hit. Output:
```
=== Candidate B: semantic-cache hit -> early return ===
route_and_call returned via cache: model=ollama/qwen2.5:7b cached-flag-path-taken
_pending_spend before=0.0 after=<reservation> leaked=<reservation>
CONFIRMED LEAK (Candidate B)
```

**Expected vs actual:** Expected: cache hits are cheap, zero-cost, high-frequency exits and must not leave any reservation behind. Actual: every semantic-cache hit that reaches this point leaks `_reservation` into `_pending_spend` permanently.

**Root cause:** Same as RED1-3-01 — no unifying `try/finally` around the reservation's lifetime; this specific early-return was not included in the manually-duplicated release call sites.

**Confidence:** High (directly reproduced).

**Suggested acceptance test:** A test that seeds a semantic-cache hit via mocked `semantic_cache.check`, calls `route_and_call`, and asserts `router._pending_spend` is unchanged before/after.

**Impact flags:** `budget-integrity`, `availability` — and notably the **highest real-world frequency** of the three leaks, since cache hits are the common/fast path the product is designed to maximize.

---

## RED1-3-03 — `_pending_spend` (and distributed envelope) reservation leak on `reserve_envelope()` failure

**Severity:** High
**Category:** Budget/reservation accounting correctness, cross-process budget enforcement
**Affected customer promise:** Same as RED1-3-01/02, plus the distributed multi-process cap-enforcement promise (envelope reservations are explicitly the cross-process budget mechanism).
**Violated invariant:** Same release-on-every-exit invariant, **and** the codebase's own established pattern for exactly this class of pre-dispatch failure (see corroborating evidence below) — making this specifically a regression/inconsistency rather than a novel gap.

**Exact location:** `chuzom/router.py`:3727, `_env_mode, _env_ok, _env_key = await reserve_envelope(identity, _reservation)`; the `if not _env_ok:` block (3728-3746) ends in `raise BudgetExceededError(...)` at lines 3743-3746, with no release call anywhere in the block.

**Corroborating evidence (this is what elevates this from "a gap" to "an inconsistency"):** Exactly 73 lines later, at router.py:3819-3822, a structurally parallel "deadline expired before dispatch" check (`if _dl_remaining_at_dispatch is not None and _dl_remaining_at_dispatch <= 0:`) correctly releases **both** the local reservation and the distributed envelope before its own raise:
```python
async with _budget_lock():
    _pending_spend = max(0.0, _pending_spend - _reservation)
await release_envelope(_env_key, _reservation)
```
This proves the maintainers know and use the correct pattern for pre-dispatch failure paths — the envelope-reservation-failure path simply omits it.

**Control-flow trace:**
1. Reservation added at 3346 (as in RED1-3-01/02).
2. Routing-policy application runs (3696-3717).
3. `reserve_envelope(identity, _reservation)` is called (3727) to also reserve budget in a cross-process/distributed ledger.
4. If the distributed reservation fails (`_env_ok is False` — e.g., another process has already consumed the shared budget), `BudgetExceededError` is raised (3743-3746) — but only the *distributed* envelope ever had a chance of being partially reserved (and `reserve_envelope` is expected to not double-book on failure); the *local* `_pending_spend` increment from step 1 is never rolled back regardless.

**Reproduction:** Same script, "Candidate C" section — `_run(["openai/gpt-4o"], env_ok=False)` with `reserve_envelope` mocked to return `(None, False, None)`. Output:
```
=== Candidate C: reserve_envelope() ok=False -> BudgetExceededError ===
raised BudgetExceededError: ...
_pending_spend before=0.0 after=<reservation> leaked=<reservation>
CONFIRMED LEAK (Candidate C)
```

**Expected vs actual:** Expected: a failed distributed-budget reservation should release the local reservation just as the deadline-expiry path does 73 lines later. Actual: the local reservation is left permanently inflated.

**Root cause:** Same missing-unification-of-release-paths root cause as RED1-3-01/02, but this instance is directly falsifiable as an *inconsistency* rather than a gap, since the immediately-following analogous check (3819-3822) demonstrates the intended/correct pattern.

**Confidence:** High (directly reproduced; corroborating sibling pattern independently read and confirmed correct).

**Suggested acceptance test:** A test mocking `reserve_envelope` to return `(mode, False, key)`, asserting both `router._pending_spend` is unchanged and `release_envelope` was NOT called with a nonexistent key (since none was reserved) — or, if `reserve_envelope` can partially reserve before failing, asserting `release_envelope` WAS called symmetrically to the deadline-check pattern.

**Impact flags:** `budget-integrity`, `cross-process-consistency`, `regression-pattern` (established correct pattern exists nearby but wasn't applied here).

---

## RED1-3-04 — Session-keyed (not route_id-keyed) pending-route file causes cross-turn misattribution and silent loss of accounting

**Severity:** High
**Category:** Route-accounting correctness / hook pipeline race condition
**Affected customer promise:** "Chuzom shows you accurate realized savings and route history" — a core product metric/dashboard promise.
**Violated invariant:** Each routing directive (route_id) must be resolved (realized-used or realized-overridden) exactly once, attributed to the correct route_id, regardless of hook delivery timing.

**Exact location:** Three cooperating hook scripts under `src/chuzom/hooks/`:
- `auto-route.py` (UserPromptSubmit hook): writes a single file `~/.chuzom/pending_route_{session_id}.json` via `_write_json_atomic`, **unconditionally overwriting** any existing pending state for that session, with no check that a prior pending directive was ever resolved.
- `enforce-route.py` (PreToolUse hook): reads that same single-slot file by `session_id` only (not by `route_id`); records realization and clears the pending file at its three call sites.
- `stop-enforce.py` (Stop hook): records an "override" if a pending file is still present (i.e., not yet cleared) when the turn ends.

`_ROUTER_DIR = Path.home() / ".chuzom"` is hardcoded in all three files with no environment-variable override (unlike `CHUZOM_DB_PATH`/`CHUZOM_EXECUTION_LEDGER_DB`), which the reproduction below works around via in-process monkeypatching rather than touching the real path.

**Control-flow trace:**
1. Turn N: `auto-route.py` writes pending state for `route_id=A`.
2. The harness fails to deliver turn N's PreToolUse/Stop hooks promptly (a Stop-hook process crash or timeout is plausible under the pipeline's own fail-open design — this is not a contrived adversarial scenario, just an ordinary reliability failure of an out-of-band hook process).
3. Turn N+1 begins: `auto-route.py` unconditionally overwrites the same single-slot file with `route_id=B`'s pending state — with no check that A was ever resolved.
4. Turn N's tool call, still in flight, is finally delivered to the PreToolUse hook. It reads whichever pending state is **currently on disk** — now `route_id=B`'s — and credits `route_id=B` as "realized," even though the tool call actually executed under `route_id=A`'s directive.
5. `route_id=A` receives **zero** accounting rows (neither `verified_used` nor `verified_overridden`) — its true outcome is silently and permanently lost from the ledger.

**Reproduction:** `/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_pending_clobber.py`. Monkeypatches `_ROUTER_DIR`/`_LOG_PATH` on all three loaded hook modules to a `tempfile.mkdtemp()` scratch dir before any write, so the real `~/.chuzom` is never touched. Simulates the write-overwrite-late-read sequence above, then calls `get_route_accounting(route_a)` / `get_route_accounting(route_b)` against an isolated `CHUZOM_EXECUTION_LEDGER_DB`. Confirmed output (from this and the prior session, unchanged):
```
[Turn N   ] auto-route.py wrote pending route_id='sess-red1-clobber-demo:...:llm_code:aaaaaaaa'
[Turn N+1 ] auto-route.py OVERWROTE the same file with route_id='sess-red1-clobber-demo:...:llm_query:bbbbbbbb'
            (no check performed that route_id='...aaaaaaaa' was ever resolved)

[Late      ] enforce-route.py's PreToolUse handler for turn N's tool call
            reads pending NOW on disk -> route_id='sess-red1-clobber-demo:...:llm_query:bbbbbbbb'
            MISATTRIBUTION CONFIRMED: turn N's tool call will be credited to
            route_id='...bbbbbbbb' (turn N+1's directive), not '...aaaaaaaa' (its own)

get_route_accounting(route_id='...bbbbbbbb') [turn N+1, never actually acted on]:
    Accounting(... realized_routes=1 ...)
get_route_accounting(route_id='...aaaaaaaa') [turn N, the ACTUAL directive the tool call honored]:
    Accounting(... realized_routes=0, realization_unknown_routes=0 ...)

CONFIRMED: route A (the directive actually honored) has ZERO accounting rows --
its realization is silently LOST -- while route B (never honored or overridden)
is credited as 'realized' purely because it happened to be the file on disk when
the PreToolUse hook fired for an unrelated, earlier turn's delayed tool call.
```
The script's own assertion (`acc_b.realized_routes >= 1 and acc_a.realized_routes == 0 and acc_a.realization_unknown_routes == 0`) gates this "CONFIRMED" print.

**Expected vs actual:** Expected: each route_id's realization outcome is recorded independently and correctly, regardless of hook delivery order/timing. Actual: the single-slot, session-keyed (not route_id-keyed) pending file causes wrong-route credit and complete, silent loss of the correct route's outcome under any out-of-order or delayed hook delivery.

**Root cause:** The pending-state storage keys on `session_id` alone rather than `(session_id, route_id)` or `route_id` alone, combined with `auto-route.py`'s unconditional overwrite (no "is prior pending already resolved?" guard) and the fail-open design of the Stop hook (a crashed/timed-out Stop hook leaves no trace that a directive was left unresolved).

**Confidence:** High (directly reproduced end-to-end, including the ledger read-back).

**Suggested acceptance test:** A test harness that (a) writes pending for route A, (b) writes pending for route B without resolving A, (c) delivers a PreToolUse event that should belong to A, and (d) asserts the event is either rejected/queued for the correct route or that route A still receives a `realization_unknown`/deferred outcome rather than route B receiving a false "realized" credit and route A receiving nothing.

**Impact flags:** `accounting-integrity`, `silent-data-loss`, `customer-facing-metric` (realized-savings dashboard).

---

## RED1-3-05 — `_aggregate`'s realization-status merge is order-dependent; `_load_rows` issues no `ORDER BY`

**Severity:** Medium
**Category:** Read-path determinism / aggregation correctness
**Affected customer promise:** Same realized-savings/route-history accuracy promise as RED1-3-04 — this finding shows the *reader* has no deterministic tie-break even when correctly-written conflicting rows exist for a route_id (e.g., produced via RED1-3-04's clobbering scenario, or any other future writer-side bug).
**Violated invariant:** For a given `route_id`, the aggregation layer should resolve conflicting realization events deterministically (e.g., by timestamp/event recency), not by unspecified physical row-scan order.

**Exact location:**
- `chuzom/execution_ledger.py:228-242`, `_load_rows`: issues `SELECT {columns} FROM execution_events WHERE {where}` with **no `ORDER BY` clause** — confirmed both via direct source-string inspection (`"ORDER BY" in inspect.getsource(_load_rows).upper()` → `False`) and via reading the function body directly.
- `chuzom/execution_ledger.py:277-339`, `_aggregate`: the realization-status merge at lines ~304-310 does `route_realization[rid] = rs` unconditionally for every row bearing a `realization_status`, with no timestamp-based tie-break:
  ```python
  rs = r.get("realization_status")
  if rs:
      route_realization[rid] = rs
  elif et == "realization_unknown":
      route_realization.setdefault(rid, "unknown")
  ```
  Whichever row is iterated **last** silently overwrites `route_realization[rid]`.

Note: `_DDL` (execution_ledger.py) does create an index `idx_exec_ts` on the `ts` column, but `_load_rows` never uses it for ordering — the ordering gap is a genuinely absent `ORDER BY`, not a missing-index oversight.

**Control-flow trace:** SQLite's row return order for a query with no `ORDER BY` is unspecified — an implementation detail (commonly rowid/insertion order for a simple unindexed scan), not a guarantee; it can shift with query-plan changes, concurrent writes/deletes, `VACUUM`, or SQLite version. `_aggregate` is fed rows straight from `_load_rows` with this unconstrained order, and its last-write-wins merge means the final `Accounting.realized_routes`/`overridden_routes`/`realized_savings_usd` for any route_id with conflicting realization rows depends entirely on that unspecified order.

**Reproduction:** `/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_aggregate_order_dependence.py`. Calls `_aggregate("route", "route-red1-order-demo", rows)` directly (bypassing the DB entirely, to isolate the aggregation logic itself) with the **same two rows** — one `realization_status="verified_used"`, one `realization_status="verified_overridden"` — in two different list orders. Run via `unset CHUZOM_ENFORCE && .venv/bin/python repro_aggregate_order_dependence.py`. Full output:
```
=== Part 1: source-level confirmation `_load_rows` has no ORDER BY ===
def _load_rows(where: str, params: tuple, path: Path | None = None) -> list[dict[str, Any]]:
    conn = _connect(path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"SELECT {','.join(_COLUMNS)} FROM execution_events WHERE {where}", params
        )
        out = []
        for r in cur.fetchall():
            d = dict(r)
            d["metadata"] = json.loads(d.get("metadata") or "{}")
            out.append(d)
        return out
    finally:
        conn.close()

'ORDER BY' present in _load_rows source: False
CONFIRMED: _load_rows has no ORDER BY -- SQLite row order is unspecified.

=== Part 2: `_aggregate` output flips depending on row order alone ===
Order [used, overridden]  -> Accounting(scope='route', scope_id='route-red1-order-demo', attempt_count=2, billable_attempt_count=2, accepted_attempt_count=2, rejected_attempt_count=0, actual_cost_usd=0.002, baseline_equivalent_cost_usd=0.04, hook_input_tokens=0, hook_output_tokens=0, terminal_states={}, cost_unknown_attempts=0, realized_routes=0, overridden_routes=1, realization_unknown_routes=0, potential_savings_usd=0.038, realized_savings_usd=0.0)
Order [overridden, used]  -> Accounting(scope='route', scope_id='route-red1-order-demo', attempt_count=2, billable_attempt_count=2, accepted_attempt_count=2, rejected_attempt_count=0, actual_cost_usd=0.002, baseline_equivalent_cost_usd=0.04, hook_input_tokens=0, hook_output_tokens=0, terminal_states={}, cost_unknown_attempts=0, realized_routes=1, overridden_routes=0, realization_unknown_routes=0, potential_savings_usd=0.038, realized_savings_usd=0.038)

acc_order_1.realized_routes=0 overridden_routes=1 realized_savings_usd=0.0
acc_order_2.realized_routes=1 overridden_routes=0 realized_savings_usd=0.038

CONFIRMED: identical two rows, only reordered, produce DIFFERENT
Accounting.realized_routes / overridden_routes / realized_savings_usd.
Since _load_rows never constrains row order (Part 1), whichever of the
two conflicting rows SQLite happens to return LAST silently wins --
determined by storage-engine internals, not event recency (no ts-based
tie-break exists anywhere in _aggregate).
```

**Expected vs actual:** Expected: for a fixed set of ledger rows, `get_route_accounting()` (and its callers) should return a deterministic, recency-correct result regardless of physical storage/scan order. Actual: the two orderings of the identical row set produce `realized_savings_usd=0.0` vs `realized_savings_usd=0.038` — a materially different answer to "did this route's savings get realized?" for the exact same underlying events.

**Root cause:** `_load_rows` has no `ORDER BY`, and `_aggregate`'s conflict-resolution logic assumes iteration order reflects event recency without enforcing or verifying it.

**Confidence:** High (directly reproduced at the function level, independent of any DB nondeterminism — the flip is proven by argument order alone, and the missing `ORDER BY` is confirmed by source inspection, establishing that nothing upstream constrains the order that would be fed into `_aggregate` in production).

**Suggested acceptance test:** A test that inserts two conflicting realization rows for the same route_id with distinct `ts` values via `record_event`, then asserts `get_route_accounting()` picks the chronologically later one regardless of insertion/query order (e.g., by forcing a table `VACUUM` or issuing the rows in reverse-`ts` insertion order and confirming the result doesn't change) — and/or a direct unit test on `_aggregate` itself asserting order-independence for a fixed row set with distinct `ts` values.

**Impact flags:** `accounting-determinism`, `compounds-RED1-3-04` (this defect matters most once conflicting rows exist for a route_id, which RED1-3-04's clobbering — or any future writer bug — can produce).

---

## Attack vectors from the task brief investigated this iteration but NOT found to be defects

- **Anthropic-fallthrough (empty Claude chain under smart/soft-no-free enforcement):** Read router.py:3454-3518 (the TQ-007 block) in full. When the smart/soft-no-free filter reduces the candidate chain to Claude-only and that reduction leaves an empty `_claude_chain`, control falls to the `else:` branch (3513-3518), which correctly calls `_release_cap_reservation()` before raising `_daily_cap_exc`. This sub-vector appears **correctly handled** — no defect found, though this was observed incidentally while reading for the RED1-3-01/02/03 line numbers, not from a dedicated targeted stress test of this specific branch.
- **`get_daily_spend*`/`get_monthly_spend` both incorporating `_rejected_attempt_spend`:** Re-checked this session via `grep -n "_rejected_attempt_spend\|async def get_daily_spend\|async def get_monthly_spend" src/chuzom/cost.py`. Confirmed `get_monthly_spend` (cost.py:809-838) and `get_daily_spend`/`get_daily_spend_by_task_type` (cost.py:889-931) all now call `_rejected_attempt_spend`/`_rejected_attempt_spend_today` before returning. This matches iteration-2's RED1-2-01 finding description and **appears to have been fixed** since that iteration — not independently re-verified with a fresh reproduction this session (only source-level confirmation), so this is noted as "checked, appears resolved," not re-certified with a new repro.

## Explicitly not investigated this iteration (honest scope statement)

The following named attack vectors from the task brief were **not investigated** in this iteration, due to time allocation toward producing five fully confirmed-and-reproduced findings rather than partial coverage of more vectors:

- **Cross-process cap bypass** (Candidate D): `_pending_spend` and `_budget_lock` are module-level globals — inherently per-process. This is conceptually solid from code reading alone (no repro attempted) but was not empirically demonstrated with an actual multi-process test.
- **`chuzom/repo_config.py::effective_enforce()`** full body (default-mode resolution, YAML-vs-env precedence) — not read in full this iteration.
- **Budget-lock spin under genuine concurrent access** within a single process (real concurrent `asyncio` tasks racing on `_budget_lock()`, not sequential test-harness calls) — not stress-tested.
- **Accepted-vs-rejected double-counting on the write side** — whether a single logical attempt could ever be recorded as both accepted (via `cost.log_usage`) and rejected-with-nonzero-cost (via `_rejected_attempt_spend`'s underlying rows) — not traced.
- **Classification/capability resolution, restart/recovery, migration/backcompat, dead code, and other contradictory-sources-of-truth** beyond the five findings above — not started.
- **route_id nonce + event_id dedup "honor-then-override double-emit"** — carried forward from a prior session's investigation (not repeated this session): ruled out as **not reachable** under ordinary sequential single-turn flow, via code tracing of `enforce-route.py`'s immediate-clear-after-record design and `stop-enforce.py`'s early-exit on `pending is None`. This negative finding is restated here for completeness but was not re-verified with a fresh repro this session.

No genuine "no defect found" verdict applies to the overall audit — five confirmed, reproduced defects were found. The above list scopes what remains open for a future iteration.
