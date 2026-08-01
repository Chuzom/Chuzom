# RED-1 — Architecture & Correctness Audit — Iteration 8 (final budgeted round)

Auditor: RED-1 (independent, adversarial). Commit: `48fb535`.
Scope per mandate: (1) atomic `settle()` across all three budget backends, (2)
`install_hooks.py` backup-before-overwrite, (3) full exit-path sweep of
`route_and_call` / `_dispatch_model_loop` including `_BG_TASKS`, (4) anything
else that miscounts spend, mis-routes, corrupts state, or crashes on a common
input. Independence maintained: RED-2's output was not read.

**Verdict: NOT CLEAN — 3 High, 2 core-Medium.**

---

## Summary table

| ID | Severity | Title |
|---|---|---|
| RED1-8-01 | High | Rejected-but-billed attempts never reach the envelope/quota ledger — real spend can exceed the enforced cap undetected |
| RED1-8-02 | High | Failed hook/rules backup silently destroys hand-edited files with a status message indistinguishable from success |
| RED1-8-03 | Medium | Single fixed `.bak` slot is clobbered by a second drift-overwrite, permanently losing the first hand-edit |
| RED1-8-04 | High | Postgres budget backend has zero T2-L2 forecast-tier support — the enterprise-default-on burn-rate guard is silently inert |
| RED1-8-05 | Medium | `drain_bg_tasks()` is never called in production — fire-and-forget tasks (`store_receipt`, OKF writes) are abandoned on shutdown |

---

## RED1-8-01 — Rejected-but-billed attempts never reach the envelope/quota ledger

**Severity:** High
**Files:** `src/chuzom/router.py:1739` (init), `:2243` and `:2302` (accumulation),
`:4037`, `:4040-4042` (settlement, drops the accumulator)

**Failure scenario:** `_dispatch_model_loop` maintains a local
`_failed_attempt_cost` accumulator that correctly captures the real,
already-billed cost of any paid-provider attempt that gets rejected by a
contract gate (line 2243) or the quality-escalation heuristic (line 2302) —
these are attempts where a real API call executed and was charged, but the
router decided to retry with a different model. When the chain eventually
returns a successful `response`, the success-path tail only settles
`response.cost_usd` — the single final attempt's cost — into both
`commit_envelope(...)` (budget-envelope rollup, `quota_envelope_routing.py`)
and `record_consumption(...)` (per-identity/team quota tracker,
`quota_routing.py`). `_failed_attempt_cost` is structurally trapped inside
`_dispatch_model_loop`'s local scope: `LLMResponse` is
`@dataclass(frozen=True)` (`types.py:457-503`) with no aggregate-cost field,
and `_enrich_response()` only overlays a small set of fields
(`confidence`, `classification_method`, `complexity`, `task_type_str`,
`chain_attempts`) — it never carries the accumulator out.

Net effect: every turn that retries past one or more billable
gate/quality rejections under-reports its true cost to **both** independent
enforcement mechanisms (P0-3 budget envelope and F4/P0-2 quota tracker).
Repeated occurrences let cumulative real spend exceed a configured cap with
no error, no alert, and no signal — the two systems whose entire purpose is
"refuse the next turn once the cap is hit" are both silently blind to a
fraction of actual spend. This is not a rare edge case: contract-gate
rejection and quality-escalation retry are both intentional, designed
routing behaviors.

**CONFIRMED** — repro at
`/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_envelope_underbill.py`,
using the real `chuzom.quota_envelope_routing.commit_envelope` and real
`chuzom.budget_backend.SqliteBudgetBackend` (no mocks). Output:
`true_total_spend=$0.0800`, `final_response.cost_usd=$0.0300`,
`_failed_attempt_cost=$0.0500` (dropped), `backend.consumed(key) AFTER
settle=$0.0300`, `undercount=$0.0500`. Also note: the CF-1 telemetry ledger
(`_actual = _final_cost + _failed_attempt_cost`, router.py ~2412) and the
`audit_routing_turn(...)` call at the same success-path tail (router.py
~4025) both use the same truncated `response.cost_usd`-only value for the
audit log, so even the audit trail does not reflect true spend — only the
telemetry-only CF-1 ledger does.

