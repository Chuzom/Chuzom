# RED-1 Architecture & Contract Audit — Iteration 2

**Auditor**: RED-1 (independent, adversarial, read-only)
**Repo**: `/Users/yaliandrona/Projects/Chuzom`
**Branch**: `fix/v1.0.1-audit-mitigation`
**HEAD**: `509b03f6375eb21ef8a94c0b1ad6776a71a52b86` (2026-07-30 07:36:46 +0100)
**Mandate**: disprove correctness of routing/execution boundaries, classification & capability
resolution, daily-cap enforcement in `router.py::route_and_call`, the `_budget_lock` /
`get_daily_spend*` / `get_monthly_spend` cost accounting, execution-ledger `route_id`/`event_id`
dedup, and related invariants. No trust extended to comments, docstrings, test names, or
prior audit claims — only to traced control flow and executed reproductions.

**Constraints honored**: read-only throughout (no edits, no commits); all reproductions run
against isolated temp state (`CHUZOM_DB_PATH`/`CHUZOM_EXECUTION_LEDGER_DB` pointed at fresh temp
files, or fully mocked router dependencies via the existing `tests/test_tq007_daily_cap_downgrade.py`
harness pattern) — the real `~/.chuzom/usage.db` was never touched.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 2 |
| Medium | 1 |
| Low | 1 |

**Top 3, one line each:**

1. **RED1-2-01 (High)** — `cost.get_monthly_spend()` never adds rejected-attempt spend that
   `get_daily_spend()`/`get_daily_spend_by_task_type()` do include, so a real, billed,
   paid-provider spend of $50 shows up as `$50.00` on the daily check but `$0.00` on the
   monthly hard-block check — reproduced live: `daily=50.0, monthly=0.0`.
2. **RED1-2-02 (High)** — the TQ-007 hard-block exit path in `route_and_call`
   (`raise _daily_cap_exc` when no free-local model survives and `enforce="hard"`) leaks the
   `_pending_spend` reservation forever; reproduced live: after 3 consecutive hard-blocked
   calls in one process, `_pending_spend` grew `0.0 → 0.005005 → 0.01001 → 0.015015` and is
   never released, never tied to any day boundary.
