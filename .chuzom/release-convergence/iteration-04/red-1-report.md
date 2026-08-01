# RED-1 Architecture & Contract Auditor — Iteration 4

**Auditor:** RED-1 (fresh-context, independent, no anchoring on prior audits)
**Repo:** `/Users/yaliandrona/Projects/Chuzom`
**Branch/HEAD at audit time:** `fix/v1.0.1-audit-mitigation` @ `c025f68`
**Mode:** READ-ONLY (no edits, no commits)
**Prime focus (per task brief):** `router.py` `route_and_call`'s budget-reservation lifecycle — the new `_release_reservation_if_held()` guard-flagged helper, its 4 call sites, the ~10 pre-existing per-site raw releases, the `_env_key` / distributed-envelope interaction, and concurrency of `_pending_spend` under `_budget_lock()`.

---

## Summary

| Severity | Count |
|---|---|
| HIGH | 1 |
| MEDIUM | 1 |
| LOW | 1 |
| INFO (design inconsistency, no independent exploit) | 1 |

**Top 3, one line each:**

1. **RED1-4-01 (HIGH)** — `_pending_spend` is released **twice** on every successful `route_and_call` turn — once inside `_dispatch_model_loop`'s success path (`router.py:2629-2630`) and again in `route_and_call` right after the dispatch coroutine returns (`router.py:3995-3996`) — neither site uses the guard-flagged helper. Reproduced live: under concurrency, a completing call erases another still-in-flight call's reservation from the shared counter, undercounting live spend and defeating the TOCTOU protection the reservation exists for.
2. **RED1-4-02 (MEDIUM)** — When the model chain is exhausted and `_dispatch_model_loop` raises its tail `RuntimeError`/`CostBudgetExceeded`/`PermissionDenied`, the distributed budget **envelope** reservation (`_env_key`, held via `reserve_envelope()`) is never released or committed — only `_pending_spend` is. Reproduced live with `CHUZOM_ENVELOPE_MODE=strict`: `reserve_envelope()` fires, `release_envelope()`/`commit_envelope()` never do. Scoped to strict-envelope / enterprise-profile deployments (off-mode, the default, never reserves a real key, so nothing leaks there).
3. **RED1-4-03 (LOW)** — `"attempt_failed"` is a defined, billable execution-ledger event type (`execution_ledger.py:42`) that **no production code path ever emits** — every `_emit_ledger_attempt()` call site in `router.py` passes only `"attempt_rejected"` or `"attempt_completed"`. Provider-error attempts (rate limits, timeouts, API failures) are silently invisible to the execution ledger; only unit tests of `execution_ledger.py` itself exercise the event type.

**Areas traced and confirmed clean this session** (see "Verified Clean" below): the guarded helper's 3 in-scope early-exit call sites (empty-chain, cache-hit, envelope-reservation-failure) release exactly once with no double-decrement; the TQ-007 hard-block raise releases correctly via the helper; `_dispatch_model_loop`'s all-models-failed tail correctly releases `_pending_spend` (but not the envelope — see RED1-4-02) before every one of its four exits; `correlation_id` is always a non-empty `uuid4().hex[:8]` in practice, so the pervasive `correlation_id or ""` fallbacks are dead-but-harmless, not a real emptiness bug; `release_envelope(None, ...)` / `commit_envelope(None, ...)` are safe explicit no-ops, so the unconditional (non-`None`-guarded) raw-release call sites are not a null-handling bug.

---

## RED1-4-01 — `_pending_spend` double-released on every successful turn (two unconditional raw releases, neither guarded)

**Severity:** HIGH
**Category:** Budget/concurrency correctness — reservation accounting
**Affected promise:** The in-flight reservation (`_pending_spend`) exists specifically to prevent TOCTOU budget-cap overruns from concurrent callers (see the design comment at `router.py:3352-3361`: "each early exit... leaked, biasing every later cap check"). The success path is supposed to release the reservation **exactly once**.
**Violated invariant:** For any single `route_and_call` reservation of size `R`, exactly one release of size `R` must occur across the call's full lifetime, regardless of which exit path is taken.