**Suggested fix:** thread `_failed_attempt_cost` out of
`_dispatch_model_loop` (extra return value, `nonlocal`/out-param, or a new
non-breaking field on `LLMResponse`), then pass
`response.cost_usd + failed_attempt_cost` as `actual_cost_usd` to both
`commit_envelope(...)` and `record_consumption(...)` at the success-path
tail.

---

## RED1-8-02 — Failed hook/rules backup silently destroys hand-edited files

**Severity:** High
**File:** `src/chuzom/install_hooks.py:165-174` (`_backup_before_overwrite`),
`:215-227` (`check_and_update_hooks`), `:261-268` (`check_and_update_rules`)

**Failure scenario:** `_backup_before_overwrite(dst)` attempts
`shutil.copy2(dst, dst.with_suffix(dst.suffix + ".bak"))` and returns `None`
on any `OSError` (silently swallowed — no log, no re-raise). Both
`check_and_update_hooks()` and `check_and_update_rules()` call this function
and then **unconditionally** proceed to `shutil.copy2(src, dst)` regardless
of whether the backup succeeded. When the backup fails (a realistic trigger:
disk-full, a transient permission hiccup, or any other `OSError` on the
managed-hooks directory at the exact moment of a version-drift-triggered
auto-update — which the function's own docstring says runs automatically on
every MCP server startup), the user's hand-edited hook/rules content is
permanently and irrecoverably destroyed with **zero** recovery path. The
resulting status message (`"Updated {dst_name} v{dst_v} → v{src_v}"`, backup
clause simply omitted) is textually indistinguishable from a normal,
successfully-backed-up update — no "Failed"/"fail" language, no distinct
warning.

**CONFIRMED** — repro at
`/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_hook_backup_silent_fail.py`,
using the real `chuzom.install_hooks._backup_before_overwrite` (chmod'd the
destination directory read-only to force a realistic `OSError`, then
replayed the exact overwrite branch from `check_and_update_hooks()`).
Confirmed output: `.bak exists (recoverable?): False`,
`status message shown to user: 'Updated chuzom-hook.py v1 -> v2'` (no
failure indication), user's original content gone from `dst` with no trace
anywhere on disk.

**Suggested fix:** make backup failure a hard stop for the overwrite (skip
`shutil.copy2(src, dst)` and report a distinct
`"Failed to back up {dst_name}, update skipped for safety"` message), or at
minimum emit a visibly different warning
(`"backup FAILED — previous content NOT recoverable"`) instead of silently
omitting the `"(previous saved to ...)"` clause.

---

## RED1-8-03 — Single fixed `.bak` slot clobbered by a second drift-overwrite

**Severity:** Medium (core)
**File:** `src/chuzom/install_hooks.py:165-174`, `:215-227`

