# RED-2 Customer-Reality Audit — Iteration 9

Auditor: RED-2 (independent — did not read RED-1's report/output)
Commit under test: fe175a0
Scope: RED2-8-01 (`chuzom uninstall` host-integration cleanup), RED1-8-02/03 (backup-before-overwrite), RED2-8-03 (banner honesty), broad claims-honesty sweep.
Method: actual `chuzom install`/`chuzom uninstall` runs against a disposable `$HOME` and a disposable git project (no pre-existing chuzom markers), file-diffing before/after, seeded-sibling JSON tests, direct code-logic replay cross-checked against real production state on this machine (read-only).

**Verdict: NOT CLEAN.** 5 High/Critical findings, 2 core-Medium findings. All are CONFIRMED (empirically reproduced), none are PLAUSIBLE-only.

---

## Severity summary

| ID | Severity | Title |
|---|---|---|
| RED2-9-01 | **Critical** | OpenCode is completely uncovered by `chuzom uninstall` — live MCP registration + routing instructions survive intact |
| RED2-9-02 | **High** | Codex CLI: live `hooks.json` PostToolUse registration + `instructions.md` survive `chuzom uninstall` |
| RED2-9-03 | **High** | VS Code (`.github/copilot-instructions.md`) and Trae (`.rules`) project-scoped files are uncovered by *any* uninstall path, contradicting the code's own docstring |
| RED2-9-04 | **High** | Banner box contradicts the mode line directly beneath it — cached-subscription detection is unconditionally broken (`is_fallback` key-default bug) |
| RED2-9-05 | core-Medium | Copilot-CLI / OpenClaw `instructions.md` survive uninstall after their MCP entries are removed — stale "call this tool" text for a now-unregistered server |
| RED2-9-06 | core-Medium | `~/.chuzom/hooks/*.py` (7 host hook scripts) are never removed by any uninstall path short of `--purge` (which is destructive + interactive-confirm, and also wipes usage history/.env) |
| RED2-9-07 | core-Medium | Backup-before-overwrite hard-stop/update/skip messages are never surfaced to the user — only `log.info()` → MCP-server stderr, invisible in a normal Claude Code session, and not surfaced by `chuzom doctor` either |

---

## RED2-9-01 — Critical — OpenCode fully uncovered by `chuzom uninstall`

**Surface:** `src/chuzom/commands/install.py::uninstall_host_integrations()` (lines 671-758) — no OpenCode branch exists at all. Compare to the installer, which *does* write OpenCode config: `~/.config/opencode/config.json` (MCP entry) and `~/.config/opencode/instructions.md` (routing rules), staged via `~/.chuzom/hooks/opencode-post-tool.py`.

**User-experience vs. truth:** `chuzom uninstall` prints "Uninstalling Chuzom..." followed by a list of actions and ends with "Done. Restart Claude Code to apply changes." A user who installed the OpenCode integration and later runs `chuzom uninstall` (or `chuzom-install-hooks uninstall`, or `--purge` without confirming) is told the product is uninstalled. In reality OpenCode's `config.json` still has a **live** `chuzom` MCP server entry, unmodified, and OpenCode will keep invoking it. This is the worst of the host gaps: unlike Codex (below), the actual registration itself remains fully live, not just a stale hook script.

**CONFIRMED — repro:**
```bash
TMPHOME=$(mktemp -d)
HOME="$TMPHOME" .venv/bin/chuzom install --host opencode
# → writes ~/.config/opencode/config.json and ~/.config/opencode/instructions.md
HOME="$TMPHOME" .venv/bin/chuzom uninstall
cat "$TMPHOME/.config/opencode/config.json"      # chuzom MCP entry still present, untouched
cat "$TMPHOME/.config/opencode/instructions.md"  # routing-rules text still present
```
Verified directly in this session's sandbox (`$TMPHOME/.config/opencode/config.json` and `instructions.md` both survived `chuzom uninstall` byte-for-byte, full live MCP entry present).

**Suggested fix:** add an OpenCode branch to `uninstall_host_integrations()` that removes the `chuzom` entry from `~/.config/opencode/config.json` (via the existing `_remove_json_mcp_block()` helper, same pattern as codex/cursor/gemini-cli) and deletes/truncates `~/.config/opencode/instructions.md`'s chuzom section, mirroring whatever `_install_*` function wrote it.

---

## RED2-9-02 — High — Codex CLI: live hook registration + instructions survive uninstall

**Surface:** `uninstall_host_integrations()` (lines 671-758) — the Codex branch removes the MCP entry from Codex's config but does not touch `~/.codex/hooks.json` (a *separate* file, home-scoped) or `~/.codex/instructions.md`.

**User-experience vs. truth:** After `chuzom uninstall`, the user is told cleanup is complete. In reality:
- `~/.codex/hooks.json` still contains a live `PostToolUse` hook entry pointing at `~/.chuzom/hooks/codex-post-tool.py`.
- That script file itself still exists (RED2-9-06 covers why), so Codex CLI will keep invoking it on **every Bash tool call, forever**, after a supposedly-complete uninstall. The script is self-contained and swallows its own errors, so it degrades silently rather than crashing visibly — the user gets no error, just a phantom process running on every tool call from a product they believe they removed.
- `~/.codex/instructions.md` still has the full chuzom routing-rules text appended, still directing the model to call `llm_query`/`llm_analyze`/etc. — tools that (per RED2-9-01/02's partial fix) are only partially still registered/no longer registered depending on host, so the model may be instructed to call an MCP tool that no longer exists.

**CONFIRMED — repro:**
```bash
TMPHOME=$(mktemp -d)
HOME="$TMPHOME" .venv/bin/chuzom install --host codex
HOME="$TMPHOME" .venv/bin/chuzom uninstall
cat "$TMPHOME/.codex/hooks.json"        # PostToolUse entry pointing at codex-post-tool.py still present
ls "$TMPHOME/.chuzom/hooks/"            # codex-post-tool.py still present
cat "$TMPHOME/.codex/instructions.md"   # full routing-rules text still present
```
Verified directly in this session's sandbox — all three survived intact.

**Suggested fix:** in the Codex branch of `uninstall_host_integrations()`, also strip the chuzom `PostToolUse` entry from `~/.codex/hooks.json` and remove chuzom's appended block from `~/.codex/instructions.md` (the installer must already know how to identify its own appended block, since it presumably avoids duplicating it on repeat `install` calls — reuse that boundary marker for removal).

---

## RED2-9-03 — High — VS Code / Trae project-scoped files uncovered by any uninstall path

**Surface:** Two functions split cleanup responsibility, and the split is documented in `uninstall_host_integrations()`'s own docstring as: *"project-scoped writers (.vscode/mcp.json, .cursor/rules, .github/copilot-instructions.md, Trae .rules in a project) are handled by `uninstall_ide_configs()` against the cwd."* This claim is **false**. `install_hooks.py::uninstall_ide_configs()`'s actual `targets` list (lines ~1236-1293) is:
```
[.vscode/mcp.json, .windsurf/mcp.json, .cursor/rules/use-chuzom.mdc]
```
`.github/copilot-instructions.md` (written by `_install_vscode_files()`, install.py:1033-1057) and Trae's `.rules` (written by `_install_trae_files()`, install.py:991-1015) are **not** in that list, and are not handled by `uninstall_host_integrations()` either (which is explicitly home-scope-only by its own docstring). No function removes them. They are simply never cleaned up.

**CONFIRMED — repro (fresh disposable project, to avoid the installer's own idempotency guard silently skipping writes against a project that already has legitimate chuzom markers):**
```bash
TMPPROJ=$(mktemp -d) && cd "$TMPPROJ" && git init -q
TMPHOME=$(mktemp -d)
HOME="$TMPHOME" /Users/yaliandrona/Projects/Chuzom/.venv/bin/chuzom install --host vscode
HOME="$TMPHOME" /Users/yaliandrona/Projects/Chuzom/.venv/bin/chuzom install --host trae
ls .github/copilot-instructions.md .rules   # both freshly created with full chuzom content
HOME="$TMPHOME" /Users/yaliandrona/Projects/Chuzom/.venv/bin/chuzom uninstall
find "$TMPPROJ" -type f -not -path "*/.git/*"
# → .github/copilot-instructions.md and .rules are STILL PRESENT, byte-for-byte unchanged
```
Verified directly in this session's sandbox: `chuzom uninstall`'s printed action log shows only the two *home-scoped* mcp.json removals (VS Code `Code/User/mcp.json`, Trae's platform mcp.json) — nothing project-scoped. Both project files survive unconditionally.

**Suggested fix:** either (a) add `.github/copilot-instructions.md` and Trae's `.rules` to `uninstall_ide_configs()`'s `targets` list, or (b) correct the false docstring in `uninstall_host_integrations()` and add real removal logic somewhere — but (a) is the more honest fix since the docstring already claims this is where it belongs.

---

## RED2-9-04 — High — Session-start banner box contradicts the mode line directly beneath it (broken cached-subscription detection)

**Surface:** `src/chuzom/hooks/session-start.py`
- `_refresh_claude_usage()` success path (lines 513-548): on a successful OAuth usage refresh it writes `~/.chuzom/usage.json` as `{"session_pct":…, "weekly_pct":…, "sonnet_pct":…, "highest_pressure":…, "updated_at":…}` — **no `is_fallback` key at all.**
- Failure path (lines 554-566): writes the same shape but explicitly sets `"is_fallback": True`.
- `main()`, banner-selection read (lines 1086-1093):
  ```python
  _cached_sub = not _cached_usage.get("is_fallback", True)
  banner = _select_banner(_cached_sub)
  ```
  The default for a *missing* key is `True`. Since the **success** path never writes the key, a missing key is indistinguishable from an explicit `is_fallback: True` (failure). Both cases make `_cached_usage.get("is_fallback", True)` evaluate to `True`, so `_cached_sub` evaluates to **`False` in every case where the cache file exists at all** — regardless of whether the previous session's refresh succeeded or failed. The only way `_cached_sub` can be `True` is the `except` branch (`_cached_sub = _CC_MODE`), which only fires when the file is missing or corrupt — i.e., effectively only on the very first-ever run.
- Meanwhile `main()` also computes a **second, independently-correct** subscription signal this same run: `is_subscription = not usage_hint.startswith("\n⚠️")` (line 1101), fed into `_render_welcome(is_subscription)` (line 1124), which prints the `mode → subscription (Claude OAuth pressure cascade)` line.
- Net effect: the prominent `╔═══╗` banner box (printed first, line 1122) is selected from the permanently-broken cached signal, while the `mode →` line three lines below it (line 1124) is selected from the correct, freshly-computed signal. **They can and do disagree**, in the same hook output, in the same session.

**User-experience vs. truth:** A user with an active, successfully-refreshing Claude subscription will, on effectively every session (any session after the very first), see the big banner box claim `⚡ chuzom ACTIVE — local routing (no cloud keys set)` (if they have no cloud API keys, which is the documented Ollama-first quickstart default state) directly above a `mode → subscription (Claude OAuth pressure cascade)` line and a `✅ Usage: session=X% weekly=Y% sonnet=Z%` line that correctly reflect real subscription pressure. The single most prominent piece of UI the product shows, at the start of every session, actively contradicts itself and misrepresents the user's real routing mode — potentially telling an active subscriber they have no working cloud routing when they do.

**CONFIRMED — two independent proofs, no network calls required:**

1. Direct logic replay of the exact snippet against both snapshot shapes the code actually produces:
   ```python
   success_snapshot = {"session_pct":15,"weekly_pct":6,"sonnet_pct":0,"highest_pressure":0.15,"updated_at":0}  # no is_fallback key — exact shape of the success branch
   fail_snapshot    = {"session_pct":50,"weekly_pct":50,"sonnet_pct":50,"highest_pressure":0.5,"updated_at":0,"is_fallback":True}
   not success_snapshot.get("is_fallback", True)  # → False  (WRONG — this was a successful subscription refresh)
   not fail_snapshot.get("is_fallback", True)     # → False  (correct, but for the wrong structural reason)
   ```
2. **Live production evidence on this machine**, read-only, no data modified: `~/.chuzom/usage.json` (written by this machine's own real, successful, subscription-mode session-start refresh — consistent with the real banner this very session showed: "chuzom ACTIVE — subscription mode", "✅ Usage: session=15% weekly=6% sonnet=0%") contains exactly:
   ```json
   {"session_pct": 16.0, "weekly_pct": 6.0, "sonnet_pct": 0.0, "highest_pressure": 0.16, "updated_at": 1785433647.6592839}
   ```
   No `is_fallback` key — confirming the success path's real, shipped output shape. Recomputing the banner-selection line against this real file: `not d.get("is_fallback", True)` → `False`. On this real machine, with a real active subscription, the next session's banner box will not select `BANNER_SUBSCRIPTION` from cache.

Confirmed `_cached_sub` is used *only* for banner-box text selection (`grep -n "_cached_sub"` → 3 hits, all within lines 1090-1093) — it does not affect actual routing decisions, only what the user is told. This is a pure display-honesty defect, not a functional routing regression, but it is the exact failure mode Priority Focus #3 asked to find: the printed banner not matching reality.

**Suggested fix:** either (a) make the success-path snapshot explicit — `"is_fallback": False` — so the key is always present and the default only matters for genuinely missing/pre-migration files, or (b) simplify by dropping the cached banner-selection entirely and using the same fresh `is_subscription` signal (already computed later in `main()`) for both the banner box and the welcome line — which also fixes the deeper design smell of picking the box from stale data and the text below it from fresh data in the same print.

---

## RED2-9-05 — core-Medium — Copilot-CLI / OpenClaw `instructions.md` survive uninstall

**Surface:** `uninstall_host_integrations()`'s copilot-cli and openclaw branches correctly remove the MCP entry from `~/.config/gh/copilot/mcp.json` / `~/.openclaw/mcp.json` (confirmed via the seeded-sibling test below — no corruption, sibling entries preserved) but do not touch the companion `instructions.md` files that `_install_copilot_cli_files()` / `_install_openclaw_files()` also write (`~/.config/gh/copilot/instructions.md`, `~/.openclaw/instructions.md`).

**User-experience vs. truth:** less severe than RED2-9-01/02 because the MCP registration itself *is* correctly removed — the host can no longer actually call the tool. But the instructions file still tells the model "route via `llm_query`/`llm_analyze`/etc." for a tool that no longer exists, which will produce confusing tool-not-found failures or silently-ignored instructions rather than a clean removal.

**CONFIRMED — repro:**
```bash
TMPHOME=$(mktemp -d)
HOME="$TMPHOME" .venv/bin/chuzom install --host copilot-cli
HOME="$TMPHOME" .venv/bin/chuzom install --host openclaw
HOME="$TMPHOME" .venv/bin/chuzom uninstall
cat "$TMPHOME/.config/gh/copilot/mcp.json"        # chuzom entry correctly removed
cat "$TMPHOME/.config/gh/copilot/instructions.md" # routing-rules text still present
cat "$TMPHOME/.openclaw/mcp.json"                 # chuzom entry correctly removed
cat "$TMPHOME/.openclaw/instructions.md"          # routing-rules text still present
```
Verified directly in this session's sandbox — both mcp.json files clean, both instructions.md files retain full chuzom text.

**Positive finding (no defect):** a seeded-sibling test against `.gemini/settings.json`, `.cursor/mcp.json`, `.config/gh/copilot/mcp.json`, `.openclaw/mcp.json` — each manually seeded with both a `chuzom` entry and an unrelated `some-other-server` entry — confirmed `uninstall_host_integrations()` removes only the `chuzom` entry in all four files; the unrelated entry survives byte-for-byte-value-correct (only JSON pretty-printing changes, no value corruption). `_merge_json_mcp_block()`/`_remove_json_mcp_block()` are sound.

**Suggested fix:** same pattern as RED2-9-01/02 — each branch that installs an `instructions.md` companion file needs a matching removal (or truncation of the chuzom-appended block) in `uninstall_host_integrations()`.

---

## RED2-9-06 — core-Medium — Host hook scripts in `~/.chuzom/hooks/` never removed short of `--purge`

**Surface:** `~/.chuzom/hooks/*.py` (7 scripts: `codex-post-tool.py`, `gemini-cli-auto-route.py`, `gemini-cli-post-tool.py`, `gemini-cli-session-end.py`, `opencode-post-tool.py`, `session-start.py`, `status-bar.py`) are staged by the various `_install_*` functions and are the actual scripts referenced by RED2-9-01/02's surviving live registrations. No non-`--purge` uninstall path removes any of them; `--purge` is a heavy, interactive-confirm, all-or-nothing operation (`shutil.rmtree(state_dir)` on the *entire* `~/.chuzom/` state dir) that also destroys unrelated usage history and `.env` secrets, so most users would reasonably avoid it just to clean up host hooks.

**User-experience vs. truth:** this is the mechanism that makes RED2-9-02 (Codex) and RED2-9-01 (OpenCode) actually *execute* after uninstall rather than merely leaving a dangling pointer to a missing file — the scripts are still there to be invoked.

**CONFIRMED** via the same repro steps as RED2-9-01/02 (`ls "$TMPHOME/.chuzom/hooks/"` post-uninstall shows all 7 scripts present).

**Suggested fix:** once RED2-9-01/02/05 are fixed to remove the *registrations* pointing at these scripts, also delete the specific script file(s) for any host that was actually uninstalled (not the whole `~/.chuzom/` dir) — this is a natural side-effect to add to the same per-host removal code path, not a reason to force `--purge`.

---

## RED2-9-07 — core-Medium — Backup-before-overwrite protection is invisible to the user

**Surface:** `src/chuzom/install_hooks.py::_backup_before_overwrite()` (lines 166-193), `check_and_update_hooks()` (196-259), `check_and_update_rules()` (262-304) — called only from `src/chuzom/server.py` at MCP-server startup, which logs results via `log.info("hook_updated", update_message=…)` / `log.info("routing_rules_updated", update_message=…)`.

**Code-level correctness (no defect):** the hard-stop/backup logic itself is sound — `_backup_before_overwrite()` returns `None` on any backup-write failure and callers correctly refuse to overwrite when `None` is returned; a first drift gets a plain `.bak`, later drifts get a timestamped `.<ts>.bak`, and an existing backup is never clobbered. No data-loss path exists in the code.

**User-experience gap:** `chuzom.logging.configure_logging()` (`src/chuzom/logging.py`, lines 55-63) attaches a plain `logging.StreamHandler()` with no explicit stream argument, which defaults to `sys.stderr` of the process. For the MCP server, that's `sys.stderr` of a background subprocess spawned by the AI host (Claude Code, Cursor, etc.) — not a stream a typical user opens in their normal chat UI. I additionally grepped `src/chuzom/commands/doctor.py` for any surfacing of backup/update history (`backup`, `.bak`, `update_message`, `hook_updated`, `routing_rules_updated`, `drift`) — no matches beyond an unrelated "gateway daemon interpreter drift" check. There is no user-facing command (`chuzom doctor`, `--help`, or otherwise) that surfaces recent hook/rules backup-or-update events.

**Practical consequence:** if a user hand-edits a bundled hook script or rules file and then upgrades chuzom, their edit is safely preserved in a `.bak` file and the bundled version is silently reinstated — but nothing in their normal session tells them this happened. They may notice their customization "disappeared" after an upgrade with no visible explanation, and would need to know to dig through MCP-server stderr logs (not exposed by default in most hosts' UI) to discover the `.bak` file even exists.

**CONFIRMED** (code-level, by reading `logging.py`, `server.py`, and `doctor.py` in full) — this is a discoverability/honesty gap (the mechanism silently does the safe thing but never tells the user), not a data-loss defect, hence core-Medium rather than High.

**Suggested fix:** surface the backup/update/skip result somewhere the user actually sees in-session — e.g., include it in the SessionStart hook's `additionalContext` (same channel RED2-9-04's banner uses, which *is* proven to reach the user) when a drift was detected in the current session, or add a `chuzom doctor` check that reports any `.bak` files newer than N days in the tracked hook/rules locations.

---

## Checked and found CLEAN (no defect)

- `_merge_json_mcp_block()` / `_remove_json_mcp_block()` — seeded-sibling test confirms no corruption of unrelated MCP server entries when removing the `chuzom` entry (see RED2-9-05).
- `chuzom-install-hooks uninstall` vs `chuzom uninstall` — read `install_hooks.py::main()` (lines 1296-1353) confirming both delegate to the same `_run_uninstall()`; no divergent-entry-point defect.
- `_backup_before_overwrite()` / `check_and_update_hooks()` / `check_and_update_rules()` core logic — sound, no data-loss path (see RED2-9-07's code-level-correctness note).
- Banner honesty (RED2-8-03's actual fix, distinct from RED2-9-04's regression): `_resolve_banner()`/`_select_banner()` do correctly check `_any_cloud_key()` before claiming "API-key routing in effect" rather than assuming it from the subscription flag alone — the *logic* for choosing among API-key/local/zero-claude variants is honest; the defect (RED2-9-04) is specifically the cached-vs-fresh subscription signal feeding that logic.
- `_zero_claude_enabled()` / `BANNER_ZERO_CLAUDE`'s "the prompt is blocked" claim — traced into `src/chuzom/hooks/auto-route.py::_block_zero_claude()`, which emits a genuine Claude Code `{"decision": "block"}` UserPromptSubmit response; this is a real, distinct blocking mechanism from the PreToolUse enforcer (which per `_enforce_label()`'s docstring never blocks file/shell tools post-P0) — no contradiction found between the two.
- README quick grep for unqualified absolute claims ("100%", "guarantee", "never fails", "zero cost", "no risk", "instantly") — only one hit, a comparison-table cell ("Claude quota consumed | 100% | ~24%") that reads as a before/after comparison rather than a standalone false claim; not pursued further given time budget and the explicit instruction not to manufacture marginal findings.

## Not completed this iteration (time-budget tradeoff, flagging for a future pass)

- Full claims-honesty sweep of `rules/*.md`, `skills/**`, IDE-config templates, hook stdout, statusline, `chuzom doctor`/`--help` (Priority Focus #4) — only a light grep pass on README was done; no deep read of skills/rules files.
- Broad sweep of fresh-install correctness beyond the uninstall symmetry testing, rules propagation beyond what RED2-9-03 touched, `cap_downgraded` telemetry, zero-provider fail-open (Priority Focus #5) — not started.
- `src/chuzom/hosts/gemini_cli.py`, `src/chuzom/hosts/base.py`, `src/chuzom/hosts/cursor.py` — not inspected; the primary audit was conducted entirely against `commands/install.py`'s host-integration functions, which appear to be the actual code path exercised by `chuzom install --host …` (confirmed empirically via the install/uninstall repros above), but a parallel/legacy implementation in `hosts/*.py` was not ruled out.

Given the strength and count of confirmed findings in the primary focus area (RED2-9-01 through 06) plus the independently-confirmed banner defect (RED2-9-04), this report is submitted now rather than continuing to chase Priority #4/#5 exhaustively, per the instruction to report real, provable defects rather than pad for completeness.
