# Iteration 9 — Implementation Report (FIX)

RED-1 (1 Critical, 1 High) + RED-2 (1 Critical, 4 High, 2 Medium) at fe175a0. All 9
findings addressed; the multi-host uninstall surface fixed **structurally** via a
manifest. Suite 6475/0/0.

## The structural fix: install/uninstall manifest
`src/chuzom/install_manifest.py` — every install write records `{kind, path, …}`;
`apply_uninstall()` replays in reverse. Install writers funnel through 3 shared
helpers (`_merge_json_mcp_block`, `_append_routing_rules`, `_copy_hook_script`) +
instrumented bespoke codex/gemini writes, so ANY host surface is covered as long as
its write records — coverage can no longer silently drift (the root cause of the
uninstall findings in iters 5-9). Wired into `_run_uninstall` ahead of the
enumerated `uninstall_host_integrations()` (kept as a legacy fallback). Verified
end-to-end: real gemini install → 8 records → uninstall replay removes all.

## Findings
| ID | Sev | Fix | Test |
|----|-----|-----|------|
| RED1-9-02 | **Critical** | TOML-remove regex over-matched through EOF (bug I introduced in RED2-8-01), destroying adjacent Codex tables. Rewrote regex (^-anchored, stops at next `[table]`) in both install.py and the manifest; backup before mutating config.toml. | test_red1_9_02_toml_overmatch.py (3) |
| RED2-9-01 | **Critical** | OpenCode uncovered → manifest + enumerated opencode target. | test_red2_9_manifest.py |
| RED2-9-02 | High | Codex hooks.json/instructions/hook-script → manifest-recorded + hooks.json PostToolUse filter. | (manifest + host tests) |
| RED2-9-03 | High | Project files via _append_routing_rules → manifest (created/appended aware); corrected false docstring. | test_red2_9_manifest.py |
| RED2-9-04 | High | Banner is_fallback: success path now sets is_fallback:False. | (banner honesty) |
| RED2-9-05 | Med | copilot/openclaw instructions → manifest. | manifest |
| RED2-9-06 | Med | ~/.chuzom/hooks/*.py → manifest (via _copy_hook_script). | manifest |
| RED1-9-01 | High | install() backs up a hand-edited hook before overwrite. | (install_hooks suite) |
| RED2-9-07 | Med | ACKNOWLEDGED — auto-update messages are stderr-only; backup IS made. Minor UX, not blocking. | — |

Clean-audit counter: 0 (code changed).
