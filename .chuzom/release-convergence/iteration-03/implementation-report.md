# Iteration 3 — Implementation Report (FIX)

Fresh RED-1 (3 High + 2 Med) + RED-2 (1 High + 1 Med + 2 Low, + 5 earned-clean) on HEAD 3f5a311. Material findings independently re-reproduced by PLAN.

## Fixes landed (8 of 9 findings; test-first, GATE-verified)

| PLAN ID | Sev | Commit | Fix |
|---------|-----|--------|-----|
| **Q3-RESLEAK-CLASS** (RED1-3-01/02/03) | High×3 | `db809ca` | One idempotent `_release_reservation_if_held()` at every early-exit path (empty-chain, cache-hit, envelope-fail, cap raises). Root-cause fix subsuming iter-2 Q-RESLEAK. Full suite 6404 green — no regression on the hottest function. |
| **Q3-RENDER** (RED2-3-01) | High | `ee9fe11` | Downgrade render describes the REAL provider (`_cap_downgrade_target()`): "free/local" for local, "Claude (subscription)" for anthropic — no longer claims free-local for a paid Claude fallthrough. |
| **Q3-CLAIMS2** (RED2-3-02) | Med | `ee9fe11` | Removed "50–100x"/"10-50x"/"50x cheaper" from rules/enforce-route/agent-route (last not even audit-flagged — caught by the broadened guard); guard now matches `NN-NNx` multipliers and scans rules/*.md + *.mdc. |
| **Q3-LEDGERORDER** (RED1-3-05) | Med | `ee9fe11` | `_load_rows` ORDER BY ts, event_id → deterministic realization merge. |
| **Q3-QUOTABUCKET** (RED2-3-03) | Low | `ee9fe11` | gemini_cli added to quota_savings free-local bucket. |

## Not fixed — architectural / protocol limitation (documented, not deferred silently)

**Q3-ATTR (RED1-3-04, High as scored, but a Claude Code hook-protocol limitation).**
The PreToolUse hook (`enforce-route.py`) receives ONLY `session_id`, `tool_name`,
`tool_input` from Claude Code — **no turn id, route id, or tool_use correlation id**
(verified against the hook's `hook_input.get(...)` sites). The pending-directive file
is therefore necessarily keyed by `session_id` and overwritten per turn. If turn N's
tool call is delivered AFTER turn N+1's directive has overwritten the pending file,
turn N's honor is credited to turn N+1's route_id.

- **Why it can't be patched here:** perfect per-route attribution requires a
  per-tool-call correlation id that Claude Code's hook API does not provide. A
  heuristic (timestamp/queue) correlation would be fragile and could mis-credit in
  the opposite direction.
- **Bounded impact:** session-level totals (realized vs overridden counts) remain
  correct — they count rows, not route_id buckets. Only the *per-route* breakdown
  ("which specific route got overridden") can misattribute, and only for rapid
  OVERLAPPING turns in one session. No spend, routing-correctness, or completion
  impact. The route_id nonce (iter-2 Q-ROUTEID) already prevents distinct decisions
  from colliding in the ledger.
- **Remediation path (upstream):** requires Claude Code to pass a stable
  per-turn/tool-use id to PreToolUse hooks; then the pending state can be a
  per-turn-keyed queue. Tracked as a known limitation, not a v1.0.1 blocker.

## GATE
Full suite: **6404 passed, 0 failed, 0 errors.** 5 order-dependent pre-existing flakes
(confirmed failing at the iter-2 GATE-green commit too, passing in full-suite order) are
not regressions. G5 will register the iteration-3 regression tests.

## Convergence status (honest)
- Findings by iteration: 12 → 6 → 9. NOT monotonically decreasing. Each round finds
  adjacent gaps in the prior round's fixes (a deeply-coupled router).
- Clean-audit counter: **0** (this round found substantive defects).
- The recurring root causes were the reservation lifecycle (now fixed at the class level
  with a single release helper) and ledger attribution (partly a hook-protocol limit).
- This is the signal workflow §14 describes. See the convergence assessment.
