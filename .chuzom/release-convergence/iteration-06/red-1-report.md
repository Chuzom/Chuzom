# RED-1 Architecture & Correctness Audit — Iteration 6

Commit: `1dd7401`. Role: adversarial ARCHITECTURE & CORRECTNESS auditor,
independent of RED-2. Goal: try hard to break the iteration-5 fixes
(RED1-5-01 envelope `settle_pending`, RED1-5-02 `_pending_spend`
release-exactly-once, RED1-5-03 `auto-route.py` render-mode blocking) plus
broad coverage.

## Summary

| ID | Severity | Title |
|---|---|---|
| RED1-6-01 | High | Multi-level budget-envelope parent chains only propagate one hop — caps 2+ levels up silently never see spend |
| RED1-6-02 | High | Any unrecognized `CHUZOM_RENDER_MODE` value fails toward full turn-blocking, not toward the safe "echo" default the RED1-5-03 fix was written to guarantee |

No Critical findings. The two headline iteration-5 fixes (RED1-5-01 `settle_pending`
double-decrement, RED1-5-02 `_pending_spend` leak) held up under adversarial
testing — see "What I tried to break" below.

---

## RED1-6-01 — Multi-level parent-chain rollup only walks one hop

**Severity:** High
**Files:**
- `src/chuzom/budget_backend.py:390-403` (`SqliteBudgetBackend._chain_rows`)
- `src/chuzom/budget_backend_postgres.py:372-391` (`PostgresBudgetBackend._chain_keys`)
- `src/chuzom/budget_envelope.py:177-190` (`BudgetEnvelopeManager._chain`)
- Design context: `src/chuzom/budget_key.py:45-88` (`BudgetKey.rolls_up_to`)

**Scenario:** `BudgetKey` is explicitly documented as a 4-level hierarchy
("tenant → org → user → agent", `budget_key.py:49-51`) with
`rolls_up_to(drop=...)` as the one-level-at-a-time coarsening primitive an
operator is meant to use to build parent keys. All three backend
implementations (`BudgetEnvelopeManager`, `SqliteBudgetBackend`,
`PostgresBudgetBackend`) implement the "chain" for `try_reserve`/`release`/
`commit` identically: load the leaf envelope's own `parents` tuple, then for
each of *those* parent keys look up the row directly — but never fetch
*that* parent's own `parents` field to continue walking upward. So if an
operator registers a natural 3-level hierarchy the way `rolls_up_to`
implies — each level pointing only at its own immediate parent
(`register(org_key, cap)`, `register(user_key, cap, parents=(org_key,))`,
`register(agent_key, cap, parents=(user_key,))`) — then any reservation at
the `agent_key` leaf touches `[agent, user]` only. The `org_key` envelope
(2 hops up) never has its `pending_usd`/`consumed_usd` touched by that
spend, ever. Its cap can never trigger and its `remaining`/`consumed`
readouts stay permanently wrong regardless of how much is actually spent
underneath it.

This is not a hypothetical multi-tenant-future concern only: per
`budget_key.py:98` ("Phase 3a semantics: tenant_id defaults to org_id"),
`tenant_id == org_id` today, so the practically-relevant 3-level hierarchy
in the *current* single-tenant deployment is exactly org → user → agent —
the same shape reproduced below. Any operator who registers an
enterprise-wide org-level cap plus per-user and per-agent-session caps
underneath it (the natural, incremental way to build this, and the only
way `rolls_up_to` supports building it) gets an org-level cap that is
silently unenforceable against agent-scoped spend.

**CONFIRMED** — repro at `/tmp/red1_iter6_chain_repro.py`, run with
`/Users/yaliandrona/Projects/Chuzom/.venv/bin/python`:

```
Before reserve:
  org  consumed/pending: 0.0 0.0
  user consumed/pending: 0.0 0.0
  agent consumed/pending: 0.0 0.0

try_reserve(agent_key, 10.0) -> True

After reserve:
  org  consumed/pending: 0.0 0.0
  user consumed/pending: 0.0 10.0
  agent consumed/pending: 0.0 10.0

After release(10)+commit(10, settle_pending=False):
  org  consumed/pending: 0.0 0.0
  user consumed/pending: 10.0 0.0
  agent consumed/pending: 10.0 0.0

VERDICT: org (2 hops up) untouched despite spend = True
VERDICT: user (1 hop up) correctly settled = True
```

The `user` level (1 hop) settles correctly — this also confirms the
RED1-5-01 `settle_pending=False` fix itself has no double-decrement bug at
the level it does reach (see "What I tried to break" below). The bug is
purely the missing chain-depth recursion.

