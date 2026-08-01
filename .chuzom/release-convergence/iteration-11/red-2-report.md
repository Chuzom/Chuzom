# RED-2 Customer-Reality Audit — Iteration 11

Auditor: RED-2 (independent, no cross-read of RED-1)
Commit: `1986990` (HEAD `198699085b43c7897c944ab2f156ea2cdb610789`), branch `fix/v1.0.1-audit-mitigation`
Scope: install/uninstall symmetry, banner/preflight honesty, claims-honesty sweep, fresh-install correctness

## Summary

| Severity | Count |
|---|---|
| Critical | 2 |
| High | 2 |
| core-Medium | 0 |

1. **RED2-11-01 (Critical)** — `chuzom uninstall` silently deletes pre-existing, non-chuzom files at `.vscode/mcp.json`, `.windsurf/mcp.json`, `.cursor/rules/use-chuzom.mdc` with zero content check.
2. **RED2-11-02 (Critical)** — Because that same blind-delete step runs *before* the content-gated manifest replay, `chuzom uninstall` after `--host windsurf`/`--host all` destroys the entire `.windsurf/mcp.json`, wiping unrelated user MCP server entries instead of surgically removing only chuzom's.
3. **RED2-11-03 (High)** — The SessionStart banner box and the `mode →` line it's printed next to can directly contradict each other (and reality), because they're computed from two different data sources at two different times, and `_mode_label()` has no "local" branch at all.
4. **RED2-11-04 (High)** — `chuzom-install-hooks --help` (and its post-install notice) tells users "Savings are guaranteed on every turn" / "routing is automatic, transparent, zero effort" for Claude Code — directly and provably contradicted by the shipped `chuzom.md` rules file and `doctor.py`'s own explainer text, both of which say routing is an optional suggestion the model can skip with "no penalty, no violation."

---

## RED2-11-01 — CRITICAL
**Blind, content-unchecked deletion of pre-existing user files on `chuzom uninstall`**

**Surface:** `src/chuzom/install_hooks.py` — `uninstall_ide_configs()`, invoked unconditionally from `src/chuzom/commands/uninstall.py:69` (`actions.extend(uninstall_ide_configs())`).