3. **RED1-2-03 (Medium)** — `auto-route.py` derives `route_id` from `int(time.time())`
   (1-second resolution, not a real turn counter, despite the in-code claim of "unique per
   decision"), and `enforce-route.py`'s ledger `event_id = sha256(session_id|route_id|
   "route_realized")` is deduped via `INSERT OR IGNORE` — two distinct routing decisions for
   the same session+tool within the same wall-clock second silently collide and the second
   `route_realized` ledger row is dropped.

No Critical-severity finding was substantiated this iteration (the strongest candidate,
RED1-2-02, degrades cap-enforcement accuracy but does not itself allow unbounded paid spend —
see Impact Flags below).

---

## RED1-2-01 — Monthly hard-block budget omits rejected-attempt spend that the daily cap includes

**Severity**: High
**Category**: Cost/telemetry accounting — contradictory sources of truth
**Affected customer promise**: "Monthly budget is a separate, harder ceiling and still
hard-blocks" (verbatim in-code comment, `router.py` lines 3241-3253)
**Violated invariant**: A dollar of real (billed) spend must be visible identically to every
budget check that claims to bound total spend. Daily and monthly ceilings must agree on what
counts as "spent."

### Exact location

- `src/chuzom/cost.py::get_monthly_spend()` (lines 809-837) — sums only the `usage` table
  (`SELECT ... FROM usage WHERE strftime('%Y-%m', timestamp, 'localtime') = strftime('%Y-%m',
  'now', 'localtime')`). No call to `_rejected_attempt_spend_today()` or any monthly-scoped
  equivalent exists in this function.
- `src/chuzom/cost.py::_rejected_attempt_spend_today()` (lines 840-869) — sums
  `execution_events WHERE rejected = 1 AND COALESCE(measured_cost_usd, 0) > 0 AND
  date(ts, 'unixepoch', 'localtime') = date('now', 'localtime')`, optionally filtered by
  `task_type`. Fail-open (returns `0.0` on any exception).
- `src/chuzom/cost.py::get_daily_spend()` (lines 872-892) — returns
  `winning + await _rejected_attempt_spend_today(db)`. **Includes** rejected spend.
- `src/chuzom/cost.py::get_daily_spend_by_task_type()` (lines 895-916) — returns
  `winning + await _rejected_attempt_spend_today(db, task_type)`. **Includes** rejected spend.
- Consumer: `src/chuzom/router.py::route_and_call`, monthly hard-block check (lines 3320-3336):
  ```python
  if config.chuzom_monthly_budget > 0:
      monthly_spend = await cost.get_monthly_spend()
      budget = config.chuzom_monthly_budget
      if monthly_spend + _pending_spend >= budget:
          _enforce_or_warn(BudgetExceededError(...))
  ```

### Control-flow trace

1. A paid-provider attempt (e.g. `openai/gpt-4o`) runs, is billed, and is subsequently
   **rejected** by a downstream quality/safety gate. `execution_ledger.record_event()` writes
   an `attempt_rejected` row with `measured_cost_usd = 50.0`, `rejected = 1`.
2. Any later call computing `cost.get_daily_spend()` (or the per-task-type variant) sees this
   $50 via `_rejected_attempt_spend_today()` and correctly reflects it in the daily/task-type
   cap checks (`router.py` lines 3277-3318) — these checks work as documented.
3. The SAME call computing `cost.get_monthly_spend()` for the monthly hard-block check
   (`router.py` lines 3320-3336) does not see this $50 at all — it queries only the `usage`
   table, which this rejected/billed attempt was never written into (rejected attempts are
   ledger-only, not `usage`-table entries).
4. Net effect: a real $50 that already left the wallet is enforced against the daily ceiling
   but invisible to the monthly ceiling, directly contradicting the monthly budget's own
   documented purpose as "a separate, harder ceiling."

### Reproduction (executed, output pasted verbatim)

Script: `/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_red1_2_01.py`

Command:
```
unset CHUZOM_ENFORCE
source .venv/bin/activate
PYTHONPATH=src python /private/tmp/.../scratchpad/repro_red1_2_01.py
```

Output:
```
config.chuzom_db_path = /var/folders/.../repro_usage.db
expected tmp path      = /var/folders/.../repro_usage.db
record_event ok = True
get_daily_spend()                    = 50.0
get_daily_spend_by_task_type('code')  = 50.0
get_monthly_spend()                   = 0.0

