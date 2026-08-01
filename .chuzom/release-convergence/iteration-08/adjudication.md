# Iteration 8 — PLAN Adjudication (final budgeted round)

Independent RED-1 (3 High, 2 Medium) + RED-2 (3 High). 0 Critical. Both auditors independently found the `.bak` clobber. RED-1 verified `settle()` and all reservation/envelope release paths clean. This is the 8th iteration — the workflow's budget. Clean-audit counter: **0** (never reached a clean round).

| ID | Sev | Verdict | Fix |
|----|-----|---------|-----|
| **RED1-8-01** | High | ACCEPT — fixed | Thread the already-billed cost of gate/quality-rejected attempts (`_failed_attempt_cost`) out of `_dispatch_model_loop` via a new `LLMResponse.chain_attempt_cost_usd`; settle `cost_usd + chain_attempt_cost_usd` into both `commit_envelope` and `record_consumption` (floor path subtracts its own already-counted cost to avoid double-billing). |
| **RED1-8-02** | High | ACCEPT — fixed | Backup failure is now a HARD STOP: if `_backup_before_overwrite` returns None, the overwrite is skipped and a distinct "SKIPPED … previous content preserved" message is emitted. |
| **RED1-8-03 / RED2-8-02** | Medium/High | ACCEPT — fixed | `_backup_before_overwrite` never clobbers an existing `.bak`; a second drift writes a timestamped `.<ts>.bak`, so no earlier hand-edit is lost. |
| **RED1-8-05** | Medium | ACCEPT — fixed | `drain_bg_tasks()` wired into a proper FastMCP `lifespan` shutdown hook (runs on the SAME loop as `_BG_TASKS`, which an `atexit` handler cannot). |
| **RED2-8-03** | High | ACCEPT — fixed | SessionStart banner reflects ACTUAL provider availability: `BANNER_LOCAL` when no cloud keys are set, instead of falsely claiming "API-key routing in effect". |
| **RED1-8-04** | High | ACCEPT — partial (warn) | Postgres backend has no forecast tier; `get_budget_backend()` now warns + alerts when postgres is selected under strict-forecast mode, so operators aren't silently missing a safety tier. Full forecast-tier port to Postgres is deferred (Postgres is EXPERIMENTAL). |
| **RED2-8-01** | High | ACCEPT — **DEFERRED** (structural) | `chuzom uninstall` doesn't remove `--host <codex/cursor/gemini-cli/vscode/…>` MCP registrations. This is the Nth recurrence of uninstall-completeness drift; the correct fix is a single source-of-truth registry (what `install --host` wrote → uninstall removes), NOT another per-host point-patch the next round would find incomplete. Documented as the primary structural work required for convergence. |

## Why RED2-8-01 is deferred, not patched
Point-fixing 8 host writers (surgical block-removal from `~/.codex/config.toml` TOML, `~/.gemini/settings.json`, `~/.cursor/mcp.json`, VS Code `mcp.json`, the `~/.gemini/extensions/chuzom/` dir, `.github/copilot-instructions.md`, opencode/trae) late in a very long session is exactly the incomplete, regression-prone patch that iteration-4 taught us to avoid. The recurring pattern (a new uninstall-completeness finding every round) is the signal that the install/uninstall surface needs a **manifest**: `install` records every path+block it wrote; `uninstall` consumes that manifest. That is a dedicated, carefully-tested change — correctly a follow-up, not a tail-of-session patch.
