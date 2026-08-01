# Iteration 5 — Implementation Report (FIX)

Fresh independent RED-1 (1 Critical + 2 High) + RED-2 (3 High + 1 Medium). All 7 findings ACCEPTED after PLAN adjudication (each reproduced; the Critical independently re-confirmed). All 7 fixed test-first.

| PLAN ID | Sev | Fix | Regression test |
|---------|-----|-----|-----------------|
| **RED1-5-01** | **Critical** | `commit()` gained `settle_pending: bool=True` across the Protocol + all 3 backends (Sqlite/Postgres/in-memory); `commit_envelope` passes `False` because `release(est)` already settled `pending_usd`. Stops the double-decrement that, on a shared envelope key, erased a concurrent sibling's reservation and admitted a 3rd caller past a hard cap (proven: 150% of a $2 cap). | `test_red1_5_01_envelope_double_release.py` (4): sibling reservation survives; 3rd caller refused; actual<est settles exactly; standalone commit still moves pending→consumed |
| **RED1-5-02** | High | Removed `route_and_call`'s redundant success-path `_pending_spend` release (dispatch already releases once at 2630/2782). This RE-APPLIES 3ea87a1's intent — the iteration-4 belief it "broke 11 tests" was disproven (the leaky *test* did). Single-release now. | covered by `test_red1_3_reservation_leaks.py` (conservation) + full-suite GATE (a leak would break budget tests) |
| **RED1-5-03** | High | `_turn_blocked = _render_mode != "echo"` — stop re-applying the `zero_claude` gate on top of the already-resolved render mode, which force-blocked an operator's explicit `CHUZOM_RENDER_MODE=echo` (bypassing Claude with an unverified draft) whenever `CHUZOM_ZERO_CLAUDE` was also set. | `test_red1_5_03_render_mode_gate.py` (7): full 6-cell matrix + the explicit-echo-under-zero-claude case |
| **RED2-5-01** | High | `uninstall()` now deletes `chuzom-statusline.sh` and removes the `statusLine` settings key when it is chuzom's (a foreign statusLine is preserved). | `test_red2_5_uninstall_cleanup.py` |
| **RED2-5-02** | High | `uninstall()`/`uninstall_claw_code()` now unlink `_SIDECAR_SCRIPTS` and strip `CHUZOM_CLAW_CODE=true` from `~/.claw-code/.env` (unrelated env lines preserved). | `test_red2_5_uninstall_cleanup.py` (3) |
| **RED2-5-03** | High | `_preflight_check` now only emits the "before starting" imperative when ZERO routing paths exist; a missing optional provider is informational; `CHUZOM_ENFORCE=hard` is a heads-up, not an "issue". | `test_red2_5_03_preflight_optional.py` (4) |
| **RED2-5-04** | Medium (core) | G6 claims guard now scans the WHOLE README with `MAGNITUDE_FORBIDDEN` (carving out only the prominently-disclaimed estimates block, and only while its disclaimer is present). Fixed the live unqualified hero claim ("3–5× Longer Sessions" → "Fewer Quota Walls"). | `test_claims_no_fabricated_magnitudes.py` (+2: full-README scan, carve-out-requires-disclaimer) |

## Notable outcome: RED1-5-02 is fixed, not deferred
The iteration-4 report deferred the in-process double-release believing a targeted patch broke 11 tests. This iteration's diagnosis (committed d80ab4b) proved that false: the 11 failures were a leaky test (un-drained bg-tasks), identical with and without the code change. With the test fixed, the correct single-release lands cleanly — so the "single-owner refactor" is no longer a prerequisite to closing this finding. The persistent-layer analogue (RED1-5-01) was the genuinely-new, higher-severity defect and is the iteration's headline fix.

## Status
7/7 accepted findings fixed, each with a data-backed regression test. Clean-audit counter: **0** (this iteration changed code). Convergence requires the NEXT fresh RED round to return clean, then one more clean round with no code change between them.