**Suggested fix:** make `_chain_rows`/`_chain_keys`/`_chain` walk
transitively (follow each parent's own `parents` field until exhausted, with
a cycle guard) instead of stopping after one hop. All three backends need
the same fix to stay in parity.

---

## RED1-6-02 — Unrecognized `CHUZOM_RENDER_MODE` fails toward turn-blocking, not toward safe echo

**Severity:** High
**Files:**
- `src/chuzom/hooks/response_formatter.py:23` (`RENDER_MODE = os.environ.get("CHUZOM_RENDER_MODE", "auto").lower()`)
- `src/chuzom/hooks/auto-route.py:2243-2256` (`_resolve_auto_render_mode`)
- `src/chuzom/hooks/auto-route.py:3225-3233` (RED1-5-03 fix site: `_turn_blocked = _render_mode != "echo"`)

**Scenario:** The RED1-5-03 comment (`auto-route.py:3226-3232`) states the
fix exists specifically so that "echo never blocks," fixing a prior bug
where an operator's explicit `CHUZOM_RENDER_MODE=echo` (paired with
`CHUZOM_ZERO_CLAUDE=1`) got force-blocked. The new logic derives blocking
purely from the resolved mode string: `_turn_blocked = _render_mode != "echo"`.

`_resolve_auto_render_mode` only special-cases the literal string `"auto"`;
every other value (including typos, trailing whitespace from a config file,
an accidentally-empty env var, or an operator's reasonable-but-unsupported
guess like `"off"`/`"disabled"`/`"warn"`) passes through unchanged and then
fails the `!= "echo"` test — i.e. **any unrecognized value silently
resolves to full turn-blocking** (the user's turn is replaced by an
unverified, possibly-fabricated routed draft), even when
`CHUZOM_ZERO_CLAUDE` is unset/false. There is no allow-list validation
anywhere in the codebase for `CHUZOM_RENDER_MODE` (grepped
`src/chuzom/` and `Docs/` — only the three references above and the docs
description). This is the same class of danger RED1-5-03 was written to
close (an operator ends up with turn-blocking they did not opt into), just
reached through a config typo instead of the zero_claude interaction.

**CONFIRMED** — repro executed with
`/Users/yaliandrona/Projects/Chuzom/.venv/bin/python` against the real
`_resolve_auto_render_mode` function loaded from
`src/chuzom/hooks/auto-route.py`:

```
CHUZOM_RENDER_MODE=     'eco' zero_claude=False -> resolved=     'eco' turn_blocked=True
CHUZOM_RENDER_MODE=        '' zero_claude=False -> resolved=        '' turn_blocked=True
CHUZOM_RENDER_MODE=    'warn' zero_claude=False -> resolved=    'warn' turn_blocked=True
CHUZOM_RENDER_MODE=     'off' zero_claude=False -> resolved=     'off' turn_blocked=True
CHUZOM_RENDER_MODE='disabled' zero_claude=False -> resolved='disabled' turn_blocked=True

CHUZOM_RENDER_MODE='echo'  zero_claude=False -> resolved='echo'  turn_blocked=False   (correct)
CHUZOM_RENDER_MODE='block' zero_claude=False -> resolved='block' turn_blocked=True    (correct — explicit opt-in)
CHUZOM_RENDER_MODE='auto'  zero_claude=False -> resolved='echo'  turn_blocked=False   (correct)
CHUZOM_RENDER_MODE='auto'  zero_claude=True  -> resolved='block' turn_blocked=True    (correct)
```

A bare `eco` typo, or an env-file line that sets `CHUZOM_RENDER_MODE=` with
nothing after the `=` (a realistic deployment mistake), silently escalates
from "advisory echo" to "replace the turn with a possibly-fabricated
draft" — with no error, no log line, and no `zero_claude` opt-in involved.

**Suggested fix:** validate `_render_mode` against the allow-list
`{"echo", "block"}` after resolving `"auto"`; treat any other value as a
configuration error that falls back to the safe default (`"echo"`) and logs
a warning, rather than deriving blocking from `!= "echo"` (which fails
open toward the more dangerous behavior for any unrecognized string).

---

## What I tried to break (and could not)

- **RED1-5-01 (`settle_pending` double-decrement):** traced
  `release(est)` → `commit(actual, settle_pending=False)` across
  `est==actual`, `actual>est`, `actual<est`, `actual==0`, `est==0`, and the
  actual-code-execution case confirmed by the RED1-6-01 repro above (the
  `user` level in that repro settles to `consumed=10.0, pending=0.0` with
  no residual/negative pending) — no double-decrement, no leak, in either
  `SqliteBudgetBackend` or `PostgresBudgetBackend`. Both backends and the
  in-process `BudgetEnvelopeManager` gate all three mutating calls on
  `cost_usd <= 0: return` symmetrically, so the `actual==0` /
  `est==0` edge cases are clean early-return no-ops, not partial-write
  hazards.
