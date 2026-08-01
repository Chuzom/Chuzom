# Iteration 10 — PLAN Adjudication

RED-1 (2 High) + RED-2 (1 Critical, 2 High, 2 Medium) at `92367ce`. All in the newly-added manifest / recent fixes. Crucially, RED-2 **confirmed the manifest works**: same-cwd `--host all` install→uninstall is fully clean, both uninstall entry points are equivalent, and pre-existing user content is preserved through install+uninstall. The findings are edge cases of the new code. Clean-audit counter: **0**.

| ID | Sev | Verdict | Fix |
|----|-----|---------|-----|
| **RED2-10-01** | **Critical** | ACCEPT | Trae recorded a bare RELATIVE `.rules` path → a cross-cwd uninstall deleted an unrelated file and orphaned the real one. Root fix: `install_manifest.record()` stores the ABSOLUTE path (resolved at install-time cwd) — protects all 7 `_append_routing_rules` callers, not just Trae. |
| **RED1-10-01** | High | ACCEPT | `apply_uninstall`'s except handler re-crashed on a non-dict record (`rec.get` on a str), aborting the whole replay. Now guards `isinstance(rec, dict)` at loop top and the handler never re-raises. |
| **RED1-10-02** | High | ACCEPT | `created_file` removal unconditionally `unlink()`ed the whole file, destroying user-appended content. Now records the exact chuzom text and strips only that (deletes the file only if nothing else remains). |
| **RED2-10-02** | High | ACCEPT | The iter-9 `is_fallback` fix patched only 1 of 4 usage.json writers. Root fix: the banner READER now defaults `is_fallback` to `False` (missing key = success, since only the fallback path writes it explicitly) — covers all writers at once. |
| **RED2-10-03** | High | ACCEPT | `--host windsurf` was rejected despite being documented. Added `_install_windsurf_files` (project `.windsurf/mcp.json`, manifest-recorded) + `_HOST_SNIPPETS`/`_FILE_WRITERS` registration. |
| **RED2-10-05** | Medium | ACCEPT | `.codex/config.toml.chuzom-bak` created *during uninstall* survived forever (chuzom cruft after uninstall). Removed the defensive backup — the TOML regex is now `^`-anchored and regression-tested (RED1-9-02), so the backup is unneeded and violated the clean-uninstall invariant. |
| **RED2-10-04** | Medium | DOCUMENTED | Cursor troubleshooting doc references `.cursor/rules/use-chuzom.mdc` but install writes `~/.cursor/rules/chuzom.md`. Cosmetic doc/verification mismatch — the real cursor rules file IS installed and manifest-covered (uninstall works). A docs alignment, not a functional defect; noted for a docs pass. |

## Convergence signal
RED-2 confirming the manifest's core (full install→uninstall clean, user content preserved, both entry points equivalent) is the first strong "the structural fix holds" signal. Iter-10's Critical was a path-resolution edge (relative vs absolute), now fixed at the root; the rest are edges of new code. The uninstall surface — the campaign's dominant recurring theme — is now converging on the manifest.