### Affected surface / exact locations
- `src/chuzom/router.py:2629-2630`, inside `_dispatch_model_loop`'s success branch, immediately before it returns `_enrich_response(...)`:
  ```python
  async with _budget_lock():
      _pending_spend = max(0.0, _pending_spend - _reservation)
  return _enrich_response(
      response, classification_data, effective_complexity,
      task_type, chain_attempts,
  )
  ```
- `src/chuzom/router.py:3995-3996`, in `route_and_call`, unconditionally executed the moment `await _dispatch_coro` / `asyncio.wait_for(_dispatch_coro, ...)` (lines 3881-3887) returns *without raising* — i.e., it runs on every success:
  ```python
  async with _budget_lock():
      _pending_spend = max(0.0, _pending_spend - _reservation)
  _success_detail = {"correlation_id": correlation_id}
  ...
  ```

### Control-flow trace
1. `route_and_call` reserves `_reservation` into `_pending_spend` under `_budget_lock()` (confirmed earlier in the function, `router.py:3345-3346`).
2. `route_and_call` builds `_dispatch_coro = _dispatch_model_loop(...)` (not yet awaited) and awaits it inside a `try` that only catches `asyncio.CancelledError` and `asyncio.TimeoutError` (`router.py:3881-3899`, `3933-3994`).
3. On success, `_dispatch_model_loop` itself already released the same `_reservation` amount at `router.py:2629-2630` before returning.
4. Because neither of the two exception handlers fired, execution falls through past the `try/except` block to `router.py:3995-3996`, which unconditionally releases `_reservation` **a second time** — same variable, same amount, same shared module-global `_pending_spend`.
5. Neither release site checks or sets `_reservation_released` (the guard flag introduced specifically to make releases idempotent, `router.py:3363,3369-3372`) — that flag is scoped to `route_and_call`'s closure and is only touched by `_release_reservation_if_held()`, which is never called on this path (confirmed: the helper has exactly 4 call sites in the entire file — `router.py:3375` [inside the helper's own body], `3530`, `3543`, `3762` — none is on the success path).

