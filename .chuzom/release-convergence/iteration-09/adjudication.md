# Iteration 9 — PLAN Adjudication

Independent RED-1 (1 Critical, 1 High) + RED-2 (1 Critical, 4 High, 2 Medium) at `fe175a0`. This round validated the assessment's thesis: my iteration-8/RED2-8-01 per-host uninstall patch missed OpenCode entirely and several codex/project surfaces — proving point-fixes can't close the multi-host uninstall surface. **Resolution: the manifest.** Clean-audit counter: **0**.

| ID | Sev | Verdict | Fix |
|----|-----|---------|-----|
| **RED1-9-02** | **Critical** | ACCEPT — a bug I INTRODUCED in RED2-8-01 | `_remove_toml_table_block`'s regex over-matched through EOF, deleting adjacent TOML tables not blank-line-separated (destroying unrelated Codex config, no backup). Rewrote the regex (^-anchored body, stops at next `[table]`); same fix in the manifest's `_remove_toml_table`; added a backup before mutating `config.toml`. |
| **RED2-9-01** | **Critical** | ACCEPT | OpenCode fully uncovered. Fixed structurally by the **manifest** (its `_merge_json_mcp_block`/`_append_routing_rules`/`_copy_hook_script` writes now record) + added `~/.config/opencode/config.json` to the enumerated legacy fallback. |
| **RED2-9-02** | High | ACCEPT | Codex `hooks.json` PostToolUse entry + hook script + instructions survived. Instrumented the codex bespoke writes to record; added `hooks.json` PostToolUse filtering to the enumerated remover. |
| **RED2-9-03** | High | ACCEPT | Project-scoped `.github/copilot-instructions.md` + Trae `.rules` uncovered, and the docstring falsely claimed coverage. They go through `_append_routing_rules` → now manifest-recorded (created-vs-appended aware, so a user-appended file is stripped, not deleted). Corrected the false docstring. |
| **RED2-9-04** | High | ACCEPT | Banner `is_fallback` key-default bug: the SUCCESS path of `_refresh_claude_usage` omitted `is_fallback`, so `get("is_fallback", True)` defaulted True → subscribers saw the wrong banner box every session after the first. Success path now sets `is_fallback: False`. |
| **RED2-9-05** | Medium | ACCEPT | copilot/openclaw `instructions.md` survive. Covered by the manifest (`_append_routing_rules` records). |
| **RED2-9-06** | Medium | ACCEPT | `~/.chuzom/hooks/*.py` never removed short of `--purge`. Now manifest-recorded via `_copy_hook_script` → removed on uninstall replay for new installs. |
| **RED1-9-01** | High | ACCEPT | `install()` overwrote a hand-edited hook with no backup (unlike the auto-update path). Now backs up before overwrite when content differs. |
| **RED2-9-07** | Medium | ACKNOWLEDGED | Backup/skip messages from the auto-update path go to server stderr (invisible in-session). The backup IS made (data safe); this is display plumbing. `uninstall`'s own messages DO print to stdout. Left as a minor UX item, not blocking. |

## The structural fix (manifest) — why this ends the recurrence
`src/chuzom/install_manifest.py`: every install write records `{kind, path, …}`; `apply_uninstall()` replays in reverse (json_mcp, toml_table, text_block, created_file, file, dir). Because the install writers funnel through 3 shared helpers (`_merge_json_mcp_block`, `_append_routing_rules`, `_copy_hook_script`) plus a few instrumented bespoke codex/gemini writes, **any current or future host surface is covered automatically as long as its write records** — coverage can no longer silently drift. The enumerated `uninstall_host_integrations()` remains as a legacy fallback for pre-manifest installs. Verified end-to-end: a real gemini install recorded 8 artifacts; uninstall replay removed all of them and cleared the manifest.
