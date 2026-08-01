# RED-1 Architecture & Correctness Audit — Iteration 05

Auditor: RED-1 (independent, no cross-read of RED-2's report)
Commit audited: `d80ab4b`
Repo: `/Users/yaliandrona/Projects/Chuzom`

Verdict: **NOT CLEAN — 2 High, 1 Critical.**

| ID | Severity | One-line title |
|---|---|---|
| RED1-5-01 | Critical | `SqliteBudgetBackend.commit()` double-decrements `pending_usd`, letting concurrent siblings sharing an envelope blow past the hard cap (150%-of-cap admission demonstrated) |
| RED1-5-02 | High | `_pending_spend` in-process reservation counter is double-released on every successful `route_and_call` turn (self-acknowledged tech debt), eroding a concurrent sibling's outstanding reservation and under-counting true in-flight exposure for the TOCTOU budget check |
| RED1-5-03 | High | `_turn_blocked` in `auto-route.py` silently overrides an operator's explicit `CHUZOM_RENDER_MODE=echo` into turn-replacing "block" behavior whenever `CHUZOM_ZERO_CLAUDE` is also enabled, contradicting the function's own "explicit echo/block is honored unchanged" guarantee and bypassing Claude verification exactly where CHZ-DRAFT-01/RED2-01 was built to prevent that |

---

## RED1-5-01 — `pending_usd` double-decrement in `SqliteBudgetBackend.commit()` lets concurrent siblings exceed a strict-mode hard cap

**Severity: Critical** (wrong billing/budget enforcement — a hard cap enterprise strict-mode envelope is supposed to guarantee is provably breachable)

**Location:**
- `src/chuzom/budget_backend.py`, `SqliteBudgetBackend._commit_sync()` (~lines 499-535), specifically the `UPDATE envelopes SET consumed_usd = consumed_usd + ?, pending_usd = max(0.0, pending_usd - ?) ...` statement that subtracts `cost_usd` (the *actual* settled cost) from `pending_usd` a second time.
- `src/chuzom/quota_envelope_routing.py`, `commit_envelope()` (lines 96-107) — the sole production caller, which does `await b.release(key, est_cost_usd)` followed immediately by `await b.commit(key, actual_cost_usd)`.
- Called from `src/chuzom/router.py` at the end of `route_and_call`'s success path (~lines 4041-4043): `await commit_envelope(_env_key, _reservation, float(getattr(response, "cost_usd", 0.0) or 0.0))`.

**Failure scenario:**
Two concurrent calls A and B share one envelope key (e.g. same user, or a parent/org rollup key), cap = $2.00.
1. A reserves $1.00 → `pending_usd = 1.00`.
2. B reserves $1.00 → `pending_usd = 2.00` (both admitted; `2.00 <= cap`).
3. A completes with actual cost $1.00. `commit_envelope` calls:
   - `release(key, 1.00)` → `pending_usd = max(0, 2.00 - 1.00) = 1.00` (correctly reflects B's still-outstanding reservation).
   - `commit(key, 1.00)` → `consumed_usd += 1.00` **and** `pending_usd = max(0, pending_usd - 1.00) = 0.00`. This second subtraction erases B's legitimately outstanding $1.00 — B never asked to have its reservation touched by A's commit.
4. A third caller C now reserves $1.00. The check is `consumed(1.00) + pending(0.00) + 1.00 = 2.00 <= cap(2.00)` → **admitted**. But B is still in flight with its own $1.00 reservation, so true exposure is `consumed(1.00) + B(1.00) + C(1.00) = 3.00`, i.e. **150% of the configured $2.00 cap**.

This directly contradicts the module's own docstring for `commit_envelope` (lines 21-25): *"`release(est)` undoes the reservation and `commit(actual)` records true spend, so `pending` stays clean even when the estimate and the actual cost differ."* That guarantee only holds for a single caller — under concurrent siblings sharing a key it is false.

**Why existing tests miss it:** `tests/test_t2_l1_sqlite_budget_backend.py::test_commit_moves_pending_to_consumed` calls `commit()` directly without a prior `release()` — not the production calling pattern. `tests/test_p0_3_envelope_enforce.py::test_routed_turn_decrements_shared_envelope` does exercise the real `commit_envelope` (release+commit), but only with a single caller, where the bug's effect is invisible because `pending_usd` is already 0 by the time the second (buggy) subtraction runs, so `max(0.0, ...)` clamps it harmlessly. No existing test has two concurrent reservations sharing a key with one committing while the other is still outstanding.

**CONFIRMED** — reproduced against the real `SqliteBudgetBackend` (temp SQLite file, `CHUZOM_ENVELOPE_MODE=strict`) via `quota_envelope_routing.reserve_envelope` / `commit_envelope`, the actual production entry points.

Repro: `/tmp/scratchpad/repro_envelope_double_release.py` (full source retained; see also description above), run with:
```
CHUZOM_ENVELOPE_MODE=strict PYTHONPATH=src .venv/bin/python repro_envelope_double_release.py
```
Output:
```
reserve A ok=True  reserve B ok=True
after both reservations: pending=2.0 consumed=0.0
after A commits: pending=0.0 consumed=1.0
expected pending (B still outstanding) = 1.0
BUG CONFIRMED: pending_usd eroded by A's commit; expected 1.0, got 0.0 (erosion amount = 1.0)
reserve C (should be refused if accounting is correct) ok=True
CRITICAL BUG CONFIRMED: third reservation C was admitted even though B's 1.0 reservation is still outstanding and A already consumed 1.0 against a cap of 2.0 -- envelope allows total exposure of consumed(1.0) + B(1.0) + C(1.0) = 3.0 > cap 2.0.
```

**Suggested fix:** `commit()` should not independently subtract `cost_usd` from `pending_usd` when it is always paired with a preceding `release(est_cost_usd)` in the only production call site. Either (a) make `commit()` a pure "move to consumed" ledger entry that does not touch `pending_usd` at all (since `release()` already settled the reservation), or (b) if `commit()` must remain independently callable and safe to invoke without a prior `release()`, have `quota_envelope_routing.commit_envelope()` pass the *estimate* (not the actual cost) to whichever step decrements `pending_usd`, and reserve the actual-vs-estimate delta adjustment for `consumed_usd` only. Add a regression test with two concurrent reservations sharing one key, one committing while the sibling is still outstanding, asserting `pending_usd` after the first commit still reflects the sibling's reservation.

---

## RED1-5-02 — `_pending_spend` double-release erodes a concurrent sibling's reservation (self-acknowledged tech debt, in-process analogue of RED1-5-01)

**Severity: High** (wrong behavior on a real path under true concurrency; blast radius is smaller than RED1-5-01 because this is the in-process-only reservation used for the daily/monthly TOCTOU pre-check, not the persistent cross-process envelope, and the persistent ledger in `budget_backend`/`cost` tracking still records true committed spend after the fact — but the TOCTOU guard itself is provably defeated, exactly the guard's entire purpose)

**Location:** `src/chuzom/router.py`, `route_and_call` success path, line ~4020: `_pending_spend = max(0.0, _pending_spend - _reservation)`, immediately preceded by the code's own comment block (lines ~4009-4018) acknowledging this is a "second decrement — a double-release for the shared counter... only bites under true concurrency," left in deliberately after removing it broke 11 other tests. `_dispatch_model_loop` already releases the same `_reservation` amount from the same global on its own success path at lines 2630 (primary chain) and 2782 (emergency BUDGET chain).

**Failure scenario:** `_pending_spend` (router.py line 1093) is a single module-global `float` shared by **all** in-flight calls — not scoped per call. Reservations accumulate additively (`_pending_spend += reservation`, line 3346) and are meant to be released additively exactly once per reservation. Two concurrent calls A and B each reserve $1.00 → `_pending_spend = 2.00`. A's dispatch succeeds; `_dispatch_model_loop`'s own success-path release fires first, correctly bringing the shared pool to $1.00 (B's still-outstanding share). `route_and_call`'s success path then runs its own (redundant) release of A's `_reservation` again, bringing the pool to $0.00 — erasing B's legitimately outstanding reservation, which A had no claim over. A subsequent caller C's TOCTOU check (`daily_spend_committed + _pending_spend + C_estimate <= cap`) now under-counts true in-flight exposure by B's full reservation amount, and can admit C when `B + C` alone already exceeds the cap.

**CONFIRMED** — reproduced against the real `chuzom.router` module globals (`_pending_spend`, `_budget_lock()`), replaying the exact sequence both code paths perform.

Repro: `/tmp/scratchpad/repro_pending_spend_double_release.py`, run with `.venv/bin/python`. Output:
```
after A+B reserve: _pending_spend = 2.0
after A's dispatch-loop release: _pending_spend = 1.0  (correct: should reflect only B's still-outstanding 1.0)
after A's route_and_call SECOND release: _pending_spend = 0.0
BUG CONFIRMED: shared _pending_spend pool eroded by A's redundant second release. Expected 1.0 (B's outstanding reservation untouched), got 0.0. Erosion = 1.0
C's budget check: committed(0.0) + pending(0.0) + C's own estimate(1.0) = 1.0 vs cap 1.5
CRITICAL: C would be ADMITTED under a cap of 1.5, even though B's outstanding reservation (1.0) + C's own estimate (1.0) = 2.0 ALONE already exceeds the cap — the erosion caused the TOCTOU guard to under-count true in-flight exposure.
```

**Note on prior context:** this exact defect was already identified and explicitly left in place per a documented tradeoff (the "RED1-4-01 NOTE" comment names it and states the correct fix — a single-owner reservation-lifecycle refactor — is tracked as follow-up work, not a tail-of-session patch). I re-confirm it here empirically (the comment describes the mechanism but the code itself carries no test proving the magnitude of the exposure), and it remains release-blocking in my assessment: it is a live, reachable defeat of a budget safety guard, not merely theoretical. The fact that it is "known" does not change its severity for a release-blocking audit — it changes only the recommended remediation urgency framing (there is already a designed fix path).

**Suggested fix:** as the existing NOTE states — implement the single-owner reservation lifecycle: reserve once at the top of `route_and_call`, release exactly once in a `finally`, and remove the ~10 scattered `_pending_spend -=` call sites inside `_dispatch_model_loop` and `route_and_call` (including the ones at lines 2630, 2782, 3372, 3679, 3841, 3930, 3936, in addition to 2814 and 4020). Until that refactor lands, a narrower stop-gap is to have `_dispatch_model_loop` return whether it already released the reservation (e.g. via a sentinel or an explicit `released: bool` on its result) so `route_and_call`'s success-path release can skip when redundant, closing the gap without the full refactor.

---

## RED1-5-03 — Explicit `CHUZOM_RENDER_MODE=echo` is silently overridden to turn-replacing "block" behavior when `CHUZOM_ZERO_CLAUDE` is also set

**Severity: High** (wrong behavior on a real, independently-configurable path; silently defeats an operator's explicit safety/advisory-mode choice and lets a routed draft answer bypass Claude and replace the user's turn — the exact fabrication risk CHZ-DRAFT-01/RED2-01 was introduced to gate behind explicit opt-in)

**Location:**
- `src/chuzom/hooks/auto-route.py`, `_resolve_auto_render_mode()` (line 2243) — correct in isolation.
- `src/chuzom/hooks/auto-route.py`, call site line 3226: `_turn_blocked = not (_render_mode == "echo" and not zero_claude)`.
- `RENDER_MODE` sourced from `CHUZOM_RENDER_MODE` env var (`src/chuzom/hooks/response_formatter.py:23`, default `"auto"`).
- `zero_claude` sourced from `_zero_claude_enabled()` (`auto-route.py` lines 1692-1710), driven by the **independent** `CHUZOM_ZERO_CLAUDE` env var (or `routing.yaml` `mode:` fallback) — documented (line 1687-1688) as "for users protecting Claude Code subscription quota," a legitimate, unrelated reason to enable it.

**Failure scenario:** `CHUZOM_RENDER_MODE` and `CHUZOM_ZERO_CLAUDE` are independent knobs; an operator can realistically set both — e.g. `CHUZOM_ZERO_CLAUDE=1` to protect Claude Code subscription quota, and `CHUZOM_RENDER_MODE=echo` because they specifically want every routed answer to remain advisory (verified by Claude before being trusted), not silently substituted for the turn. `_resolve_auto_render_mode()` correctly leaves an explicit (non-"auto") render mode untouched — its own docstring promises *"An explicit CHUZOM_RENDER_MODE of 'block'/'echo' is honored unchanged."* But `_turn_blocked`'s formula re-applies the `zero_claude` condition on top of that already-resolved value: `not (_render_mode == "echo" and not zero_claude)` evaluates to `True` (blocked) whenever `zero_claude` is `True`, **even when `_render_mode == "echo"` explicitly**. When `_turn_blocked` is `True`, the code path at line 3288 (`_output = _build_block(...)`) fires, followed by `json.dump(...)` and `sys.exit(0)` (line 3293-3294) — Claude never sees the prompt; the routed model's draft directly replaces the user's turn. So the operator's explicit "echo only, always advisory" configuration is silently converted into exactly the turn-replacing behavior they opted out of.

**CONFIRMED** — reproduced by extracting the exact verbatim two-line production logic (`_resolve_auto_render_mode` body and the `_turn_blocked` expression, copied character-for-character from the current file) and exercising all four combinations of explicit vs. auto render mode against `zero_claude ∈ {False, True}`.

Repro: `/tmp/scratchpad/repro_render_mode_turn_blocked.py`, run with `.venv/bin/python`. Output:
```
render_mode_in  zero_claude   resolved  expected_blocked  actual_blocked  result
auto            False         echo      False             False           OK
auto            True          block     True              True            OK
echo            False         echo      False             False           OK
echo            True          echo      False             True            BUG
block           False         block     True              True            OK
block           True          block     True              True            OK

BUG CONFIRMED: explicit CHUZOM_RENDER_MODE=echo + CHUZOM_ZERO_CLAUDE=True resolves to render_mode='echo' (correctly honored unchanged by _resolve_auto_render_mode) but _turn_blocked is computed True anyway -- the turn is force-blocked (Claude bypassed, routed draft replaces the turn via _build_block + sys.exit(0)) even though the operator explicitly configured advisory-only echo display. This contradicts the function's own docstring guarantee that explicit echo/block is 'honored unchanged'.
```
Note all other combinations, including the `"auto"` cases that CHZ-DRAFT-01/RED2-01 was specifically designed to fix, are correct — only the explicit-`"echo"`-plus-`zero_claude`-True cell is wrong.

**Secondary observation (not separately scored — documentation staleness, not a defect):** the older comment block immediately above the call site (auto-route.py lines 3211-3217) still describes `"auto"` as resolving to `"block"` "for drafts answering self-contained prompts," which does not match `_resolve_auto_render_mode`'s actual (simpler, zero_claude-only) resolution logic post-RED2-01. Worth a documentation pass so a future maintainer reading the call site doesn't get confused about which invariant is actually enforced where — but this is a comment-accuracy issue, not the reported code defect.

**Suggested fix:** `_turn_blocked` should be derived purely from the already-resolved `_render_mode` value, not by re-testing `zero_claude` a second time — the zero_claude gating is `_resolve_auto_render_mode`'s job and it has already been applied by the time `_render_mode` reaches this line. Replace with `_turn_blocked = _render_mode != "echo"` (i.e., "echo" never blocks, any other resolved mode — "block", or any future explicit value — does), which correctly reproduces all six cases above including the previously-wrong `echo` + `zero_claude=True` cell. Add a regression test covering the four `(explicit render_mode, zero_claude)` combinations directly against `_turn_blocked`'s computation (or an equivalent integration test asserting Claude is *not* bypassed when `CHUZOM_RENDER_MODE=echo` regardless of `CHUZOM_ZERO_CLAUDE`).

---

## Focus areas assessed CLEAN (no Critical/High/core-Medium findings)

- **Concurrency locks / `_BG_TASKS`** (`src/chuzom/router.py` lines ~95-122, ~1075-1119): `_AsyncProcLock`'s critical sections are short and never hold the lock across a nested `await`; `_BG_TASKS`/`_spawn_bg()`/`drain_bg_tasks()` is a correctly-implemented fire-and-forget pattern (strong references prevent premature GC, `add_done_callback` cleans up, `drain_bg_tasks` awaits-with-timeout then cancels+gathers stragglers on shutdown). No defect found.
- **Frozen `LLMResponse` mutation** (`src/chuzom/types.py`): exhaustive greps for direct-assignment patterns on response-like variables and on every `LLMResponse` field name found zero hits; the main construction/modification site (`_enrich_response()`, router.py ~1488-1503) correctly uses `dataclasses.replace()`. No defect found.
- **RED1-4-02 envelope-release exception handler** (`route_and_call`, router.py ~3995-4008): correctly scoped — `_dispatch_model_loop`'s post-loop exhaustion tail (line 2814) unconditionally releases `_pending_spend` exactly once before raising any of `RuntimeError`/`CostBudgetExceeded`/`PermissionDenied`, so this handler's own logic (release the distributed envelope only, not `_pending_spend` again) is internally consistent and does not itself introduce a new double-release. Its interaction with the RED1-4-01 double-release pattern (RED1-5-02 above) is a pre-existing, separately-documented issue, not a defect in this specific handler.
- **TQ-007 cap-downgrade ordering** (router.py ~3411, ~3481-3531): applied last, after precision-tier fronting / subject-specialist / bandit reorder, as intended (RED1-01/RED1-02 fix comment verified against current code). The block/hard-refuse branch correctly calls `_release_reservation_if_held()` exactly once before raising the cap-exceeded exception (line 3530-3531) — consistent with, not an additional instance of, the RED1-5-02 pattern.
- **Mid-loop `RuntimeError` raises inside `_dispatch_model_loop`** (router.py lines 2119, 2152, 2184 — Codex/Gemini-CLI/Claude-CLI subprocess failure paths): these are per-model-attempt failures inside the per-attempt loop body, caught by the loop's own per-attempt exception handling and used to advance to the next candidate model, not exits that bypass the loop's success/exhaustion release sites (2630/2782/2814). No additional `_pending_spend` release gap found here.

## Report format note

The mandate's specified fallback line ("CLEAN — no Critical/High/core-Medium findings") does not apply to this iteration: three findings meeting the severity bar were confirmed (one Critical, two High).