### Reproduction (re-verified this session; script re-read in full and its logic independently traced against the two exact line numbers above)
`/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_double_release.py` — fires two concurrent `route_and_call` turns (A: short prompt/small reservation, B: long prompt/larger reservation, B's provider call gated on an `asyncio.Event` so its reservation stays outstanding while A completes), and samples `router._pending_spend` immediately after A finishes.

Pasted output:
```
reservation(A, short prompt)  = 0.005
reservation(B, long prompt)   = 0.0075
_pending_spend after B reserved, before A starts: 0.0075
_pending_spend immediately after A completes: 0.0025000000000000005
Expected (B still in flight, A fully settled): 0.0075
Actual - Expected = -0.004999999999999999  (should be 0.0)
_pending_spend after both A and B fully complete: 0.0
Expected: 0.0 (both settled)

BUG CONFIRMED (double-release of _pending_spend on success path): True
  While B (reservation=0.0075) was still in flight, A's completion (reservation=0.005) wrongly drove shared _pending_spend down to 0.0025000000000000005 instead of 0.0075 -- B's pending spend was silently erased by 0.005000, which equals A's reservation (0.005).
```
The erasure magnitude (`0.005`) equals A's own reservation exactly — i.e., A's completion event decremented the shared counter by `2 × A's reservation` total (once in `_dispatch_model_loop`, once in `route_and_call`), which is only invisible in a single-caller test because the counter floors at 0.0 (`max(0.0, ...)`) and returns to 0 once all calls finish — it only manifests as wrong intermediate values while calls overlap, exactly the TOCTOU window `_pending_spend` exists to protect.

### Expected vs actual
- **Expected:** each call's `_reservation` is subtracted from `_pending_spend` exactly once.
- **Actual:** on every successful call, `_reservation` is subtracted twice — the shared counter under-reports true in-flight spend by the reservation size of every successful call, for the (short) window between that call's dispatch-loop return and the caller's next cap check.

### Root cause
The guard-flagged `_release_reservation_if_held()` helper was added (per its own design comment at 3352-3361) specifically to fix leaks on **early-exit** paths that ran before `_dispatch_model_loop` existed as the sole releaser. The refactor did not touch the **success** path, which still has two independent, unguarded raw releases: one inside `_dispatch_model_loop` (added under the "P1-7" effort, per the comment at `router.py:3348-3350`: "the in-process token-pressure reservation moved into the dispatch loop... released symmetrically per attempt") and one left over in `route_and_call` itself (`3995-3996`) from before that move. Nothing currently detects or prevents this: the guard flag exists but is simply never consulted by either site.

### Confidence
**High** — reproduced live with exact, predicted-and-matched numeric evidence; both release sites read directly from source with line numbers; root cause (two independent unguarded call sites, no shared idempotency mechanism) is unambiguous from the code.

### Suggested acceptance test
A regression test structured like `repro_double_release.py`: run two overlapping `route_and_call()` calls with distinguishable reservation sizes; after the first completes while the second is still in flight, assert `router._pending_spend` equals the still-in-flight call's reservation (not less). This is a genuinely new test — the existing `tests/test_red1_3_reservation_leaks.py` and `tests/test_tq007_daily_cap_downgrade.py` only exercise early-exit paths and single-call scenarios, and would not catch this (a lone successful call trivially returns to 0.0 regardless of single vs. double release).

### Suggested fix direction (not applied — read-only audit)
Route the success path through `_release_reservation_if_held()` (which would also naturally cover committing/releasing the envelope symmetrically) instead of two independent raw `async with _budget_lock(): _pending_spend = max(0.0, _pending_spend - _reservation)` blocks, OR remove one of the two sites and make the other the single source of truth. Since `_dispatch_model_loop` is a separate function/frame and cannot call `route_and_call`'s closure-scoped helper directly, the cleanest fix is likely to drop the release at `router.py:2629-2630` (or `3995-3996`) and rely on the other.

### Impact flags
`[budget-integrity]` `[concurrency]` `[TOCTOU]` `[reproduced]`

---

## RED1-4-02 — Distributed budget envelope reservation leaks on the all-models-failed exit (strict/enterprise envelope mode only)

**Severity:** MEDIUM (HIGH in strict/enterprise-envelope deployments specifically; not exploitable at all in the default off-mode, since no real key is ever reserved there)
**Category:** Budget/concurrency correctness — cross-process distributed reservation accounting
**Affected promise:** P0-3's stated lifecycle contract (`quota_envelope_routing.py:21-25`): "reserve the estimate before dispatch; on success `release(est)` then `commit(actual)`; on failure `release(est)`... so `pending` stays clean even when the estimate and the actual cost differ."
**Violated invariant:** Every `reserve_envelope()` call that returns a non-`None` key must be matched by exactly one `release_envelope()` or `commit_envelope()` call for that key, on every exit path.

### Affected surface / exact locations
- `src/chuzom/router.py:3742` — `_env_mode, _env_ok, _env_key = await reserve_envelope(identity, _reservation)`. Per `quota_envelope_routing.py:70-93`, `_env_key` is non-`None` precisely when: `CHUZOM_ENVELOPE_MODE=strict` (or enterprise profile with mode unset), `identity.user_id` is truthy, and the backend's `try_reserve()` call succeeds without raising.
- `src/chuzom/router.py:2813-2816` — `_dispatch_model_loop`'s tail block releases only `_pending_spend`, unconditionally, before all four of its possible exits (the `CostBudgetExceeded` raise at ~2818-2833, the `PermissionDenied` raise at ~2835-2846, the exhaustion-floor `return` at ~2854-2884, and the generic `raise RuntimeError(f"All models failed for ...")` at 2886-2889). It has **no reference to `_env_key`** — it is a separately-defined function, not a nested closure of `route_and_call`, so it cannot see or release the envelope reservation created in the caller's frame.
- `src/chuzom/router.py:3881-3899` (`except asyncio.CancelledError`) and `3933-3937` (`except asyncio.TimeoutError`) are the **only** two exception handlers wrapping `await _dispatch_coro` in `route_and_call`, and both *do* call `release_envelope(_env_key, _reservation)` (lines 3931, 3937). Neither of these handlers matches `CostBudgetExceeded`, `PermissionDenied`, or a bare `RuntimeError` — those exception types propagate straight out of `route_and_call` uncaught (confirmed: no `except Exception:` and no `finally:` exists on that `try` block; `router.py:4020-4028`, the code that runs after the try/except, is only reached on the success path since it is sequential — not inside a `finally`).
- Full grep confirmation of every `release_envelope`/`commit_envelope` call site in `router.py`: lines `3375` (inside `_release_reservation_if_held`, guarded by `if _env_key is not None`), `3842` (pre-dispatch deadline recheck), `3931`, `3937` (the two exception handlers above), and `4017` (`commit_envelope`, success path only). **None of these five sites is reachable when `_dispatch_model_loop` raises its tail exceptions.**

### Control-flow trace
1. Caller with `identity.user_id` set, `CHUZOM_ENVELOPE_MODE=strict`, and a registered envelope in the backend's rollup chain calls `route_and_call`.
2. `reserve_envelope()` succeeds and returns a real key; `_env_key` is set (line 3742).
3. Chain building / `_build_and_filter_chain` returns a non-empty chain, so none of the 3 pre-dispatch `_release_reservation_if_held()` call sites fire.
4. `_dispatch_model_loop` is invoked; every candidate model in the chain fails (provider errors, RBAC/policy denial, or per-task cost-cap skip).
5. `_dispatch_model_loop`'s tail block releases `_pending_spend` (2813-2816) then raises one of its three terminal exceptions.
6. That exception is not `asyncio.CancelledError` or `asyncio.TimeoutError`, so it is not caught by either handler in `route_and_call`; it propagates directly out of `route_and_call` to the caller.
7. The envelope reservation made in step 2 is never released and never committed. The backend (`BudgetBackend.try_reserve`) continues to hold it indefinitely — until process restart or any backend-side TTL cleanup (not verified to exist; the module's own docstring only claims `try_reserve`/`commit`/`release` semantics, no expiry).

### Reproduction (executed this session)
Script: `/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_envelope_leak_allfailed.py` — mocks `reserve_envelope` to return a **real, non-`None`** key (`"tenant:acme/user:42"`, unlike the existing test suite and the RED1-4-01 repro, both of which mock `reserve_envelope` as `(None, True, None)` and therefore cannot observe this leak), forces `providers.call_llm` to raise on every attempt so the chain exhausts into the generic `RuntimeError`, and asserts on the `release_envelope`/`commit_envelope` mocks.

Command:
```
unset CHUZOM_ENFORCE
export CHUZOM_DB_PATH=$(mktemp -u /tmp/chuzom_test_XXXX.db)
export CHUZOM_EXECUTION_LEDGER_DB=$(mktemp -u /tmp/chuzom_ledger_test_XXXX.db)
python repro_envelope_leak_allfailed.py
```

Pasted output:
```
route_and_call raised: RuntimeError: All models failed for code/balanced. Last error: simulated provider outage.
Chain failures:
  1. openai/gpt-4o: RuntimeError: simulated provider outage
 Run `llm_health()` to see circuit breaker status, or `chuzom doctor` to diagnose all issues.
reserve_envelope call args: call(TurnIdentity(user_id='yaliandrona', user_email='yaliandrona@local', org_id='local', agent_id=None, tenant_id='local', team_id=None, permissions=frozenset(), allowed_providers=None, allowed_models=None), 0.0050025)
release_envelope called: False  (call_count=0)
commit_envelope called:  False  (call_count=0)
_pending_spend after failure: 0.0  (expected 0.0 -- that part IS released)

BUG CONFIRMED (envelope reservation leaked on all-models-failed exit): True
  reserve_envelope() was called and returned key='tenant:acme/user:42', but neither release_envelope() nor commit_envelope() was ever called for it. The backend's try_reserve() hold for this key is now permanently stuck (until process restart / backend TTL), biasing every subsequent try_reserve() check against this identity upward by the leaked estimate.
```
This confirms `_pending_spend` (the in-process counter) *is* correctly released on this path — consistent with the code trace above — while the distributed envelope is not. The same mechanism applies identically to the `CostBudgetExceeded` and `PermissionDenied` tail exceptions (not independently re-run — they share the exact same uncaught-exception code path through the identical `try`/`except CancelledError`/`except TimeoutError` block; there is no code-level distinction between the three exception types that would cause different envelope handling).

### Expected vs actual
- **Expected (per the module's own documented lifecycle contract):** every `reserve_envelope()` that returns `ok=True` and a real key is matched by exactly one `release()`/`commit()` before the turn ends, on every exit path including "all models failed."
- **Actual:** on the all-models-failed exit specifically (and only that exit — cancellation and timeout are correctly handled), the envelope reservation is silently abandoned.

### Root cause
`_dispatch_model_loop` was extracted as a standalone function (not a nested closure of `route_and_call`) as part of the "P1-7" refactor referenced in its own comments, so it structurally cannot see or release `_env_key` (a variable local to `route_and_call`'s frame). Its own raw release at 2813-2816 only handles the piece of state it *can* see (`_pending_spend`, a module global). The envelope-release responsibility for this exception class was never assigned to anything in `route_and_call` either — only the two `asyncio`-specific handlers release the envelope, and the design comment introducing the guarded helper (3352-3361) explicitly enumerates the early-exit paths it was built to fix but does not mention the "all models failed" tail exception at all, suggesting this gap was not in scope for that fix.

### Confidence
**High** for the code-level mechanism (exhaustively grep-confirmed: exactly 5 `release_envelope`/`commit_envelope` call sites in the whole file, none reachable from this exit) and for the live reproduction. **Medium** for real-world blast radius, since it requires `CHUZOM_ENVELOPE_MODE=strict` or enterprise profile (the module's own docstring: "off — no-op (developer-profile default)") — i.e., it is a real defect but scoped to a specific, currently-experimental deployment configuration (the module also self-flags: "EXPERIMENTAL for multi-instance... Postgres backend's multi-instance coordination is not yet covered by a real-Postgres CI test").

### Suggested acceptance test
A test mirroring `repro_envelope_leak_allfailed.py`: mock `reserve_envelope` to return a real key, force chain exhaustion, and assert `release_envelope` or `commit_envelope` was called with that key before/while the exception propagates. Should be added alongside `tests/test_red1_3_reservation_leaks.py`, whose existing tests structurally cannot catch this (they mock `reserve_envelope` as `(None, True, "k")` for one test but only exercise the empty-chain and cache-hit paths, not chain exhaustion).

### Suggested fix direction (not applied — read-only audit)
Either wrap the `await _dispatch_coro` call in a broader `except Exception:` that releases the envelope (and re-raises) for exception types beyond `CancelledError`/`TimeoutError`, or have `_dispatch_model_loop` accept and release an envelope key/callback so its own tail block can settle it symmetrically with `_pending_spend`.

### Impact flags
`[budget-integrity]` `[distributed-state]` `[enterprise-scoped]` `[reproduced]`

---

## RED1-4-03 — `"attempt_failed"` execution-ledger event type is defined but never emitted by any production code path

**Severity:** LOW
**Category:** Observability / dead code / silent accounting gap
**Affected promise:** INV-COST-001 as described in `_emit_ledger_attempt`'s own docstring (`router.py:1622-1627`): "Records EVERY billable attempt — accepted, gate-rejected, quality-rejected — exactly once, so route/session totals derived by the aggregation layer include rejected/escalated attempt cost."
**Violated invariant:** Every billable attempt type declared in `execution_ledger.py`'s `_BILLABLE_EVENTS`/event-type set should have at least one production writer.

### Affected surface
- `src/chuzom/execution_ledger.py:42` — `"attempt_failed",  # provider error; cost only if usage is known` is declared as a first-class billable event type, and appears again in the billable-set literal at line 59 (`{"attempt_completed", "attempt_rejected", "attempt_failed"}`).
- `src/chuzom/router.py` — the only module that calls `_emit_ledger_attempt()` (the sole production wrapper around `execution_ledger.record_event` for attempt-level events, defined at `router.py:1610-1649`) — has exactly 4 call sites, at lines 2244-2249, 2303-2308, 2321-2325, and 2758-2762. All 4 pass `event_type="attempt_rejected"` (×2, for gate-fail and low-quality rejections) or `event_type="attempt_completed"` (×2, success paths). **None passes `event_type="attempt_failed"`.**
- The only places `"attempt_failed"` is ever actually used as a literal string in the whole repo are: `execution_ledger.py`'s own declarations, and `tests/test_execution_ledger.py` (3 call sites, all calling `record_event` directly — bypassing `router.py` entirely) plus one test-name reference in `tests/test_streaming_integration.py:272` (`test_attempt_failed_before_commit`, which — not independently verified this session — appears from its name to test the ledger module's handling of the string, not to exercise a real `router.py`-driven emission).

### Control-flow trace
1. In `_dispatch_model_loop`'s per-attempt loop, when a provider call raises (a genuine "provider error" — rate limit, timeout, auth failure, etc.), the exception is caught (confirmed via the `except Exception as e:` block starting at `router.py:2636`, which classifies `is_rate_limit`/`is_content_filter`/`is_auth` and continues the loop / records `chain_errors` / triggers `cost_skipped` accounting as appropriate).
2. Nowhere in that exception-handling branch (nor anywhere else the codebase was found to touch attempt-level ledger writes) is `_emit_ledger_attempt(..., event_type="attempt_failed", ...)` called.
3. Consequently, a provider-error attempt leaves **no execution-ledger row at all** — it is invisible to `execution_ledger`'s aggregation layer (`_aggregate()`), which can only sum what was written. Only outcomes that reach an explicit `attempt_rejected` (gate/quality-check failure on a response that *was* successfully returned) or `attempt_completed` emission are ever recorded at the attempt level.

### Expected vs actual
- **Expected (per the event type's own name, its billable-set membership, and `_emit_ledger_attempt`'s docstring claim of recording "EVERY billable attempt"):** a provider error during dispatch should produce an `attempt_failed` ledger row, at minimum for cost-visibility when the provider bills for a partially-completed or errored call.
- **Actual:** provider-error attempts produce no ledger row of any kind; the event type exists only as declared-but-orphaned code, exercised solely by unit tests that call the ledger layer directly.

### Root cause
Most likely an incomplete migration/oversight: the event type and its billable-set membership were added when the ledger schema was designed, but the corresponding `_emit_ledger_attempt(event_type="attempt_failed", ...)` call was never added to the provider-exception branch in `_dispatch_model_loop`. Not independently confirmed via `git blame`/history in this session (out of scope given time budget) — flagged as the most probable explanation based on the code shape (a fully-wired constant with zero production writers is a classic "forgot to wire it up" pattern, not a deliberately-reserved-for-future-use pattern, since the docstring already claims the behavior as current).

### Confidence
**High** that the gap exists as described (exhaustive grep across `src/` and `tests/` for `attempt_failed`, and a full read of every `_emit_ledger_attempt` call site in `router.py`, confirm zero production emissions). **Low-Medium** on real-world cost impact, since most provider-error paths in this codebase appear to be genuinely $0 (rejected before any token generation, e.g. rate limits returned immediately) — the comment at `execution_ledger.py:42` itself hedges with "cost only if usage is known," suggesting the original author anticipated this would usually be a $0 record whose main value is *attempt-count* visibility (e.g., for reliability/circuit-breaker reporting) rather than cost accounting. That visibility is what's currently missing, not necessarily billing accuracy.

### Suggested acceptance test
Add a test asserting that a `route_and_call()` invocation where the chain has at least one failing-then-succeeding provider produces an `attempt_failed` (or equivalent) ledger row for the failed attempt, distinct from the final `attempt_completed` row for the succeeding one. Would fail today (zero rows for the failed attempt).

### Impact flags
`[observability-gap]` `[dead-code]` `[unconfirmed-root-cause]`

---

## Verified Clean (traced and/or reproduced this session — no defect found)

### `_release_reservation_if_held()`'s 3 in-scope early-exit call sites release exactly once
Full re-read of `router.py:3355-3594` (TQ-007 hard-block raise at 3530-3531) and `3700-3766` (envelope-reservation-failure exit at 3762) confirms each site: (a) is only reachable before `_dispatch_model_loop` has been invoked (so no risk of colliding with `_dispatch_model_loop`'s own success-path release — that's specifically what makes these different from RED1-4-01), (b) sets `_reservation_released = True` on first call so a second call to the same closure instance would short-circuit, and (c) for the envelope-fail branch specifically, explicitly nulls `_env_key = None` (line 3761) *before* calling the helper, with an inline comment confirming the intent ("so the helper does not try to release an envelope that never held") — correctly preventing a spurious envelope-release attempt for a reservation that was never granted. `tests/test_red1_3_reservation_leaks.py` (`test_no_leak_on_empty_chain`, `test_no_leak_on_cache_hit_fast_path`) and `tests/test_tq007_daily_cap_downgrade.py` (`test_hard_block_releases_pending_spend_reservation`) exercise these paths and pass on the current code; their logic was independently traced against the source, not merely trusted.

### `_dispatch_model_loop`'s all-models-failed tail: `_pending_spend` (not the envelope) is released correctly
Full re-read of `router.py:2790-2889` confirms the raw, unconditional release at 2813-2816 runs before every one of the block's four exits (the two specific raises, the exhaustion-floor return, and the generic `RuntimeError`). Cross-referenced with the file-wide 4-call-site grep for `_release_reservation_if_held` (none near the dispatch-invocation block) to confirm `route_and_call` does not also independently re-release `_pending_spend` for this exception class — so, unlike RED1-4-01's success path, there is no double-release here. (The envelope specifically *is* leaked on this same path — see RED1-4-02.)

### `release_envelope(None, ...)` / `commit_envelope(None, ...)` are safe, explicit no-ops
`quota_envelope_routing.py:100-101` and `112-113` both start with `if key is None: return`. This resolves what was an open question at the start of this session (whether the several call sites that call `release_envelope(_env_key, _reservation)` *unconditionally*, i.e. without an `if _env_key is not None:` guard — `router.py:3842`, `3931`, `3937` — could misbehave when `_env_key` is `None`, which per `reserve_envelope`'s own contract is the common case in the default `off` envelope mode). Confirmed safe: calling with `key=None` always returns immediately without touching the backend.

### `correlation_id` is never falsy in practice — the pervasive `or ""` fallbacks are dead-but-harmless
`correlation_id = uuid4().hex[:8]` (`router.py:3018`, `4317` — the only two assignment sites) always produces a non-empty 8-character hex string; a `uuid4()` call cannot realistically produce an all-zero UUID whose truncated hex would be empty (probability ~0, and even so the string `"00000000"` is still truthy). The `correlation_id or ""` / `session_id=... or (correlation_id or "")` patterns seen throughout (`router.py:1633-1634`, `1659-1660`, `2351`, etc.) are therefore defensive code that never actually triggers on the empty-string branch in the current call graph — not a functional bug, just unreachable defensiveness. No route-id nonce/dedup weakness was found stemming from this.

### TQ-007 daily-cap downgrade / anthropic cap-fallthrough logic (re-confirmed by full code read, not independently re-executed this session)
`router.py:3481-3531`, re-read in full this session, matches the behavior asserted by `tests/test_tq007_daily_cap_downgrade.py` exactly: cap-exceeded confines the chain to free-local providers if any exist; otherwise, under `smart`/`soft` enforce mode with a Claude model present in the original chain, falls through to a Claude-only chain (never a non-Claude paid provider); under `hard`, or `smart`/`soft` with no Claude available, raises via the guarded helper. No path was found where a non-Claude paid model dispatches while a daily cap is actively exceeded.

---

## Explicitly Out of Scope / Not Chased This Session (time-budget triage, not "checked and clean")

- **Cross-process cap bypass** — not investigated this session (or any prior session per the inherited audit trail). Would require exercising two real separate OS processes against a shared `CHUZOM_DB_PATH`/backend, which was not attempted.
- **Classification/capability concerns** — not investigated this session.
- **Restart/recovery** — not investigated this session (e.g., whether `_pending_spend`, being a pure in-memory module global, is expected to reset to 0 on every process restart, and whether that's consistent with how the distributed envelope's cross-process state is expected to reconcile — plausible interaction with RED1-4-01/02 but not traced).
- **`execution_ledger.py` `ORDER BY` determinism and `_aggregate()`** — covered by a **prior session** in this same audit lineage (per the inherited summary, concluded clean with a "no double-count" verification of rejected-attempt-spend accounting), not independently re-verified this session since `execution_ledger.py` was flagged this session as already-read-but-too-large-to-re-include; treat that specific conclusion as **carried-over, not freshly re-confirmed**.
- **`route_id` nonce/dedup semantics beyond the `correlation_id` emptiness check above** — the emptiness sub-question is resolved (see Verified Clean); broader dedup-collision analysis (e.g., whether two truly concurrent calls could ever generate the same `uuid4().hex[:8]` and collide in the ledger) was not attempted (astronomically unlikely given 32 bits of entropy at 8 hex chars, not treated as a credible attack surface worth reproducing).
- **Sibling audit cross-reference**: a background task output at `/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/cedb4281-dede-47c9-98cc-94346f802354/tasks/ac79b4b53bea6c3b9.output` was flagged for review; its content is the same material now published as `/Users/yaliandrona/Projects/Chuzom/.chuzom/release-convergence/iteration-04/red-2-report.md` (RED-2, a separate "customer reality & failure" audit covering instruction-file integrity, not budget/reservation mechanics). Skimmed for overlap: no overlap with this report's findings (RED-2's findings concern orphaned rules files and unscanned capability-claim strings, entirely disjoint from `router.py`'s reservation lifecycle).

---

## Methodology Note

All findings above with a "Reproduction" section were executed against the real repository code (`.venv`, `CHUZOM_ENFORCE` unset for route tests, isolated `CHUZOM_DB_PATH`/`CHUZOM_EXECUTION_LEDGER_DB` temp files), not inferred from comments or docstrings — the design comment at `router.py:3352-3361` describing the guarded helper's purpose was treated as a claim to verify, not a fact, and the verification found the claim to be **true for the 4 early-exit paths it was built for**, but **false for two paths it does not cover** (the success path, RED1-4-01; and the envelope specifically on the all-models-failed path, RED1-4-02). No prior audit iteration's conclusions were trusted without independent re-tracing against current line numbers in this session; where a prior conclusion was relied upon without fresh re-verification (execution_ledger `_aggregate`/rejected-spend accounting), this is explicitly flagged above rather than presented as freshly confirmed.
