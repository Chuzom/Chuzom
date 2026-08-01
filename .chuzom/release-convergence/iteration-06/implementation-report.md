# Iteration 6 — Implementation Report (FIX)

Independent RED-1 (2 High) + RED-2 (1 Critical, 1 High, 1 core-Medium) at `1dd7401`. Both auditors verified the iteration-5 fixes were correct in source (RED-1 could not break the envelope/`_pending_spend` fixes across all three success paths + Postgres parity; RED-2 confirmed the uninstall/preflight/claims fixes correct in repo). All 5 findings accepted and fixed test-first.

| PLAN ID | Sev | Fix | Test |
|---------|-----|-----|------|
| **RED2-6-01** | **Critical** | Hook auto-update made CONTENT-aware: `check_and_update_hooks()` re-copies when the bundled stamp is newer OR stamps match but installed bytes differ (`_files_differ`), never downgrading. Bumped the two stale stamps (session-start 17→18, auto-route 26→27, incl. its `_THIS_VERSION_LINE`). This is the delivery path for EVERY hook fix — it was version-stamp-gated, so content changes without a bump (incl. security fixes) silently never reached installed users. | `test_red2_6_01_hook_content_drift.py` (6): drift refreshes, identical is no-op, newer updates, never downgrades, rules drift + rules no-op |
| **RED2-6-03** | Medium (core) | Same content-aware self-heal for `check_and_update_rules()`. | (above, rules cases) |
| **RED2-6-02** | High | `_run_uninstall()` now calls `uninstall_claw_code()` + `uninstall_ide_configs()` (both no-op when nothing was installed; a failure in one is caught and never aborts uninstall). My iteration-5 `uninstall_claw_code()` fix existed but the CLI never called it. | `test_red2_6_02_uninstall_cli_wiring.py` (2) |
| **RED1-6-01** | High | `_chain_rows`/`_chain_keys`/`_chain` walk the parent chain TRANSITIVELY (BFS + cycle guard) in all 3 backends. Safe superset: flat parent tuples have empty grandparent links so their result is unchanged; a cap 2+ levels up (org→user→agent) is now enforced/settled. | `test_red1_6_01_transitive_chain.py` (4): org sees spend, org cap enforced 2 hops up, settle reaches org, in-memory parity |
| **RED1-6-02** | High | `_resolve_auto_render_mode` validates against `{auto,echo,block}` (case/whitespace-normalized); any unrecognized value (typo, empty, `off`) fails SAFE to `echo`, never escalating to turn-blocking. Hardens my own RED1-5-03 fix. | `test_red1_5_03_render_mode_gate.py` (+9): unrecognized→echo matrix, normalization |

## Headline: RED2-6-01 is why fixes weren't reaching users
The content-aware self-heal is the most consequential fix of the convergence effort. Before it, hook fixes only propagated on a version-stamp bump — so my iteration-5 `session-start.py`/`auto-route.py` fixes, plus historical security fixes (`_safe_sid` path-traversal, `_scrub_secrets_text`, ST-003 fail-open), were stranded on already-installed machines despite matching stamps. Installed hooks now converge to bundled on the next MCP startup regardless of stamps; the stamp bumps give immediate propagation and the content-diff makes recurrence impossible.

## Status
5/5 accepted findings fixed, each with a data-backed regression test (+28 tests). Clean-audit counter: **0** (this iteration changed code). Convergence needs the next fresh RED round clean, then one more clean round with no code change between.