**Failure scenario:** `_backup_before_overwrite` always targets the same
fixed path (`dst.with_suffix(dst.suffix + ".bak")`, no timestamp/versioning).
If a user hand-edits a managed file twice across two separate startup
events without ever consulting the intervening `.bak`, the second
drift-triggered overwrite backs up edit #2 into the *same* `.bak` path,
clobbering edit #1 — which was only ever preserved in that one slot. After
the second overwrite, edit #1 (the user's true original customization)
exists nowhere on disk: not in `dst` (replaced by bundled content), not in
`.bak` (overwritten by edit #2), not anywhere else. Narrower and lower
severity than RED1-8-02: it requires two separate hand-edits across two
restart boundaries with no `.bak` consultation in between, and the
*immediately preceding* edit remains recoverable — only history older than
the last edit is lost. Single-slot backup naming (no timestamp/versioning)
is also a common tradeoff pattern in other tools, which tempers the
severity further.

**CONFIRMED** — repro at
`/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_hook_bak_clobber.py`,
using the real `_backup_before_overwrite` and `_files_differ` via an
`overwrite_cycle()` helper that mirrors `check_and_update_hooks()`'s branch
logic. Confirmed output: `.bak` content after the second overwrite equals
edit #2, not edit #1 — the true original is unrecoverable.

**Suggested fix:** timestamp or version-suffix the backup filename (e.g.
`<name>.<timestamp>.bak`, or retain the last N backups) instead of a single
fixed `.bak` slot.

---

## RED1-8-04 — Postgres budget backend has zero T2-L2 forecast-tier support

**Severity:** High
**Files:** `src/chuzom/budget_backend_postgres.py` (whole file — no
`budget_spend_events`-equivalent table in `_SCHEMA`, no
`_check_forecast_inside_tx` equivalent; `try_reserve`/`_try_reserve_sync`,
lines 257-298, perform only the hard-cap `UPDATE ... WHERE consumed_usd +
pending_usd + %s <= cap_usd` check), cross-referenced against
`src/chuzom/budget_backend.py:153-166` (`_forecast_mode()`) and `:773-812+`
(`get_budget_backend()`)

**Failure scenario:** the T2-L2 forecast tier is a burn-rate-based
*additive* refusal layer, separate from and stricter than the hard cap:
`_forecast_mode()` defaults to `"strict"` for enterprise-profile
deployments **with no required opt-in** (`CHUZOM_BUDGET_FORECAST_MODE`
unset → `is_enterprise()` ⇒ `"strict"`), and in strict mode
`ForecastedBudgetBreach` is raised — refusing a turn — when the projected
burn rate would breach the cap within a horizon, *even if the immediate
hard-cap check would still pass*. This tier is entirely absent from
`PostgresBudgetBackend`: there is no spend-event log, no burn-rate
projection, and `try_reserve` performs only the hard-cap arithmetic. An
operator on the enterprise profile who selects
`CHUZOM_BUDGET_BACKEND=postgres` (the backend intended for exactly the
multi-instance/scale deployments enterprises need) gets **zero** forecast
enforcement, silently: `get_budget_backend()` selects the backend purely by
env var with no cross-check against `_forecast_mode()`'s
enterprise-default-strict setting, so nothing warns that the "strict
forecast" protection the operator believes is on (per the enterprise
default) is completely inert on this backend. This is distinct from and
more severe than the *already-documented* "EXPERIMENTAL, not yet
CI-tested for multi-instance atomicity" caveat in
`quota_envelope_routing.py`'s module docstring — that caveat is about an
unproven-under-load claim for a feature that does exist; this is a complete
structural absence of a named, enterprise-default-on safety tier. Bounded
impact: the hard cap itself is confirmed present and structurally correct
on Postgres (parity-matched with the already-verified SQLite `settle()`
implementation — see below), so this does not by itself allow spend beyond
the hard cap; it silently removes the pre-emptive early-throttle that
"strict forecast" mode is supposed to provide.

**CONFIRMED** via direct code reading — `grep -n
"forecast\|spend_events\|_check_forecast" budget_backend_postgres.py`
returns zero matches; full read of `_try_reserve_sync` (257-298),
`_settle_sync` (383-403), `_commit_sync`, `_release_sync` confirms these are
otherwise structurally correct and parity-matched with SQLite's
already-audited implementation (same parent-chain-walk-then-uniform-UPDATE
pattern via `_chain_keys` + `SELECT ... FOR UPDATE`, same floor-at-zero
pending via `GREATEST(0.0, ...)`, same no-cap-recheck-on-`actual>est`
design) — i.e. this is a scoped, isolated gap (missing forecast tier only),
not a general Postgres-backend correctness defect.

