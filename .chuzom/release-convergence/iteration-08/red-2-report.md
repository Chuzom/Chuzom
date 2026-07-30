# RED-2 Report — Iteration 8 (final budgeted round)

**Auditor**: RED-2 (independent — no RED-1 collusion, no prior-round report read for this iteration)
**Commit**: `48fb535` on `fix/v1.0.1-audit-mitigation`
**Scope**: customer-reality — install/uninstall symmetry, backup-before-overwrite (RED1-7-02) UX, claims honesty, pre-flight/banner honesty
**Method**: live `chuzom install`/`chuzom uninstall`/`chuzom-install-hooks` runs against disposable `$HOME` sandboxes, hooks driven with real stdin JSON, `chuzom doctor` output inspected, direct in-process reproduction of the backup helper. Every finding below was actually reproduced this round; none is a re-read of a prior-round finding.

## Verdict: 3 CONFIRMED High findings. No Critical. No new install-symmetry gaps beyond what's listed.

---

## RED2-8-01 — `chuzom uninstall` (both entry points) leaves live, functioning chuzom MCP registrations in every `--host`-installed tool

**Severity**: High
**Surface**: `src/chuzom/commands/uninstall.py::_run_uninstall`, `src/chuzom/install_hooks.py::uninstall()` / `uninstall_claw_code()` / `uninstall_ide_configs()`

**User-experience-vs-truth**: A user who ran `chuzom install --host codex`, `--host cursor`, `--host gemini-cli`, `--host vscode` (all documented, supported hosts — see `README.md` "Supported IDEs" and `chuzom install --host <name>  # or: cursor, codex, gemini-cli, windsurf, all`) and later runs `chuzom uninstall` sees a long, reassuring, itemized removal log ending in:

```
Done. Restart Claude Code to apply changes.
```

Nothing in that output mentions Codex, Cursor, Gemini CLI, or VS Code. In reality, `_run_uninstall()` only calls `uninstall()` (Claude Code), `uninstall_claw_code()`, and `uninstall_ide_configs()` (which itself only removes `.vscode/mcp.json`, `.windsurf/mcp.json`, `.cursor/rules/use-chuzom.mdc` — a *different*, project-scoped set from the `--host` writers). None of the `_FILE_WRITERS` targets in `commands/install.py` (`codex`, `opencode`, `gemini-cli`, `copilot-cli`, `openclaw`, `trae`, `vscode`, `cursor`) has any remover at all — confirmed by `grep -n "host\|--host" src/chuzom/commands/uninstall.py` → zero matches.

Critically, these are not just leftover static files — they are **live MCP server registrations** that keep those tools actively routing through `chuzom` after the user believes they've uninstalled it:

- `~/.codex/config.toml` still has `[model_providers.chuzom]` pointing at `http://127.0.0.1:17900/v1`.
- `~/.gemini/settings.json` still has `"mcpServers": {"chuzom": {"command": "chuzom", "args": []}}`.
- `~/.cursor/mcp.json` still has the same live `chuzom` MCP entry.
- `~/Library/Application Support/Code/User/mcp.json` still has `"servers": {"chuzom": {"command": "chuzom", "args": []}}`.
- `~/.gemini/extensions/chuzom/` (the whole extension dir: `gemini-extension.json`, `hooks/hooks.json`, `INSTRUCTIONS.md`) survives intact.
- The project-level `.github/copilot-instructions.md` (written by `--host copilot-cli`) also survives.

By contrast, `_uninstall_claude_desktop()` correctly empties `mcpServers` in `claude_desktop_config.json` — proving the codebase already knows how to do this correctly for one surface; it was simply never extended to the `--host` writer surfaces.

If the user subsequently does `pip uninstall chuzom-router`, Codex/Cursor/Gemini CLI/VS Code will all have a dangling `chuzom` MCP entry pointing at a now-missing binary, breaking those tools' MCP initialization on next launch — a direct, provable regression caused by trusting the uninstall command's own "Done." message.

**Status**: **CONFIRMED** (reproduced twice this round, once via `chuzom uninstall`, once via `chuzom-install-hooks uninstall` on the same leftover state — both no-op on these files).

