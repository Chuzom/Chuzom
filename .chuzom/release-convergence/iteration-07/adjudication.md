# Iteration 7 — PLAN Adjudication

Independent RED-1 (2 High) + RED-2 (2 High). **0 Critical** — severity dropped from iter5/iter6 (each had a Critical). RED-1 verified the iter-6 transitive-chain fix fully clean (cycle guard, diamond no-double-count, mid-chain atomic rollback all repro'd on both production backends) and all `_pending_spend`/envelope release paths clean. Clean-audit counter: **0**.

| ID | Sev | Verdict | Reproduced | Fix |
|----|-----|---------|-----------|-----|
| **RED1-7-01** | High | ACCEPT | Repro: $1 cap → $1.98 exposure via the release→commit gap | Add an atomic `settle(key, est, actual)` to the backend Protocol + all 3 impls (pending−=est and consumed+=actual in ONE transaction/lock-hold). `commit_envelope` calls `settle()` instead of `release()`+`commit()`, closing the concurrent-admit window. `release`/`commit` stay for their other callers. |
| **RED1-7-02** | High | ACCEPT | Repro: user edit to a hook + chuzom.md destroyed on next startup | My own iter-6 content-aware overwrite. Resolve the "silent + permanent" harm: **back up** the existing file (`.bak`) before any content-drift/version overwrite and return a clear message naming the backup; fix the stale docstring that still claims "only overwritten when the bundled version is newer." Propagation (RED2-6-01) is preserved — drift still refreshes, but recoverably and visibly. |
| **RED2-7-01** | High | ACCEPT | E2E: `chuzom-install-hooks uninstall` leaves full claw-code + IDE install | `install_hooks.main()`'s uninstall branch delegates to `commands.uninstall._run_uninstall` so the two entry points can't drift again; add a test covering this entry point. |
| **RED2-7-02** | High | ACCEPT | Injected prose claim in the disclaimed block passed the guard | Narrow the README carve-out: exempt only the disclaimed **table-data rows** (`|`-lines) within the section, never free prose. Add a regression test asserting an injected prose claim in that block IS caught. (Not live today — a mechanism hardening.) |

## Convergence signal
Severity trajectory: iter5 (1C+2H) → iter6 (1C+2H+1M) → iter7 (0C+4H). The two Criticals were genuinely new subsystem defects (envelope double-decrement; stale-hook delivery). Iter7's findings are all refinements of already-touched areas (envelope atomicity, my own update-fix's side effect, a sibling uninstall entry point, a guard-scoping weakness). This is the expected shape approaching convergence — but it is NOT clean, so the counter stays 0.

## Fix order (test-first, GATE after)
1. RED1-7-01 atomic settle (budget correctness).
2. RED1-7-02 backup-before-overwrite + docstring.
3. RED2-7-01 uninstall entry-point delegation.
4. RED2-7-02 carve-out narrowing + test.
Then full-suite GATE.