CONFIRMED: rejected paid-provider spend counted in DAILY cap but INVISIBLE to MONTHLY cap.
```

(Isolation: `CHUZOM_DB_PATH` and `CHUZOM_EXECUTION_LEDGER_DB` both pointed at a fresh temp
file for the duration of the script; the real `~/.chuzom/usage.db` was never opened.)

### Expected vs actual

- **Expected**: `get_monthly_spend()` and `get_daily_spend()` agree on whether a real, billed,
  rejected attempt counts as "spent," since both are described as ceilings on the same
  underlying dollar spend.
- **Actual**: `get_daily_spend()` = $50, `get_monthly_spend()` = $0 for the identical
  underlying event.

### Root-cause hypothesis

`get_daily_spend()`/`get_daily_spend_by_task_type()` were patched (per in-code comment, under
a prior fix referencing rejected-attempt accounting) to add `_rejected_attempt_spend_today()`,
but no equivalent `_rejected_attempt_spend_this_month()` (or generalized date-range version)
was ever written or wired into `get_monthly_spend()`. The daily fix was not propagated to its
sibling function despite both being consumed by the same `route_and_call` budget-check block
seven lines apart.

**Confidence**: Confirmed (live reproduction, not a hypothesis).

### Suggested acceptance test

Add to `tests/` (e.g. alongside `test_tq007_daily_cap_downgrade.py` or a new
`test_monthly_spend_rejected_attempts.py`): insert an `attempt_rejected` `LedgerEvent` with a
positive `measured_cost_usd` timestamped "now," then assert
`await cost.get_monthly_spend() >= event.measured_cost_usd`, mirroring the existing assertion
style already used for `get_daily_spend()` in the daily-cap test suite. A second test should
drive `route_and_call` end-to-end (via the existing mocking harness) with a monthly budget set
just above a rejected attempt's cost and assert `BudgetExceededError` is NOT silently bypassed.

### Impact flags

- Telemetry/cost corruption: **Yes** — the monthly total the product reports to itself is
  systematically undercounted whenever any billed attempt is later rejected.
- False completion: No.
- Silent expensive routing: **Yes** — a caller whose daily cap resets (new day) but whose
  monthly ceiling should have already been reached (due to accumulated rejected-attempt spend
  across prior days) will continue to be routed to paid providers past the monthly ceiling,
  because the monthly check never sees that spend.
- File damage: No.

---

## RED1-2-02 — `_pending_spend` reservation leaks permanently on the TQ-007 hard-block raise path

**Severity**: High
**Category**: Concurrency / cost accounting — resource leak on error exit
**Affected customer promise**: Budget caps are accurate and self-correcting; a rejected call
should not itself distort the accounting used to evaluate the *next* call.
**Violated invariant**: Every reservation added to `_pending_spend` must be released exactly
once, on every exit path (success, downgrade, or raise) — per the function's own concurrency
design (module comment near line 1081: guarded increments/decrements to avoid lost updates).

### Exact location

- `src/chuzom/router.py::route_and_call` (function spans lines 2893-4017).
- Reservation added, inside `_budget_lock()`, lines 3338-3346:
  ```python
  try:
      from chuzom.session_spend import _estimate_cost as _est_fn
      _reservation = _est_fn("gpt-4o", len(prompt) // 4, 500)
  except Exception as e:
      log.debug("cost_estimation_failed", error=str(e))
      _reservation = 0.0
  _pending_spend += _reservation
  ```
- Hard-block raise, lines ~3454-3479 (TQ-007 downgrade filter, applied after chain building,
  precision-tier fronting, subject-specialist override, and bandit reorder):
  ```python
  if _daily_cap_exc is not None:
      _FREE_LOCAL_PROVIDERS = {"ollama", "codex", "gemini_cli"}
      _free_chain = [m for m in models_to_try if provider_from_model(m) in _FREE_LOCAL_PROVIDERS]
      if _free_chain:
          ...
          models_to_try = _free_chain
      elif _enforce_mode == "hard":
          raise _daily_cap_exc          # <-- exits here; _pending_spend never decremented
      else:
          ...  # fall through to Claude
  ```
- The only release sites for `_reservation` are inside `_dispatch_model_loop` (lines 2630,
  2782, 2814 — confirmed via grep), a **separate function** that `route_and_call` calls later,
  *after* the block above. When the `raise` at line ~3479 fires, `_dispatch_model_loop` is
  never invoked for this call, so its reservation is never released.
- Confirmed via `awk`/search across lines 2893-4017: **no 4-space-indented `try:` wraps the
  body of `route_and_call`**, i.e. no top-level `try/finally` exists to guarantee cleanup of
  `_pending_spend` on any exception exit, including this one.
- `_pending_spend` is a bare module-level `float` (declared ~line 1093), read by every future
  call's cap check (`daily_spend + _pending_spend >= _daily_limit`, `monthly_spend +
  _pending_spend >= budget`) and is **never reset by any clock/day-boundary logic** — only by
  explicit decrement call sites, none of which cover this path.

### Control-flow trace

1. Caller invokes `route_and_call` with a prompt; task-type or total daily cap is already
   exceeded (`_daily_cap_exc` gets set at lines 3277-3318, not raised yet).
2. Line 3346: `_pending_spend += _reservation` (a real, non-zero `gpt-4o`-priced estimate —
   confirmed via `session_spend.py::_estimate_cost` fallback logic, `"gpt-4o"` is not a
   known free-provider prefix).
3. Chain building/filtering runs; the resulting `models_to_try` contains no
   `ollama`/`codex`/`gemini_cli` entries (e.g. an org policy or classification pinned a
   paid-only chain).
4. `enforce_mode == "hard"` → `raise _daily_cap_exc` fires immediately, propagating out of
   `route_and_call` with no intervening `finally`.
5. `_pending_spend` retains the reservation added in step 2, forever (until process restart),
   silently inflating every subsequent cap check for the remaining lifetime of the process.

### Reproduction (executed, output pasted verbatim)

Using the exact mocking pattern from `tests/test_tq007_daily_cap_downgrade.py`
(`test_cap_hit_no_free_hard_blocks`): paid-only chain (`["openai/gpt-4o"]`), task-type daily
cap set to `$0.0001`, mocked `get_daily_spend_by_task_type` returning `9999.0` (guaranteed
over cap), `enforce="hard"`.

**Single call** (script:
`/private/tmp/claude-501/.../scratchpad/repro_red1_2_02.py`):
```
_pending_spend BEFORE call = 0.0
BudgetExceededError raised = True (Task-type daily limit for code ($0.00) exceeded
  (spent: $9999.0000 today UTC). Resets at midnight UTC. To raise the limit: update
  ~/.chuzom/org-policy.yaml task_caps or routing.yaml's daily_caps.code.)
_pending_spend AFTER call  = 0.00501

CONFIRMED: hard-block raise path leaked the reservation into _pending_spend. It is a
bare process-global float never tied to a day/month boundary -- it will never self-heal
and will bias every subsequent daily/monthly cap check upward, compounding with every
further hard-blocked call, until the process restarts.
```

**Compounding across repeated calls** (inline script, same process, 3 consecutive
hard-blocked calls):
```
start _pending_spend = 0.0
after call 1: _pending_spend = 0.005005
after call 2: _pending_spend = 0.01001
after call 3: _pending_spend = 0.015015

Simulated next-day check: real daily_spend=0.0, but daily_spend + _pending_spend =
0.015015 (nonzero purely from leaked reservations, never released, never reset by
day rollover)
```

### Expected vs actual

- **Expected**: `_pending_spend` returns to its pre-call value (`0.0` in this isolated test)
  after a call that neither dispatched nor committed any real spend — a rejected/blocked call
  reserved nothing that was ever actually spent.
- **Actual**: `_pending_spend` permanently retains the reservation, growing without bound
  across repeated hard-blocked calls, and is never tied to a wall-clock reset.

### Root-cause hypothesis

The reservation/release contract for `_pending_spend` was designed around the success path
through `_dispatch_model_loop` (which does correctly release at its own multiple exit points:
lines 2630, 2782, 2814). The TQ-007 hard-block raise was added as a short-circuit *before*
`_dispatch_model_loop` is ever reached, and its author did not extend the release contract to
cover this new early-exit path — likely because the reservation is added and the raise fires
in the same contiguous block of `route_and_call`, making the mismatch easy to miss without
tracing the full function (4017 - 2893 = 1124 lines).

**Confidence**: Confirmed (live reproduction, single-call and compounding-across-calls both
executed with pasted output).

### Suggested acceptance test

Add to `tests/test_tq007_daily_cap_downgrade.py`: after `test_cap_hit_no_free_hard_blocks`
raises, assert `router._pending_spend == 0.0` (or whatever its pre-call value was). Run the
existing hard-block test 3× in a loop within one process and assert `_pending_spend` does not
monotonically increase. The minimal fix is a `try/finally` around the reservation-consuming
portion of `route_and_call` (or moving reservation release into a context manager entered at
line 3346 and exited on every path, mirroring `_budget_lock`'s own `__aexit__` pattern).

### Impact flags

- Telemetry/cost corruption: **Yes** — `_pending_spend` is added into every subsequent daily
  and monthly cap comparison; a leaked reservation biases the process's view of "how much is
  currently at risk" upward, indefinitely.
- False completion: No.
- Silent expensive routing: **No** direct instance in this reproduction (the bias makes the
  system *more* conservative, not less — it will trigger cap-exceeded/downgrade behavior
  *earlier* than warranted on subsequent calls, which is a false positive in the opposite
  direction: legitimate paid-provider calls could be wrongly downgraded to free-local or
  wrongly hard-blocked because of dollars that were never actually spent). This is a
  correctness bug (wrong number reported/enforced) rather than a spend-cap bypass, which is
  why it is scored High rather than Critical.
- File damage: No.

---

## RED1-2-03 — `route_id` derived from 1-second wall-clock truncation permits execution-ledger collisions within a session

**Severity**: Medium
**Category**: Execution-ledger dedup / telemetry integrity
**Affected customer promise**: "A stable per-routing-decision id so the execution ledger can
attribute each realization/override to the specific route it corresponds to... unique per
decision" (verbatim in-code comment, `auto-route.py` lines 3495-3502).
**Violated invariant**: `event_id` (and its input `route_id`) must uniquely identify one
routing decision so that `INSERT OR IGNORE` dedup only ever suppresses true retries of the
*same* decision, never two distinct decisions.

### Exact location

- `src/chuzom/hooks/auto-route.py` line 3493: `"turn_id": int(_now)` (comment: "proxy for
  turn — clears when next prompt arrives") and line 3503:
  `"route_id": f"{_safe_sid(session_id)}:{int(_now)}:{tool}"`, where `_now = time.time()`
  (line 3466). Despite the surrounding comment calling this "unique per decision," the
  "turn" component is not a monotonic turn counter — it is the current Unix timestamp
  truncated to whole seconds.
- `src/chuzom/hooks/enforce-route.py` lines 488-496 (`_record_realization_used`):
  ```python
  _route_id = pending.get("route_id")
  _eid = hashlib.sha256(
      f"{session_id}|{_route_id or ''}|route_realized".encode()
  ).hexdigest()[:32]
  record_event(LedgerEvent(event_id=_eid, ...))
  ```
- `src/chuzom/hooks/stop-enforce.py` lines 104-112 (`_stable_event_id`): identical
  construction pattern (`sha256(f"{session_id}|{route_id}|{event_type}")[:32]`) with
  `event_type="plain_text_override"`.
- `src/chuzom/execution_ledger.py::record_event()` (lines 203-225): `INSERT OR IGNORE` keyed
  on `event_id` as PRIMARY KEY — designed for idempotent retries, silently drops any second
  insert with a colliding `event_id`.

### Control-flow trace

1. Two distinct user turns in the *same session* both route to the *same tool* (e.g. two
   rapid-fire prompts both classified as `code` → `llm_code`), and both `auto-route.py`
   invocations happen to compute `int(time.time())` to the same integer second (plausible in
   a scripted/automated session, or simply two hook invocations landing either side of a
   second boundary being truncated to the same value, or the same value by chance in a fast
   loop).
2. Both produce `route_id = "<sid>:<same_second>:<tool>"` — identical strings.
3. Both eventually reach `enforce-route.py::_record_realization_used` (or
   `stop-enforce.py`'s override path), each computing
   `event_id = sha256(f"{sid}|{route_id}|route_realized")[:32]` — identical hash.
4. The first `record_event()` call succeeds; the second is silently discarded by
   `INSERT OR IGNORE` — the ledger permanently loses the second (legitimately distinct)
   `route_realized` (or `plain_text_override`) row.

### Reproduction status

**Confirmed via static code reading** (exact line numbers and formulas verified above,
including tracing `_pending_state_path()` — confirmed to be one file per *session*
(`pending_route_<sid>.json`, `auto-route.py` line 1811), not per route-decision, meaning
overlapping in-flight pending states for the same session are also clobbered independent of
this collision). A live dynamic reproduction (spawning two hook invocations within the same
wall-clock second and observing an actual dropped `INSERT OR IGNORE`) was **not executed** —
this requires either mocking `time.time()` to return an identical value across two full
`auto-route.py` + `enforce-route.py` hook round-trips, or a tight timing race, which was out
of scope for the remaining audit window. **Confidence: high on the static mechanism (the
formulas are unambiguous and directly quoted above); unconfirmed on real-world trigger
frequency** — marking this an **unconfirmed-hypothesis-for-trigger-rate, confirmed-mechanism**
finding per the task brief's distinction.

### Expected vs actual

- **Expected**: `route_id`/`turn_id` uniquely identify a routing decision regardless of
  wall-clock timing, so `INSERT OR IGNORE` dedup never conflates two different decisions.
- **Actual**: the "turn" component is 1-second-resolution wall-clock time, not a counter; any
  two same-session, same-tool routing decisions issued within the same second collide.

### Root-cause hypothesis

`int(_now)` was likely chosen as a cheap, dependency-free "turn proxy" (comment: "clears when
next prompt arrives") without considering that `auto-route.py` could fire more than once per
second in bursts (e.g. rapid successive prompts in a scripted or high-throughput session, or
retried hook invocations). A true monotonic counter (e.g. an incrementing integer persisted
alongside the per-session pending-state file, or a sub-second/microsecond timestamp, or a
random nonce) would close this gap.

### Suggested acceptance test

Unit test: call the `route_id`-construction logic (or a minimal stand-in) twice with `time.time`
patched to return the same value, for the same `session_id`/`tool`, and assert the two
resulting `route_id`s (and downstream `event_id`s) differ — or, if the fix instead scopes
`event_type`/dedup differently, assert that both `record_event()` calls succeed (i.e. neither
is silently dropped) via checking `execution_events` row count after both.

### Impact flags

- Telemetry/cost corruption: **Yes** (if triggered) — a dropped `route_realized` row means the
  execution ledger's honored-vs-bypassed accounting (explicitly called out in
  `enforce-route.py`'s own comment as fixing a scenario where "97.7% of directives were
  bypassed looked identical... the product could not measure its own bypass rate") would
  undercount honored routes for the colliding decision, potentially misclassifying a
  correctly-honored route as bypassed in later reporting.
- False completion: No.
- Silent expensive routing: No.
- File damage: No.

---

## Minor note (not written up as a numbered finding — Low, message-text only)

`router.py` line ~3283's `BudgetExceededError` message for the daily/task-type cap reads
`"... exceeded (spent: $X today UTC). Resets at midnight UTC."`, but the underlying query
(`cost.py::_rejected_attempt_spend_today`, and the `usage`-table portion of
`get_daily_spend()`) both use `date(ts, 'unixepoch', 'localtime')` / `'localtime'` framing, not
UTC. This is a **user-facing message accuracy** issue only — the actual cap-check boundary is
local midnight, not UTC midnight, so a user in a non-UTC timezone reading this message would
be told the wrong reset time. No functional/accounting impact confirmed; not reproduced as a
standalone item given time constraints, but the code citation above is exact and can be
verified by inspection alone.

---

## Areas traced but not exhaustively audited this iteration (explicitly flagged as open, per methodology)

To be transparent about audit coverage: the following required-focus areas from the task
brief were examined only partially or not at all, and should not be read as "clean" —
only as "not yet disproven this iteration":

- **Cross-process budget-lock gap**: `_budget_proc_lock` is a `threading.Lock`, process-wide
  only. Whether the deployment topology (e.g. one MCP server process per Claude Code session
  via stdio, per `route_server.py` vs `server.py` inspected in a prior session) allows two
  *processes* to each pass a cap check independently was not re-verified this iteration.
  Flagged as an **open, unconfirmed hypothesis** carried over from prior work.
- **Classification & capability resolution**: not touched this iteration.
- **Restart/recovery, backward-compat/migration**: not touched this iteration.
- **Dead code / bypass paths**: only incidentally observed (e.g. the `elif _enforce_mode ==
  "hard"` branch at router.py ~3477, and the "smart" fallthrough branch below it, were read
  but not adversarially tested for a bypass of their own).
- **`_load_rows()` lacking `ORDER BY` in `execution_ledger.py`** (prior-session observation,
  lines 228-243): `_aggregate()`'s `route_realization[rid] = rs` last-write-wins semantics
  under unordered SQLite row iteration remains a plausible non-determinism source for
  `realized_savings_usd` — not re-investigated or reproduced this iteration.

None of these are claimed as findings; they are logged so the next iteration (or a
complementary auditor, e.g. the concurrently-running "Iter-2 RED-2 customer-reality audit")
does not need to rediscover the starting points.

---

## Explicit statement on audit completeness

Genuine adversarial effort was applied to the required focus areas this iteration and
produced **three substantiated findings** (two Confirmed via live reproduction with pasted
output — RED1-2-01, RED1-2-02 — and one Confirmed-mechanism/static — RED1-2-03), plus one
Low-severity message-accuracy note. This is **not** a "no defect found" iteration. Coverage
gaps are listed explicitly above rather than silently left unmentioned.