**Suggested fix:** either implement an equivalent forecast tier for
`PostgresBudgetBackend` (a `budget_spend_events`-equivalent table plus a
burn-rate check ported from `budget_backend.py`), or have
`get_budget_backend()` / `_forecast_mode()` detect the
postgres+strict-forecast combination at backend-selection time and emit an
explicit warning/alert (or refuse to silently degrade) so operators are not
unknowingly missing an enterprise-default safety tier.

---

## RED1-8-05 — `drain_bg_tasks()` is never called in production

**Severity:** Medium (core)
**Files:** `src/chuzom/router.py:95-121` (`_BG_TASKS`, `_spawn_bg`,
`drain_bg_tasks`), `:2338-2341` (`store_receipt` fire-and-forget call site),
`src/chuzom/server.py:409-425` (`main()`, MCP server entrypoint)

**Failure scenario:** the `_BG_TASKS` tracking set and `_spawn_bg()` helper
exist specifically (per their own comment, router.py:95-100) to fix two
failure modes of bare `asyncio.create_task(...)`: GC of the task mid-flight,
and inability to drain pending work at shutdown ("a pending DB write is
silently dropped when the loop closes — leaking its aiosqlite connection").
The strong-ref/GC half of that fix is real (`_BG_TASKS.add(task)` +
`add_done_callback`). The shutdown-drain half is not wired to anything in
production: `drain_bg_tasks()` is defined at router.py:112 but the *only*
call site in the entire repository is
`tests/test_red1_3_reservation_leaks.py:86` — a test teardown. The actual
MCP server entrypoint, `server.py:main()`, calls `mcp.run()` directly with
no lifespan hook, no `atexit` registration, and no `SIGTERM`/`SIGINT`
handler that calls `drain_bg_tasks()`. So every real fire-and-forget task
spawned via `_spawn_bg` — most notably `store_receipt(_receipt)` at
router.py:2341, whose own adjacent comment says "Tracked so shutdown can
drain it" — is, in fact, never drained on real process shutdown: when the
MCP stdio server process exits (normal exit or signal), any still-pending
`store_receipt` write (or the OKF enrichment writes at ~3777/~4060/~4065)
is simply abandoned when the event loop tears down — the exact "silently
dropped... leaking its aiosqlite connection" outcome the tracking mechanism
was built to prevent, just with the second half of the fix never connected.
Impact is bounded to receipts/analytics/OKF-enrichment data (the savings
dashboard / session-end summary bridge, and per-turn audit receipts) —
not spend enforcement or security — but it is a real, silent, unsignaled
data-loss path on every process shutdown with in-flight background writes.

**CONFIRMED** via direct code inspection — `grep -rn "drain_bg_tasks" .
--include="*.py"` across the full repository returns exactly two lines: the
definition (`router.py:112`) and the one test-teardown call
(`tests/test_red1_3_reservation_leaks.py:86`); `server.py:409-425`
(`main()`) read in full, confirming `mcp.run()` is called with no shutdown
hook of any kind. No repro script was needed — this is a direct,
verifiable static fact (absence of any production call site), not a
runtime behavior requiring simulation.

**Suggested fix:** register `drain_bg_tasks()` in `server.py:main()` — via
an `atexit` handler wrapping `asyncio.run(drain_bg_tasks())`, a
`SIGTERM`/`SIGINT` handler, or (if FastMCP exposes one) a lifespan/shutdown
hook — so the tracking mechanism's own stated purpose is actually realized
in production, not just in tests.

---

## What else was checked (no defect found)

- **Priority 1 — `settle()` across all three backends.** SQLite
  (`budget_backend.py:591-616`, `_settle_sync`) and Postgres
  (`budget_backend_postgres.py:383-403`) both re-confirmed structurally
  correct and parity-matched this session: single-lock/transaction
  parent-chain walk, `consumed += actual`, `pending = max(0, pending -
  est)`, no cap re-check on `actual > est` (by design — the cap was already
  checked at reservation time), soft-cap flip fires after commit via
  `_maybe_flip_soft_state`. `BudgetEnvelopeManager` (in-process,
  `budget_envelope.py`) was confirmed correct in a prior iteration and is
  unchanged. The `getattr(b, 'settle', None)` dispatch in
  `commit_envelope()` (`quota_envelope_routing.py:111-116`) correctly
  prefers the atomic path and falls back to the legacy
  `release()+commit(settle_pending=False)` two-step for backends that
  predate `settle()`. Tried and found correct: est>actual, est<actual (via
  the repro's numbers), actual=0/est=0 boundary math (both floor at zero
  via `max(0.0, ...)` / `GREATEST(0.0, ...)`), and the shared-key parent
  chain propagation (BFS walk applies the same delta to every ancestor
  uniformly).
- **Priority 3 — full exit-path sweep of `route_and_call` /
  `_dispatch_model_loop`.** Re-read this session (not relied on memory):
  the three internal success/exhaustion returns inside
  `_dispatch_model_loop` (primary-chain success at router.py:2629-2630,
  emergency-BUDGET success at :2781-2782, chain-exhaustion tail at
  :2813-2814) each release `_pending_spend` under `_budget_lock()` exactly
  once, matching the RED1-5-02 comment's claim (now independently
  verified, not just cited). Combined with the previously-confirmed
  deadline-pre-dispatch early exit, `CancelledError` handler,
  `TimeoutError` handler, generic `except Exception` handler
  (RED1-4-02-tagged, envelope-only release), and the success-path tail
  (RED1-5-02-tagged) in `route_and_call` itself — every terminal exit path
  releases/settles `_pending_spend` and/or the envelope exactly once. No
  new leak or double-release defect found in this sweep; the three
  prior-iteration audit-ID comments (`RED1-4-01`, `RED1-4-02`, `RED1-5-02`)
  documenting the specific bugs these paths were previously fixed for all
  remain accurate.