**Repro** (fresh `$HOME`):
```bash
export HOME=$(mktemp -d); cd $(mktemp -d); git init -q .
chuzom install --host claude-code
chuzom install --host codex
chuzom install --host cursor
chuzom install --host gemini-cli
chuzom install --host vscode
chuzom uninstall            # ends with "Done. Restart Claude Code to apply changes."
cat ~/.codex/config.toml    # [model_providers.chuzom] still present
cat ~/.cursor/mcp.json      # "chuzom" MCP entry still present
cat ~/.gemini/settings.json # "chuzom" MCP entry still present
ls ~/.gemini/extensions/chuzom/   # extension dir intact
```

**Suggested fix**: Give every `_FILE_WRITERS` entry in `commands/install.py` a matching remover (mirroring `_uninstall_claude_desktop`'s pattern of surgically deleting/merging-out only the `chuzom` block, not the whole file), wire them into `_run_uninstall()`, and print an explicit summary line per host that was cleaned (or a "not installed for X — skipped" line), so the final "Done." message is actually true for every surface `chuzom install --host` can touch.

---

## RED2-8-02 — Content-aware drift-refresh backup (`RED1-7-02`) silently destroys the user's ORIGINAL edit on a second drift event; the fixing message is never shown to the user in the first place

**Severity**: High
**Surface**: `src/chuzom/install_hooks.py::_backup_before_overwrite()` (lines 165-174), called from `check_and_update_hooks()` (line 217) and `check_and_update_rules()` (line 263); message sink `src/chuzom/server.py` lines 46-56.

**User-experience-vs-truth**: RED1-7-02's stated purpose (its own docstring, line 166-168): *"preserve the file about to be overwritten, so a hand-edited managed hook/rules file is never SILENTLY and PERMANENTLY destroyed."* The implementation fails this exact guarantee the second time it fires, because the backup target is a fixed, unversioned name (`dst.with_suffix(dst.suffix + ".bak")`) that is unconditionally clobbered by `shutil.copy2`:

```python
def _backup_before_overwrite(dst: Path) -> Path | None:
    backup = dst.with_suffix(dst.suffix + ".bak")
    shutil.copy2(dst, backup)     # <-- unconditionally overwrites any existing .bak
    return backup
```

Live in-process reproduction this round (`chuzom-session-start.py`, two successive hand-edits + drift-refreshes):

```
Round 1: user hand-edits hook → "USER EDIT #1"
  check_and_update_hooks() → "Refreshed chuzom-session-start.py (content drift at v18) (previous saved to chuzom-session-start.py.bak)"
  .bak now contains "USER EDIT #1"   ✓ (correct so far)

Round 2: user hand-edits hook AGAIN → "USER EDIT #2"
  check_and_update_hooks() → "Refreshed chuzom-session-start.py (content drift at v18) (previous saved to chuzom-session-start.py.bak)"
  .bak now contains "USER EDIT #2"; "USER EDIT #1" is GONE — permanently, silently.
```

The message shown to the user is byte-for-byte **identical** both times ("previous saved to chuzom-session-start.py.bak"). There is no way, from the message alone, to know that a second refresh has occurred and that an earlier `.bak` (and thus an earlier hand-edit) has just been destroyed. This is the exact failure mode RED1-7-02 was written to close — it closes it for exactly one overwrite, then re-opens it on every subsequent one. Any user who hand-edits a managed hook/rule file more than once across MCP-server restarts (a very ordinary workflow: tweak, restart, tweak again) loses everything except their most recent edit, with a message that reads as if a backup succeeded.

**Aggravating factor — message visibility**: even the (currently non-lossy) first-time case is not actually visible to an ordinary user. `server.py` routes both the refresh and the backup-path message exclusively through `log.info(...)` (structlog). `configure_logging()` in `logging.py` wires this to a plain `logging.StreamHandler()` (stderr) — grepped: zero `FileHandler` references anywhere in `logging.py` or `server.py`. The MCP server's stderr is not a channel Claude Code (or any host) surfaces to the user by default. So in practice the backup silently happens (or silently fails to protect a second edit) with no user-visible confirmation either way — the fix's own "and the backup path is reported" claim (docstring line 189-190) is true only to a log stream nobody reads.

**Status**: **CONFIRMED** (reproduced live this round via direct Python reproduction against `chuzom.install_hooks`, shown above; also independently confirmed the stderr-only sink via `server.py`/`logging.py` grep, no execution needed for that part).

**Repro**: see the round-1/round-2 script executed this round; equivalent to:
```python
from chuzom import install_hooks as ih
dst = ih._HOOKS_DST / "chuzom-session-start.py"
dst.write_text(dst.read_text() + "\n# EDIT 1\n"); ih.check_and_update_hooks()
dst.write_text(dst.read_text() + "\n# EDIT 2\n"); ih.check_and_update_hooks()
bak = dst.with_suffix(dst.suffix + ".bak")
assert "EDIT 1" not in bak.read_text()   # true — EDIT 1 is unrecoverable
```

**Suggested fix**: Timestamp or increment the backup filename (`<name>.bak.<epoch>` or `<name>.bak.1`, `.bak.2`, ...) instead of a fixed name, so successive drift events never clobber each other, and cap/rotate to avoid unbounded growth. Separately, route the refresh/backup message through a channel the user actually sees (stdout print in the CLI paths that already exist, or the SessionStart hook's own additionalContext banner) rather than stderr-only structlog, so "previous saved to X" is an actually-checkable claim.

---

## RED2-8-03 — SessionStart banner unconditionally claims paid-API routing "in effect" and names specific paid providers, even with zero API keys configured and zero subscription flag set — directly contradicting the documented, promoted zero-key install path

**Severity**: High
**Surface**: `src/chuzom/hooks/session-start.py` — `_CC_MODE` (line 96), `BANNER_API_KEYS` (lines 126-142), `BANNER = BANNER_SUBSCRIPTION if _CC_MODE else BANNER_API_KEYS` (line 144). Contrasted against the already-correct `_preflight_check()` (lines 725-787) and `chuzom doctor`'s "Provider API keys" section (both honest).

**User-experience-vs-truth**: `session-start.py`'s mode selection is a pure two-way binary on one env var:

```python
_CC_MODE = os.environ.get("CHUZOM_CLAUDE_SUBSCRIPTION", "").lower() in ("true", "1", "yes")
...
BANNER = BANNER_SUBSCRIPTION if _CC_MODE else BANNER_API_KEYS
```

There is no third "nothing is actually configured" state. Whenever `CHUZOM_CLAUDE_SUBSCRIPTION` is unset (the case for every user who has not separately run the optional `chuzom setup` wizard — confirmed by grep, `CHUZOM_CLAUDE_SUBSCRIPTION` is set *only* by `commands/setup.py`/`onboard.py`, never by `chuzom install`), the hook prints, unconditionally, at the very top of every session:

```
╔════════════════════════════════════════════════════════════════╗
║  ⚡ chuzom ACTIVE — API-key routing in effect             ║
╠════════════════════════════════════════════════════════════════╣
║  Every task is routed to the cheapest capable external model: ║
║  simple   → llm_query   (Gemini Flash / Groq / GPT-4o-mini)  ║
║  moderate → llm_analyze (GPT-4o / Gemini Pro)                ║
║  complex  → llm_code    (o3 / Gemini Pro)                    ║
║  research → llm_research (Perplexity — web-grounded)         ║
╚════════════════════════════════════════════════════════════════╝
```

This claim ("API-key routing **in effect**", naming Gemini Flash/Groq/GPT-4o-mini/GPT-4o/Gemini Pro/o3/Perplexity as the active chain) is asserted with zero check of whether any of `OPENAI_API_KEY`/`GEMINI_API_KEY`/`ANTHROPIC_API_KEY`/etc. actually exist. Live reproduction this round, driving the real hook with a fresh `$HOME`, all API-key env vars unset, no subscription flag:

```
$ echo '{"session_id":"t","hook_event_name":"SessionStart","cwd":"...","source":"startup"}' \
    | python3 .claude/hooks/chuzom-session-start.py
...
║  ⚡ chuzom ACTIVE — API-key routing in effect             ║
...  [full paid-provider chain listed as above] ...
...
mode    → api-keys (Ollama → Codex → paid providers)
...
{"additionalContext": "...ℹ️  Optional providers not configured: OpenAI, Gemini, Anthropic — routing works via Ollama."}
```

The truth ("routing works via Ollama" — zero paid providers reachable) is generated correctly, but by a *completely separate, disconnected* function (`_preflight_check()`), and appears only as a small trailing line inside a JSON blob (`additionalContext`), not in the loud boxed banner the user actually reads at the top of context. Every plain-text visual signal (the box header, the provider names, `mode → api-keys`) says paid-API routing is live; only a machine-oriented JSON tail — easy to miss, arguably not even rendered prominently by the host — says otherwise.

The product **already knows how to be honest about this exact state** elsewhere: `chuzom doctor`'s "Provider API keys" section, run against the identical environment this round, correctly prints:
```
⬜  Claude subscription mode off (set CHUZOM_CLAUDE_SUBSCRIPTION=true to enable)
⬜  No external provider API keys found in environment
⚠️   No providers configured — set at least one API key or subscription mode
```
This proves the false banner is not a fundamental limitation (no way to detect key presence) — it is a specific code path (`session-start.py`'s `BANNER` binary) that was never wired to the check that already exists and is already correct in two other places (`_preflight_check()` in the same file, and `chuzom doctor`).

This is not a rare edge case. It is the **documented, promoted default path**: README's own "Why People Install This" callout reads *"Quick Setup: Two commands (`pip install` + `chuzom install`); a local provider (e.g. Ollama) unlocks the free-routing savings"* — i.e., the headline-promoted flow is Ollama-only, zero API keys. README's "The Solution" diagram and cost table likewise sell **Ollama (free)** → **Codex CLI / Gemini CLI (free via subscriptions)** → **Claude (only when needed)** as the intended chain — not "API-key routing." A user following the documented quickstart exactly as written, with no API keys and no `chuzom setup` (which the README's grepped install/quickstart references never mention), gets a session-opening banner that falsely claims a paid multi-provider API chain is active, directly contradicting the same product's own marketing promise of a free, local-first, zero-key experience.

**Status**: **CONFIRMED** (reproduced live this round with real stdin JSON against a fresh, fully-unconfigured `$HOME`; cross-checked against `chuzom doctor`'s correct output on the identical environment; root-caused to `session-start.py` lines 96/144; confirmed via grep that `CHUZOM_CLAUDE_SUBSCRIPTION` is set only by the optional `chuzom setup`/`onboard.py`, never by `chuzom install`; confirmed via README read (lines 1-170) that the documented quickstart is exactly "`pip install` + `chuzom install`" with Ollama/Codex-CLI/Gemini-CLI positioned as the free, promoted path, and no mention of `chuzom setup` as a prerequisite).

**Repro**:
```bash
export HOME=$(mktemp -d)
unset OPENAI_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY OPENROUTER_API_KEY CHUZOM_CLAUDE_SUBSCRIPTION
chuzom install --host claude-code
echo '{"session_id":"t","hook_event_name":"SessionStart","cwd":"'"$HOME"'","source":"startup"}' \
  | python3 "$HOME/.claude/hooks/chuzom-session-start.py"
# Compare against:
chuzom doctor   # correctly says "No providers configured"
```

**Suggested fix**: Make `BANNER` selection consult the same reachability check `_preflight_check()` already performs (or call it once, upstream, and pass the result in), and add the genuinely-missing third state: when `_CC_MODE` is false AND no external API key is present AND Ollama is unreachable, show a banner that honestly says routing is unavailable/local-only-when-Ollama-starts, not "API-key routing in effect." At minimum, gate the specific named-provider list in `BANNER_API_KEYS` on at least one of those providers actually being configured, falling back to an honest "Ollama-only (no external providers configured — see `chuzom doctor`)" banner otherwise.

---

## Checked and found clean this round (tried to break, could not)

- **CHZ-DRAFT-01 / enforce-mode honesty** (`hooks/auto-route.py` `_resolve_auto_render_mode`, its call site's `_turn_blocked` derivation): unrecognized render-mode values still fail-safe to `echo` (never turn-blocking); `zero_claude` is not re-tested at the call site (avoiding the prior RED1-5-03 regression of force-blocking an operator's explicit `CHUZOM_RENDER_MODE=echo`). No new defect found.
- **`response_formatter.py`** block/echo disclaimers: both `format_direct_response()` and `format_echo_context()` prominently and correctly label routed drafts as unverified, with an explicit instruction to discard drafts that depend on unseen context. No new defect found.
- **`cap_downgraded` telemetry** (`types.py` `summary()`/`header()`): correctly names the real fallback provider via `_cap_downgrade_target()`, avoiding a false "free-local" claim when the fallback is actually paid Claude. Upstream flag origin in `router.py` was inspected but not exhaustively re-traced given the extensive prior-round hardening (RED2-02/RED2-2-02/RED2-3-01) visible in comments at that exact code region; no new defect surfaced in what was inspected.
- **Claims-honesty automated guard** (`tests/test_claims_no_fabricated_magnitudes.py`, all 7 tests): manually re-verified the RED2-7-02 carve-out narrowing is correct — `_scannable_from_lines()` only exempts `|`-prefixed table-data rows inside the disclaimed "Estimated savings by workload" section, and only while its disclaimer string is present; a synthetic smuggled-prose test case (already in the suite) is correctly caught. No abuse vector found this round.
- **`chuzom doctor` output**: independently confirmed honest — correctly reports "No providers configured" for the exact environment where `session-start.py`'s banner (RED2-8-03) is false. This asymmetry between two first-party surfaces reporting the same fact differently is itself evidence for RED2-8-03, not a separate finding.
- **Claude Desktop uninstall**: `_uninstall_claude_desktop()` correctly empties `mcpServers` rather than leaving a stale entry — the one surface among all install targets that does this correctly, and the template the fix for RED2-8-01 should follow.
- **`--host trae`'s `Path(".rules")`**: relative-to-cwd by design (matches its own docstring: "in current project directory"), consistent with the project-scoped pattern used by `.cursor/rules`; not a defect.
- **`chuzom install` vs `chuzom-install-hooks install` IDE-config auto-detection asymmetry**: confirmed real (only `chuzom-install-hooks`'s default `install` path auto-writes `.vscode/mcp.json`/`.windsurf/mcp.json`/`.cursor/rules/use-chuzom.mdc` into a detected project dir; `chuzom install` requires explicit `--host`). Checked README for any "auto-detects your project's IDEs" claim tied to `chuzom install` — none found (the only "auto-detect" claims in README are about local inference servers, unrelated). Since no documented promise is broken, this is an entry-point behavioral difference, not a provable user-facing harm — **not reported** per the no-Low/style-findings instruction.
- **Gemini extension manifest hardcoded `"version": "9.0.1"`** (vs package `1.0.1`) in `_install_gemini_cli_files()`: cosmetic, internal extension-manifest metadata; chuzom is not published to a Gemini extension registry that would consume this for update-checking. **Not reported** — does not clear the core-Medium+ bar.

---

## Summary

| ID | Severity | Title |
|---|---|---|
| RED2-8-01 | High | `chuzom uninstall` (both entry points) leaves live chuzom MCP registrations in every `--host`-installed tool (Codex, Cursor, Gemini CLI, VS Code) |
| RED2-8-02 | High | Drift-refresh `.bak` backup uses a fixed filename — a second hand-edit+refresh silently and permanently destroys the first backup, with an identical, non-differentiating message; messages are stderr-only and never user-visible |
| RED2-8-03 | High | SessionStart banner claims paid-API routing "in effect" and names specific providers with zero check that any are configured — false for the documented, promoted zero-API-key quickstart path |

**0 Critical, 3 High, 0 core-Medium.**
