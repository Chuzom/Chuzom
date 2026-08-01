# Iteration 6 — PLAN Adjudication

Independent RED-1 (2 High) + RED-2 (1 Critical, 1 High, 1 core-Medium) at `1dd7401`. NOT clean. Both auditors verified the iteration-5 fixes are correct in source — RED-1 could not break the envelope/`_pending_spend` fixes; RED-2 confirmed the uninstall/preflight/claims fixes are correct in repo. Clean-audit counter: **0**.

| ID | Sev | Verdict | Reproduced | Fix |
|----|-----|---------|-----------|-----|
| **RED2-6-01** | **Critical** | ACCEPT | Live on auditor's real `~/.claude` (v17==17, v26==26 but content differs; `check_and_update_hooks()` → `[]`) | Make hook auto-update **content-aware**: re-copy when `src_v > dst_v` OR (`src_v == dst_v` AND installed bytes differ from bundled). Bump the two stale stamps (session-start 17→18, auto-route 26→27) so the fix propagates immediately. Add a content-hash CI guard. |
| **RED2-6-02** | High | ACCEPT | Live tmp-HOME: 16 chuzom files survive `chuzom uninstall` under `.claw-code` | `_run_uninstall()` calls `uninstall_claw_code()` + `uninstall_ide_configs()` (my iteration-5 `uninstall_claw_code()` fix was never reached — the CLI never called it). |
| **RED2-6-03** | Medium (core) | ACCEPT | Same class as 6-01, currently latent | `check_and_update_rules()` gets the same content-aware self-heal; the CI guard covers rules too. |
| **RED1-6-01** | High | ACCEPT | RED-1 repro: org cap 2 hops up never sees spend | Make `_chain_rows`/`_chain_keys`/`_chain` walk the parent chain **transitively** (BFS with a visited cycle-guard) in all 3 backends. Safe superset: flat parent tuples already have empty grandparent links, so their result is unchanged. |
| **RED1-6-02** | High | ACCEPT | RED-1 repro: `eco`/empty/`off` → turn_blocked=True | Validate `_render_mode` against `{echo, block}` after resolving `auto`; any unrecognized value fails **safe to `echo`** (advisory), not to block. Hardens my own RED1-5-03 fix. |

## Cross-cutting insight (RED2-6-01)
This is the most important finding of the convergence effort: it means every hook fix we shipped (and historical security fixes: `_safe_sid` path-traversal, `_scrub_secrets_text`, the ST-003 fail-open wrapper) never reached already-installed users because their version stamps weren't bumped on content change. The content-aware self-heal fixes this permanently — installed hooks converge to bundled on the next MCP startup regardless of stamps — and the CI guard stops silent drift recurring.

## Fix order (test-first, GATE after)
1. RED2-6-01 content-aware hook update + stamp bumps (Critical).
2. RED2-6-03 content-aware rules update + shared CI content-hash guard.
3. RED2-6-02 uninstall CLI wiring.
4. RED1-6-01 transitive chain (3 backends).
5. RED1-6-02 render-mode allow-list.
Then full-suite GATE.