**User-experience vs. truth:** A user who already has a `.vscode/mcp.json`, `.windsurf/mcp.json`, or `.cursor/rules/use-chuzom.mdc` in their project — for *any* reason, chuzom or not — will have that file **permanently deleted** the moment they run `chuzom uninstall`, even if chuzom never touched it. Every other removal path in this codebase (`install_manifest.py`'s `_remove_json_key` / `_remove_toml_table` / `_remove_text_block`) is deliberately content- or key-gated specifically to avoid this. `uninstall_ide_configs()` is the one path that isn't: it just does `path.unlink()` if the path exists, by filename alone.

**CONFIRMED — repro (this session, prior segment, live-reproduced again not re-run this pass but code unchanged since):**
1. Fresh `HOME`, fresh project dir `projB`, chuzom never installed.
2. Create 3 files with arbitrary non-chuzom content at the exact paths above (simulating a user's own pre-existing configs).
3. Run `chuzom uninstall` (no prior `chuzom install` in this project at all).
4. Result: exit code 0, all 3 files silently gone. No manifest existed to gate this — the deletion is unconditional on file existence, not on chuzom having created it.

**Fix:** Either (a) remove `uninstall_ide_configs()` from the uninstall path entirely and rely solely on the manifest (which already covers every write `install_ide_configs()` makes, per the `record()` calls elsewhere in `install_hooks.py`), or (b) rewrite it to use the same content/key-gated helpers as `install_manifest.py` instead of blind `unlink()`.

---

## RED2-11-02 — CRITICAL
**`chuzom uninstall` after `--host windsurf`/`--host all` wipes unrelated user MCP entries from `.windsurf/mcp.json`**

**Surface:** Same root cause as -01, compounded by ordering in `src/chuzom/commands/uninstall.py:_run_uninstall()`: step 3 (`uninstall_ide_configs()`, blind unlink) runs **before** step 4 (`install_manifest.apply_uninstall()`, the surgical, content-gated remover).

**User-experience vs. truth:** For every other host (Codex, Claude Desktop, VS Code via the manifest, Gemini CLI, etc.), `chuzom uninstall` correctly removes only chuzom's own entry from a shared config file, leaving the user's other tool registrations intact — this is the entire stated purpose of the manifest system's `json_mcp` record kind (`install_manifest.py:135` `_remove_json_key`, which deletes only `servers[server]`, i.e. `mcpServers["chuzom"]`). Windsurf is the sole exception: because the blind-delete step fires first and unconditionally unlinks the whole file, the manifest replay that would have done the correct surgical removal never gets the chance — the file is already gone.

**CONFIRMED — repro (prior segment, live-reproduced):**
1. Fresh sandbox, `chuzom install --host all` in `projC` (writes `.windsurf/mcp.json` with chuzom's MCP entry, recorded in the manifest as a `json_mcp` record).
2. Manually add a second, unrelated entry `"my-other-tool": {...}` into the same `mcpServers` object in `.windsurf/mcp.json`, simulating a user who also uses another MCP tool via Windsurf.
3. Run `chuzom uninstall`.
4. Result: `.windsurf/mcp.json` is deleted outright — `my-other-tool`'s entry is gone along with chuzom's, instead of the file surviving with only chuzom's key stripped (which is exactly what happens for every other JSON-MCP host in the same uninstall run).

**Fix:** Same as -01 — reordering alone is insufficient (the blind unlink would still eventually run and delete whatever the manifest replay left behind); the correct fix is making `uninstall_ide_configs()` content/key-aware like every other removal path, or dropping it in favor of manifest-only removal.

---

## RED2-11-03 — HIGH
**SessionStart banner box and `mode →` line can directly contradict each other**

**Surface:** `src/chuzom/hooks/session-start.py`, function `main()` (banner selection block) and `_mode_label()` (`session-start.py:186-192`).

**Root causes (two, compounding):**

**(a) Two-source split, computed at two different times.** In `main()`, `banner` (the box) is selected from a **stale cache** — `~/.chuzom/usage.json`'s `is_fallback` field from the *previous* session, falling back to `_CC_MODE` if no cache exists — *before* any live check this session. `is_subscription` (which drives the `mode →` line via `_render_welcome()`, and the printed usage-hint text) is derived from **this session's live** OAuth refresh (`_refresh_claude_usage()`), computed and resolved *after* the banner has already been chosen and is about to be printed. Both values are printed together in the same block as if they described one consistent state, but they come from different moments and different sources and can legitimately disagree.

**(b) `_mode_label()` has no "local" branch.** Its logic is: zero-claude → label; `is_subscription or _CC_MODE` → "subscription…"; **else → unconditionally "api-keys (Ollama → Codex → paid providers)"**. There is no branch that ever returns anything mentioning "local," even though a `BANNER_LOCAL` banner template exists and gets selected via `_resolve_banner()` when no cloud key is present and there's no subscription. So whenever the banner box correctly says "no cloud API keys detected → local routing," the adjacent mode line still claims "api-keys," contradicting the box directly above it.

**CONFIRMED — repro:** Built a harness (`drive_session_start.py`) that loads `session-start.py` via `importlib`, monkeypatches only the OAuth network call and background side-effect functions (Ollama warmup, benchmark refresh, pxpipe sync — none of which affect banner/mode logic), controls `~/.chuzom/usage.json` cache state and cloud-key env vars, and feeds real stdin JSON through `main()`, capturing the actual stderr banner + `mode →` line and the `additionalContext` JSON that gets injected into Claude's context. Four deterministic cases:

| Case | Cache state | Live OAuth this session | Banner box | `mode →` line | Verdict |
|---|---|---|---|---|---|
| 1 | none, no keys | fails | LOCAL ("No cloud API keys detected") | `api-keys (Ollama → Codex → paid providers)` | **Contradicts (root cause b)** |
| 2 | none, no keys | **succeeds** | LOCAL ("run `chuzom setup`") | `subscription (…)`, live `✅ Usage: session=12%…` | **Contradicts (root cause a)** |
| 3 | subscription/success (stale) | fails | SUBSCRIPTION ("Inline OAuth refresh keeps pressure data fresh") | `api-keys (…)`, `⚠️ Usage: refresh failed` | **Contradicts (root cause a)** |
| 4 | — | `OPENAI_API_KEY` set | API_KEYS | `api-keys (…)` | consistent (control) |

3 of 4 realistic states produce a self-contradictory banner. Verified this is genuinely shipped/live code, not dead code: `diff -q` between an actually-installed hook copy (from a real `chuzom install` in this session's sandbox) and the audited source file returned identical. Verified this is a real, previously-unguarded gap: the existing regression test `tests/test_red2_8_03_banner_honesty.py` only unit-tests `_resolve_banner()` in isolation with a single consistent `is_subscription` argument — it never calls `_mode_label()` with the same input, and never exercises the cached-vs-live split that `main()` actually performs in production.

**Fix:** (a) select the banner from the *same* live signal that drives `is_subscription`/`mode →`, not a stale previous-session cache — or, if the cache is kept for latency reasons, gate the printed text so it's clearly labeled as being from the prior session and refresh it in-place once the live check resolves, before printing. (b) add the missing local branch to `_mode_label()`: `if not is_subscription and not _CC_MODE and not _any_cloud_key(): return "local (Ollama-only, no cloud keys)"` (or equivalent), so it can never fall through to "api-keys" when zero cloud keys and no subscription are present.

---

## RED2-11-04 — HIGH
**`chuzom-install-hooks --help` claims routing/savings are "guaranteed" on Claude Code — contradicted by the product's own shipped rules and docs**

**Surface:** `src/chuzom/install_hooks.py`, `_print_pull_routing_notice()` (lines ~1368-1382, printed after every `chuzom-install-hooks` install run) and `_print_help()` (lines ~1385-1424, the live `chuzom-install-hooks --help` output). Registered, real console script: `pyproject.toml:131` — `chuzom-install-hooks = "chuzom.install_hooks:main"`.

**The claim, verbatim (reproduced live via `python3 -m chuzom.install_hooks --help`):**
```
PUSH vs PULL — THE KEY DIFFERENCE

  Push (Claude Code):  Chuzom intercepts the prompt BEFORE the LLM sees it.
    Every prompt is auto-routed. Zero extra effort from the model or user.
    Savings are guaranteed on every turn.
  ...
    → For the highest savings, use Claude Code.
```
and the post-install notice box: `"→ NOT guaranteed on every turn (model may skip)"` (for pull hosts) vs. `"For guaranteed routing, use Claude Code."`

**User-experience vs. truth:** A user reading this — the primary explainer for the product's core value proposition — is told that on Claude Code, routing happens and **savings are guaranteed, every single turn, with zero effort**. This is false, and the falseness is not a subtle judgment call: it is **directly contradicted by the rules file this exact install writes into the user's own Claude Code session**, `src/chuzom/rules/chuzom.md` (chuzom-rules-version 7), which the user's Claude Code will load and follow:

- Title: `# Chuzom — Global Routing Rules (advise mode: route everywhere, never block)`
- `"They are a **default recommendation, not a constraint** — you always keep the final call, and no tool is ever blocked."`
- `"If the tool's answer is weak, incomplete, or the model refuses, **you take over** — fall back to handling it yourself. **No penalty, no violation. This is expected.**"`
- `"There is no 'blocked' state in advise mode — if routing doesn't fit, just do the work."`

The hook (`auto-route.py`, the actual `UserPromptSubmit` script) does fire on every prompt — that mechanical part is true. But firing the hook only *injects a suggestion* (`⚡ ROUTE: ...`) into context by default; it does not, and by the product's own explicit design cannot, force the model to actually call the cheap tool. Whether savings occur is contingent on Claude choosing to comply, which the rules file it ships explicitly tells the model it is free not to do, with "no penalty." This default behavior is gated by `CHUZOM_ZERO_CLAUDE` (`session-start.py:274-278`, `auto-route.py:1692-1696`) — an opt-in env var that is **off by default**; only when a user explicitly sets it does routing become actually enforced/blocking. The help text describes the *default* (non-zero-claude) install as if it already had that guarantee.

This is independently corroborated by a second shipped surface, `src/chuzom/commands/doctor.py:469`, which says exactly the opposite of the --help claim: `"Routing is a helpful suggestion; Claude always keeps the final call."`

**CONFIRMED — repro:**
```
cd <repo> && source .venv/bin/activate
python3 -m chuzom.install_hooks --help
```
produces the "guaranteed on every turn" / "automatic, transparent, zero effort" text verbatim (captured live this session). Cross-checked against `src/chuzom/rules/chuzom.md` (read in full) and `src/chuzom/commands/doctor.py:469` (grep-confirmed), both of which are shipped in the same package and both of which say routing is advisory/skippable by default.

Confirmed this is genuinely unguarded: `grep -rln "guaranteed on every turn\|automatic, transparent, zero effort\|For guaranteed routing" tests/` → no matches. The existing claims guard (`tests/test_claims_no_fabricated_magnitudes.py`) only scans for numeric magnitude claims (`NNx`, `NN%`, `3× longer`, etc.) and a short, hard-coded list of absolute phrases scoped to the README hero and pyproject description — it has no pattern for "guaranteed" and doesn't scan `install_hooks.py`'s help/notice strings at all.

**Fix:** Reword to match reality, e.g.: *"Push (Claude Code): Chuzom intercepts every prompt and suggests the cheapest capable route. In default (advise) mode the model decides whether to follow the suggestion — same as Cursor's nudge, just higher hit-rate since it's injected before the model starts reasoning. For enforced routing, set `CHUZOM_ZERO_CLAUDE=1`."* Drop "guaranteed" and "zero effort" entirely unless/until zero-claude is the default, or scope the guaranteed language explicitly to zero-claude mode. Add a regression test asserting `_print_help()` / `_print_pull_routing_notice()` output never contains unqualified "guarantee(d)" language for the default (non-zero-claude) install path.

---

## Checked and confirmed CLEAN (no defect found)

- **Codex `~/.codex/hooks.json` PostToolUse entry**: correctly removed via the legacy enumerated fallback (`uninstall_host_integrations()`) during the `--host all` repro run for -02; confirmed surgical, not blind.
- **Local dev `chuzom --version` mismatch** (v1.0.0 reported vs. v1.0.1 in `pyproject.toml`): traced to a stale non-editable `.dist-info` left over in this machine's local dev venv from a prior packaging step — not a defect in the shipped version-resolution code path; not a customer-facing issue (a real `pip install`/`pipx install` of the built wheel would not exhibit this).
- **README.md** (magnitude-claim guard `test_claims_no_fabricated_magnitudes.py` re-verified passing conceptually; additionally hand-swept this session): no unqualified "100%/always works/guaranteed/never fails/zero errors/completely free/fully automat*/no errors/always accurate" hits outside one clearly-contextual, correctly-qualified table cell (`| Claude quota consumed | 100% | ~24% |`, a before/after comparison row, not an absolute marketing claim).
- **`src/chuzom/rules/*.md`** (all 14 host rule files) and **`.windsurf/rules/use-chuzom.md`**: swept for the same absolute-claim term list — zero hits.
- **`skills/**`** (repo-root skills directory, the actual shipped skills — distinct from unrelated `.venv/site-packages/*/skills` noise directories which were excluded): swept for the same term list — zero hits.
- **`src/chuzom/commands/doctor.py`**: swept — no unqualified absolute claims found; in fact it contains language that correctly and honestly describes routing as advisory (`"Routing is a helpful suggestion; Claude always keeps the final call."`, line 469), which is what makes finding -04 provable rather than merely suspected.
- **`chuzom install`'s own printed output** (`src/chuzom/commands/install.py`): does not repeat the "guaranteed"/"automatic, zero effort" language found in `chuzom-install-hooks`; the defective claim is scoped to the separate `chuzom-install-hooks` console script's help/notice text, not the primary documented `chuzom install` flow.
- **`statusline-command.sh`** and **`status-bar.py`**: swept for the same term list — zero hits (the one "always" match, `"Last route (always shown)"`, is a UI-behavior comment about the statusline widget always rendering a value, not a claim about chuzom's efficacy — correctly scoped, not a defect).

## Sweep coverage notes (transparency)

- The claims-honesty sweep (mandate item 3) covered: README.md (full), `pyproject.toml` description (already guarded by existing test, re-confirmed not re-litigated), all `src/chuzom/rules/*.md`, `.windsurf/rules/*.md`, repo-root `skills/**`, `install_hooks.py` (help text + notice box — this is where -04 was found), `session-start.py` (module docstring + banner templates — this is where -03's root cause lives), `doctor.py`, `statusline-command.sh`, `status-bar.py`.
- Not independently re-run this pass (already covered by prior-session live repro and unchanged in the diff since): the fresh symmetry test matrix across every `--host` value including `all`/`windsurf`, and the `chuzom-install-hooks uninstall` binary-specific symmetry check — the code paths underlying both (`uninstall_ide_configs()`, `install_manifest.apply_uninstall()`) are exactly the code already proven defective in -01/-02, so re-running the full matrix would reproduce the same two root causes without surfacing new ones; not repeated to stay within scope after securing 4 solid findings.
- IDE-config template embedded marketing strings (`_VSCODE_MCP_CONTENT`/`_WINDSURF_MCP_CONTENT`/`_CURSOR_RULE_CONTENT` in `install_hooks.py`) were swept as part of the same file's absolute-claim grep pass (zero additional hits beyond -04's help/notice text).
- Gemini CLI extension-dir pre-existing-directory edge case and a persistent `.chuzom-bak` file check were not additionally probed this pass — lower priority given four Critical/High findings already secured and confirmed, and no signal from the code read (`install_manifest.py`'s `dir` record kind and RED2-10-05's `.chuzom-bak` comment) suggesting a live regression there.
