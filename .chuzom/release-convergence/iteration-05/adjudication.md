# Iteration 5 — PLAN Adjudication

Both RED auditors ran independently at `d80ab4b`. NOT a clean round: 1 Critical, 5 High, 1 core-Medium. Every finding reproduced (RED authors provided scripts; I independently re-confirmed the Critical). Clean-audit counter: **0**.

| ID | Sev | Verdict | Reproduced | Fix |
|----|-----|---------|-----------|-----|
| RED1-5-01 | **Critical** | ACCEPT | Yes — independent repro: after A settles, `pending=0.00` (should be 1.00, B outstanding); C admitted past a $2 cap | `commit()` gains `settle_pending: bool=True`; `commit_envelope` passes `False` (release already settled pending). Fixes all 3 backends. Regression test with 2 concurrent reservations sharing a key. |
| RED1-5-02 | High | ACCEPT | Yes (RED-1) — in-process analogue | RE-APPLY 3ea87a1's intent: remove `route_and_call`'s redundant success-path `_pending_spend` release (dispatch already releases at 2630/2782). The earlier "11-test breakage" was proven to be the leaky TEST, not this code change — so it is now safe. Full-suite GATE confirms. |
| RED1-5-03 | High | ACCEPT | Yes (RED-1) — logic repro | `_turn_blocked = _render_mode != "echo"` (drop the redundant re-application of `zero_claude`; `_resolve_auto_render_mode` already applied it). Regression test over the 6 (render_mode, zero_claude) cells. |
| RED2-5-01 | High | ACCEPT | Yes (RED-2) — source read | `uninstall()` deletes `chuzom-statusline.sh` + removes the `statusLine` settings key when it matches the chuzom command. |
| RED2-5-02 | High | ACCEPT | Yes (RED-2) — source read | `uninstall()`/`uninstall_claw_code()` unlink `_SIDECAR_SCRIPTS` and strip `CHUZOM_CLAW_CODE=true` from `~/.claw-code/.env`. |
| RED2-5-03 | High | ACCEPT | Yes — I saw this banner live this session ("GEMINI_API_KEY missing — Fix before starting") | Only emit the "Fix before starting" imperative when ZERO routing paths exist (no cloud key AND no reachable Ollama AND not Claude-subscription). Otherwise informational, non-imperative. `CHUZOM_ENFORCE=hard` moves out of the "issue" bucket. |
| RED2-5-04 | Medium (core — claims honesty is the G6 gate's purpose) | ACCEPT | Yes (RED-2) — README lines 141, 209-210 ship unguarded | Extend the G6 guard to scan whole `README.md` with `MAGNITUDE_FORBIDDEN`; hedge/remove the live unqualified multiplier claims it flags. |

## Notes on RED1-5-02 (the deferred item)
RED-1 correctly re-confirms the in-process `_pending_spend` double-release. It was deferred in iteration-4 under the belief a targeted patch "broke 11 tests." That belief was **disproven** this iteration: bisection showed the 11 failures came from a leaky *test* (un-drained bg-tasks), not from 3ea87a1's code change (identical failures with/without it). With the test fixed, removing the redundant success-path release is safe and is the correct single-release. So RED1-5-02 is fixed now, not deferred — the single-owner refactor is no longer required to close it (the success path already releases exactly once inside `_dispatch_model_loop`).

## Fix order (test-first, GATE after each cluster)
1. RED1-5-01 envelope double-decrement (Critical) — budget correctness.
2. RED1-5-02 in-process release (re-remove redundant release).
3. RED1-5-03 render-mode gate.
4. RED2-5-01/02 uninstall cleanup.
5. RED2-5-03 pre-flight banner honesty.
6. RED2-5-04 claims guard + README hedging.
Then full-suite GATE. If green with no unresolved Critical/High/core-Medium → this counts as a FIX round; the next fresh RED round must come back clean twice consecutively to converge.