- **`commit_envelope`'s release-succeeds-then-commit-raises window**
  (`quota_envelope_routing.py:109-112`): confirmed this is possible (the two
  awaits are sequential, not one transaction, and a transient SQLite-busy or
  Postgres-connection-drop between them would leave `pending_usd` correctly
  cleared but `consumed_usd` under-counted for that turn) but did not find
  it to be a *leak* — it under-counts real spend rather than double-billing
  or leaking a reservation, is caught and logged
  (`envelope_commit_failed`), and requires a narrow timing window on top of
  an already-degraded store. Judged below reportable severity for this
  audit's bar (no double-spend, no permanently-stuck `pending`, fail-open
  by design).
- **RED1-5-02 (`_pending_spend` release-exactly-once):** mapped every exit
  from `_dispatch_model_loop` (`router.py:1668-2890`). Three internal
  `RuntimeError`s from CLI subprocess failures (~2119/2152/2184) are all
  caught by the per-attempt `except Exception` at line 2636 and never
  escape the function. Three tail raises (`CostBudgetExceeded` ~2826,
  `PermissionDenied` ~2846, final `RuntimeError` "All models failed"
  ~2887) all occur strictly after the unconditional release at
  2813-2814. Found and specifically stress-tested a previously-unlabeled
  **third success-return path** — the exhaustion-floor / "lever ①" return
  of `_best_rejected` (lines 2862-2884) — not named in the RED1-5-02
  comment (which only cites the primary-chain and emergency-BUDGET success
  sites). Confirmed this path is also safe: it occurs after the 2813-2814
  release, and the return value is built via `_enrich_response`
  (`router.py:1488-1503`), which is a *synchronous* function (`replace()`
  on a frozen dataclass, no `await`) — so there is no cancellation window
  between the release and the return where `asyncio.CancelledError` could
  slip in and skip the release. `route_and_call`'s outer dispatch handling
  (`router.py:2893+`) does not distinguish which of the three success paths
  fired inside `_dispatch_model_loop`; it uniformly proceeds to
  `_enrich_response` → audit → `record_consumption` →
  `commit_envelope` whenever the dispatch await does not raise, so the
  exhaustion-floor path gets the same envelope-commit treatment as the
  other two. **No leak found on any of the three success paths**, including
  under the `asyncio.CancelledError`-mid-release edge case (any
  `CancelledError` raised *inside* `_dispatch_model_loop` before its own
  release fires is a `BaseException`, not caught by the loop's
  `except Exception`, and propagates to `route_and_call`'s dedicated
  `CancelledError` handler at line 3888, which performs its own
  `_pending_spend` + envelope release — exactly once, since the inner
  release never ran on that path).
- **RED1-5-03 (`_turn_blocked` derivation):** the fix itself is correct for
  the two values it was built to protect (`"echo"` never blocks,
  `"block"` always blocks) — see RED1-6-02 above for the residual gap
  (unrecognized values).
- **Postgres backend parity with SQLite** (`budget_backend_postgres.py`):
  read `try_reserve`/`release`/`commit`/`_chain_keys` in full
  (lines 209-410). Confirmed identical `settle_pending` SQL-fragment logic
  and identical `cost_usd <= 0` early-return guards to the SQLite backend —
  no divergence found other than the shared one-hop chain-walk bug
  (RED1-6-01, present in both).
- **Frozen `LLMResponse` mutation:** grepped `router.py` for direct
  attribute assignment on response objects (`response\.\w+\s*=`,
  `resp\.\w+\s*=`) — no matches; all response enrichment goes through
  `dataclasses.replace()` in `_enrich_response`.
- **`_release_reservation_if_held()` idempotency:** confirmed it is a
  locally-scoped closure used only for pre-dispatch early exits (empty
  model chain, semantic-cache hit, envelope-reservation-denied) and is
  never called again after dispatch begins, so it cannot double-release
  against `_dispatch_model_loop`'s own release sites.

## Not fully covered in this pass (time-boxed)

- `_BG_TASKS` drainage correctness under abnormal shutdown was read
  structurally but not stress-tested with a concurrency repro.
- The `reserve_envelope` fail-open catch-all
  (`quota_envelope_routing.py:88-92`) masking a partially-committed SQL
  transaction was considered but not deeply chased — both backends wrap
  their mutating paths in explicit `try/except: rollback(); raise` around
  the whole transaction (`_try_reserve_sync`/`_release_sync`/
  `_commit_sync` in both `budget_backend.py` and
  `budget_backend_postgres.py`), which structurally rules out a partial
  write surviving an exception, so this was not pursued further given the
  time budget.
