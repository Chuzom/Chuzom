# Iteration 7 — Implementation Report (FIX)

Independent RED-1 (2 High) + RED-2 (2 High). **0 Critical** — first round with no Critical. RED-1 verified the iter-6 transitive-chain fix fully clean and all reservation/envelope release paths clean. All 4 findings fixed test-first.

| PLAN ID | Sev | Fix | Test |
|---------|-----|-----|------|
| **RED1-7-01** | High | Added atomic `settle(key, est, actual)` to the backend Protocol + all 3 impls (pending−=est and consumed+=actual in ONE transaction/lock-hold). `commit_envelope` calls `settle()` instead of `release()`+`commit()`, closing the concurrent-admit window (repro'd $1→$1.98 cap breach). Legacy backends without `settle` fall back to the two-step path. | `test_red1_7_01_settle_atomic.py` (5): settle accounting, sibling preserved, single-settle spy, in-memory parity, legacy fallback |
| **RED1-7-02** | High | Content-aware overwrite now **backs up** the existing file to `<name>.bak` before any drift/version overwrite and names the backup in the message — a hand-edited managed hook/rules file is no longer silently or permanently destroyed. Propagation (RED2-6-01) preserved. Fixed the stale docstring. | `test_red2_6_01_hook_content_drift.py` (+2): hook backup, rules backup |
| **RED2-7-01** | High | `install_hooks.main()`'s uninstall branch delegates to `commands.uninstall._run_uninstall` (which calls all three removers), so `chuzom-install-hooks uninstall` — the frozen entry point the tool directs users to — can no longer drift from `chuzom uninstall`. | `test_red2_6_02_uninstall_cli_wiring.py` (+1): main() delegates + forwards flags |
| **RED2-7-02** | High | README claims carve-out narrowed to exempt only the disclaimed **table-data rows** (`|`-lines), never prose. Extracted a pure `_scannable_from_lines` helper for testability. | `test_claims_no_fabricated_magnitudes.py` (+1): injected prose claim in the disclaimed block IS caught; table figure stays exempt |

## Convergence signal
iter5 (1C+2H) → iter6 (1C+2H+1M) → **iter7 (0C+4H)**. All iter7 findings are refinements of already-touched subsystems (envelope atomicity, my own iter-6 update fix's side effect, a sibling uninstall entry point, a guard-scoping weakness) — not new subsystem defects. RED-1 explicitly could not break the iter-6 transitive-chain fix (cycle guard, diamond, rollback all clean) or any `_pending_spend`/envelope release path. Trajectory is consistent with approaching convergence.

## Status
4/4 accepted findings fixed, each with a data-backed regression test. Clean-audit counter: **0** (this iteration changed code). Convergence needs the next fresh RED round clean, then a second clean round with no code change between.