- **Frozen `LLMResponse` dataclass.** Confirmed immutable
  (`@dataclass(frozen=True)`, types.py:457-503) with the full field list
  enumerated; its immutability is in fact the root structural cause of
  RED1-8-01 (no aggregate-cost field to carry `_failed_attempt_cost` out),
  not a defect in itself.
- **Cap enforcement / cap-downgrade (TQ-007) / semantic-cache accounting**
  on the common path — spot-checked, no new defect (semantic-cache store
  at router.py:2621-2627 is fire-and-forget with its own try/except,
  consistent with prior audit rounds).

## Break-attempts tried that did NOT reproduce a defect

- Forcing est>actual, est<actual, actual=0, est=0 through `settle()` on
  both SQLite and Postgres code paths (read-level verification; math is
  symmetric and correct in both).
- Re-tracing every `_pending_spend`-touching line across `router.py` via
  `grep -n "_pending_spend"` (18 call sites) to confirm no path double-
  releases or under-releases.
- Attempting to find a second, independent forecast/cap gap in the
  in-process `BudgetEnvelopeManager` — none found; it has no forecast tier
  at all (by design, single-instance in-process use case), consistent
  behavior, not a gap.

---

## Compact summary (for orchestrator)

**3 High, 2 Medium — NOT CLEAN.**

- RED1-8-01 (High): rejected-but-billed attempt costs never reach the
  budget envelope or quota tracker — real spend can exceed the enforced cap
  undetected.
- RED1-8-02 (High): a failed hook/rules backup lets the destructive
  overwrite proceed anyway, with a success message indistinguishable from a
  normal update.
- RED1-8-03 (Medium): the single fixed `.bak` slot is clobbered by a second
  drift-overwrite, losing the first hand-edit permanently.
- RED1-8-04 (High): the Postgres budget backend has zero T2-L2 forecast-tier
  support, silently inert exactly where the enterprise-default-strict
  forecast mode is most likely to be relied on.
- RED1-8-05 (Medium): `drain_bg_tasks()` has no production call site —
  fire-and-forget receipt/analytics writes are abandoned on real process
  shutdown.
