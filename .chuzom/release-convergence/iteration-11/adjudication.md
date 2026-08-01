# Iteration 11 — PLAN Adjudication

RED-1 (2 High) + RED-2 (2 Critical, 2 High) at `1986990`. Clean-audit counter: **0**. RED-1 confirmed the manifest, budget/spend, concurrency, dataclass, and render-mode areas all CLEAN — the findings are two remaining data-safety gaps (both real, both fixed).

| ID | Sev | Verdict | Fix |
|----|-----|---------|-----|
| **RED2-11-01 / RED2-11-02** | **Critical** | ACCEPT | `uninstall_ide_configs()` wholesale-`unlink()`ed the SHARED `.vscode/mcp.json` and `.windsurf/mcp.json` — destroying a user's own MCP servers (not just chuzom's) — and ran before the surgical manifest replay. Rewrote it to **surgically remove only the chuzom entry** (via `_remove_json_key`), never deleting the shared file. Only the dedicated `.cursor/rules/use-chuzom.mdc` is unlinked. Verified: user servers preserved, files intact. |
| **RED1-11-01** | High | ACCEPT | `install()` overwrote `~/.claude/rules/chuzom.md` with no backup. Now backs up before overwrite and SKIPS the overwrite if the backup fails (parity with the auto-update path). |
| **RED1-11-02** | High | ACCEPT | `install()`'s hook-copy loop called `_backup_before_overwrite` but didn't gate `copy2` on its success. Now skips the overwrite (with a distinct message) when the backup fails — never destroy a hand-edited hook with no recovery path. |
| **RED2-11-03** | High | ACCEPT | The welcome mode line (`_mode_label`) had no "local" branch — it claimed "api-keys" even with zero cloud keys, contradicting the (already-fixed) banner box. Added a `local` branch gated on `_any_cloud_key()`, aligning the mode line with the banner. |
| **RED2-11-04** | High | ACCEPT | `chuzom-install-hooks` notice claimed "Savings are guaranteed on every turn" — contradicting advise-mode ("no tool is ever blocked", "Claude keeps the final call"). Reworded to: routing is suggested on every prompt, nothing is blocked, and savings depend on the task mix — not a guarantee. |

## Note on the two Criticals
Both `uninstall_ide_configs` Criticals are a **pre-existing** wholesale-delete bug (the shared mcp.json files were always unlinked outright) — it surfaced now because RED-2 specifically tested uninstall with pre-existing *user* content in those files. The manifest already removes chuzom surgically for new installs; the enumerated `uninstall_ide_configs` path is now surgical too, closing the legacy/edge path. This is data-safety, not the recurring coverage-drift theme (which the manifest resolved).
