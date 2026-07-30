# RED-2 Customer-Reality Audit — Iteration 5

**Auditor:** RED-2 (independent, no cross-read with RED-1)
**Commit audited:** `d80ab4bae37fa0f6f9a31f929d7da26012b924d5` (HEAD, verified unchanged at report time)
**Scope:** install/uninstall, claims honesty (G6 guard), rules-version propagation, hook
behavior (CHZ-DRAFT-01 / enforce modes), telemetry honesty, config/env foot-guns.
**Method:** Direct reproduction only (Bash/Read/Grep against real source, live hook
invocations with fake stdin JSON, install/uninstall simulated against tmp `$HOME`
fixtures, and one genuinely-live in-session reproduction of the SessionStart banner).
No finding below is asserted without a command or file:line backing it.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 3 |
| Medium | 1 |
| Low | (not reported per mandate) |

One-line titles:
- **RED2-5-01** (High) — `uninstall()` leaves `chuzom-statusline.sh` installed *and registered* in `settings.json`; Claude Code keeps executing it on every render after "uninstall".
- **RED2-5-02** (High) — `uninstall()` / `uninstall_claw_code()` never remove the `_SIDECAR_SCRIPTS` (`start-ollama.sh`, `start-pxpipe.sh`) or the `CHUZOM_CLAW_CODE=true` flag in `~/.claw-code/.env`.
- **RED2-5-03** (High) — SessionStart pre-flight banner tells the agent "Fix before starting implementation" for a missing *optional* API key even when the system is fully functional via other configured providers — reproduced live in this very session.
- **RED2-5-04** (Medium) — The G6 claims guard (`tests/test_claims_no_fabricated_magnitudes.py`) never scans `README.md` beyond its first 60 lines, and never runs the `MAGNITUDE_FORBIDDEN` (NN×/NN-NNx) pattern set against README.md at all — so unqualified multiplier claims ("3–5× Longer Sessions", "~2–3× more sessions/day", "~4–5×", "~4×") ship un-guarded in the public README, the exact surface the guard's own docstring says it exists to protect.

Focus areas confirmed **CLEAN** (checked, no reportable finding):
- Focus area #3 — rules-version propagation (`chuzom-rules-version: 7` in `src/chuzom/rules/chuzom.md`, `check_and_update_rules()` correctly detects and rewrites stale installed copies).
- Focus area #4 — CHZ-DRAFT-01 render-mode gate and the four `CHUZOM_ENFORCE` modes: verified via live hook invocation (both with local Ollama reachable, success path, and with `CHUZOM_DIRECT_EXECUTION=false` + unreachable Ollama, forcing the advisory fallback path) that shadow/advise/suggest/hard diverge honestly and proportionally in wording, none fabricate a "decision", and none leak a broker/socket path to stdout.
- Focus area #1 (partial) — the RED2-4-01 legacy `llm-router.md`/`llm-router-*.py` migration itself works correctly on both `install()` and `uninstall()` (confirmed via grep of `_legacy_llm_router_paths()` call sites in both functions) and does not delete anything the current chuzom install still needs.
- Zero-provider foot-gun (focus area #6, partial): a session with **no** API keys and an **unreachable** Ollama (`CHUZOM_OLLAMA_URL=http://127.0.0.1:1`, `env -i`) fails open cleanly — hook exits 0, emits an honest "suggestion only, nothing is blocked" advisory, no crash, no fabricated draft.

---

## Findings

### RED2-5-01 — Uninstall leaves the statusline script installed and actively running (High)

**Surface:** `src/chuzom/install_hooks.py`, `install()` lines 751–778 vs `uninstall()` lines 797–869.

**What the user experiences vs. what's true:** The user runs the uninstall path (CLI
`chuzom uninstall` / equivalent) expecting Chuzom to be fully removed. In reality:

- `install()` (lines 751–778) copies `statusline-command.sh` → `~/.claude/hooks/chuzom-statusline.sh`
  and writes a `"statusLine": {"type": "command", "command": "bash <path>"}` entry
  into `~/.claude/settings.json`.
- `uninstall()` (full body read, lines 797–869) iterates `_HOOK_DEFS` to remove
  UserPromptSubmit/PreToolUse/etc. hooks, removes the MCP server registration, removes
  `chuzom.md` rules, and removes legacy `llm-router.*` artifacts — but **never once
  references `chuzom-statusline.sh` or the `statusLine` settings key.** Grep confirms
  zero occurrences of `statusline`/`statusLine` anywhere in the `uninstall()` function body.

Consequence: after "uninstall", Claude Code continues to invoke
`bash ~/.claude/hooks/chuzom-statusline.sh` on every status-line render (this runs on a
timer/every prompt, per Claude Code's statusLine mechanism) — a script belonging to a
product the user just told the system to remove, indefinitely, until the user manually
edits `settings.json` by hand. This is an ongoing, silent side effect post-uninstall, not
a cosmetic leftover file.

**CONFIRMED** via source read: `install()` body (751–778) shows the write; `uninstall()`
full body (797–869, re-read this session) shows no corresponding removal — `grep -n
"statusline\|statusLine" src/chuzom/install_hooks.py` returns only the three `install()`-path
line groups (751–778) plus one docstring reference (line 1241), none inside `uninstall()`.

**Suggested fix:** In `uninstall()`, mirror the `install()` block: delete
`~/.claude/hooks/chuzom-statusline.sh` if present, and if `settings.json["statusLine"]["command"]`
matches the chuzom-installed command, delete the `statusLine` key (or restore to whatever
it was before install, if that state is ever captured — currently it is not).

---

### RED2-5-02 — Sidecar scripts and the claw-code marker flag survive uninstall (High)

**Surface:** `src/chuzom/install_hooks.py` — `_SIDECAR_SCRIPTS` (line 245), copy sites at
lines 694 (`install()`) and 923 (`install_claw_code()`); `CHUZOM_CLAW_CODE` write site at
lines 937–951 (`install_claw_code()`); `uninstall()` (797–869) and `uninstall_claw_code()`
(969–1023), both re-read in full this session.

**What the user experiences vs. what's true:**

- `_SIDECAR_SCRIPTS = ["start-ollama.sh", "start-pxpipe.sh"]` (line 245) are copied into
  `~/.claude/hooks/` by `install()` (line 694) and into the claw-code hooks dir by
  `install_claw_code()` (line 923). These are plain files with no `event`/`matcher`, so
  they are invisible to the `_HOOK_DEFS`-driven removal loop by construction.
  `uninstall()` (797–869, full body) contains **zero** references to `_SIDECAR_SCRIPTS`.
  `uninstall_claw_code()` (969–1023, full body) likewise contains **zero** references.
  Both scripts are left on disk in `~/.claude/hooks/` (and the claw-code equivalent)
  forever after uninstall.
- `install_claw_code()` (937–951) writes `CHUZOM_CLAW_CODE=true` into
  `~/.claw-code/.env` (creating the file/parent dir if needed) so the claw-code host
  knows Chuzom is active. `uninstall_claw_code()` (969–1023, full body, re-verified this
  session) never touches `~/.claw-code/.env` or this flag — grep for `CHUZOM_CLAW_CODE`
  in `install_hooks.py` returns only the three lines inside `install_claw_code()`
  (941, 944, 951), none inside `uninstall_claw_code()`.

Consequence: any code path in the claw-code host (or a future chuzom version) that
branches on `CHUZOM_CLAW_CODE=true` continues to believe Chuzom is installed after the
user has uninstalled it. The two orphaned shell scripts are lower-impact (dead files) but
still fail the basic "uninstall removes what install created" contract, and one of them
(`start-ollama.sh`) is a script that starts a background service — an orphaned copy
sitting in `~/.claude/hooks/` is a plausible source of confusion if anything ever invokes
hooks-dir scripts by directory scan rather than exact registered command.

**CONFIRMED** via source reads of `install()` (642–869 region, including the specific
694/751–778/797–869 line spans), `install_claw_code()` (870–969, full body), and
`uninstall_claw_code()` (969–1023, full body) plus targeted greps for
`_SIDECAR_SCRIPTS`/`CHUZOM_CLAW_CODE`/`statusline` across the whole file confirming no
removal-side occurrence outside the `install*` functions.

**Suggested fix:** Add a `for name in _SIDECAR_SCRIPTS: (dir / name).unlink(missing_ok=True)`
loop to both `uninstall()` and `uninstall_claw_code()` (mirroring the existing copy loops
at 694/923), and add explicit removal of the `CHUZOM_CLAW_CODE=true` line from
`~/.claw-code/.env` in `uninstall_claw_code()` (parse-and-rewrite, same pattern already
used for `settings.json` in the same function).

*Minor, non-blocking note:* `~/.chuzom/` (the state/log dir holding
`pending_route_*.json`, session-context and savings logs) is never referenced anywhere in
`install_hooks.py` (`grep -n '\.chuzom\b' src/chuzom/install_hooks.py` → no matches), so
uninstall never offers to clean it. This is consistent with how most CLIs treat
cache/state dirs and is not being scored as its own finding, but it reinforces that
"uninstall" in this product is a partial hook/settings cleanup, not a full removal.

---

### RED2-5-03 — SessionStart pre-flight banner tells the agent to "fix" an optional, non-blocking condition (High)

**Surface:** `src/chuzom/hooks/session-start.py`, `_preflight_check()`, lines 725–777.

**What the user experiences vs. what's true:** `_preflight_check()` loops over
`OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` (lines 735–747) and appends
`"{key} missing"` to `issues` for **any** key that isn't set — with the sole exception of
`ANTHROPIC_API_KEY` in Claude Code subscription mode (line 742–745, correctly treated as
expected). Gemini and OpenAI get no such carve-out: a user who has deliberately chosen
Ollama-only or Claude-subscription-only routing (both fully product-supported
configurations — confirmed elsewhere in this audit that the zero-cloud-key path fails
open cleanly) still gets every missing cloud key listed as an "issue". `Ollama not
running`/`not found` (750–760) and `CHUZOM_ENFORCE=hard` (764–765, itself only a
heads-up, not a problem) are bucketed into the same list. Whenever `issues` is non-empty
for **any** reason, lines 774–777 unconditionally render:

```
⚠️  Pre-flight issues:
  ✗ <each issue>
  Fix before starting implementation.
```

This text is injected as `additionalContext` into the agent's own SessionStart context —
it is an imperative addressed at the coding agent, not just a cosmetic status line for
the human — so it can push the agent to treat a fully-optional configuration gap as a
blocking defect it must resolve before doing anything else (e.g. prompting the user for
an API key that isn't actually needed, per the safety rule against entering
credentials/being asked to route around it).

**CONFIRMED — reproduced live in this very audit session**, not simulated: the
SessionStart hook context visible earlier in this session reads verbatim:

```
✅ Usage: session=63% weekly=73% sonnet=0%
⚡ p50: gpt-4o 1.0s · qwen3-coder:30b 2.5s · hermes3:8b 2.8s · qwen2.5-coder:7b 3.0s · qwen2.5-coder:7b 3.9s
⚠️  Pre-flight issues:
  ✗ GEMINI_API_KEY missing
  Fix before starting implementation.
```

The `p50` line proves Ollama is reachable and multiple local models responded; the
absence of any `OPENAI_API_KEY missing` / `Ollama not running` / `CHUZOM_ENFORCE=hard`
line proves OpenAI is configured, Ollama is healthy, and enforce mode is the default —
i.e. **three of four possible routing paths (Ollama, OpenAI, Claude subscription) are
fully functional on this machine**, yet the banner still asserts an actionable defect
("Fix before starting implementation") over a single redundant, optional third provider
key. This is not a hypothetical edge case; it is what a normal, correctly-configured user
on this exact codebase saw during this audit.

**Suggested fix:** Distinguish "nothing works, you have zero routing paths" (genuinely
actionable) from "you have N of 3 possible providers configured" (informational, not an
issue). Only emit the "Fix before starting implementation" imperative when the union of
configured keys + reachable Ollama + Claude-subscription-mode yields **zero** usable
routing paths. Otherwise, either stay silent or use non-imperative phrasing (e.g. "ℹ️
Optional providers not configured: Gemini — routing still works via Ollama/OpenAI/Claude").
Separately, `CHUZOM_ENFORCE=hard` should not share the same "issue"/"fix" bucket as a
missing key — it is a mode notice, not a defect.

---

### RED2-5-04 — G6 claims guard never scans the bulk of README.md, where unqualified multiplier claims actually ship (Medium)

**Surface:** `tests/test_claims_no_fabricated_magnitudes.py` vs `README.md` (502 lines total).

**What the guard claims vs. what it actually covers:**
- `test_readme_headline_has_no_fabricated_claims` (lines ~35–39) scans only
  `README.md`'s **first 60 lines**, against the narrow `FORBIDDEN` list (5 hardcoded
  phrases: "3× longer", "60–90%", "every prompt flows...", "no cloud", "zero data
  leaves...").
- `test_no_fabricated_magnitude_claims_anywhere_in_src` (lines 60–84) — the broader guard
  with the generic `MAGNITUDE_FORBIDDEN` patterns (`\d+-\d+[x×]`, `\d{2,}[x×]\s*(less|cheaper|
  faster|savings?)`) that would catch things like "3–5×" or "4–5×" — is scoped to
  `roots_and_globs = [(ROOT/"src"/"chuzom", ...), (ROOT/"skills", ...)]` only (lines
  65–68). **`README.md` lives at the repo root and is in neither root**, so it is never
  scanned by this test at all.

Net effect: everything in `README.md` past line 60, and every `NN×`/`NN-NN×` style claim
anywhere in `README.md` at any line, is completely unguarded. Live examples present in
the file today (none of these are hypothetical — read directly from `README.md`):

- Line 141: `### ⏱️ 3–5× Longer Sessions` — an unqualified multiplier claim, structurally
  identical to the "3× longer sessions" claim the guard's own module docstring (lines
  1–8) cites as the original fabricated-claim audit finding this guard exists to prevent
  recurrence of.
- Lines 209–210 (workload table): `~2–3× more sessions/day`, `~4–5×`, `~4× (1–2 → 6–8 /
  day)` — three more unqualified multiplier figures in a table presented as concrete
  per-workload guidance, none inside the guard's first-60-lines or src/skills scan scope.

**CONFIRMED** via direct read of both test functions' scope logic and direct read of the
live README.md content at the cited line numbers (`sed -n '135,145p'` and
`sed -n '205,215p' README.md`, output captured verbatim above in this report's
investigation). Whether these particular numbers are individually defensible/hedged
elsewhere in prose is a separate question from the guard's coverage gap being real: the
guard's stated job is to prevent exactly this class of claim from reappearing anywhere a
user-facing surface ships it, and README.md is the single most user-facing surface in the
repo, largely outside its scan.

**Suggested fix:** Add `ROOT / "README.md"` (whole file, not just first 60 lines) as a
third scan target in `test_no_fabricated_magnitude_claims_anywhere_in_src` (or a sibling
test), using the same `MAGNITUDE_FORBIDDEN` pattern set already defined. If the
"3–5×"/"2–3×"/"4–5×" figures in the table are meant to be defensible estimates rather
than fabricated claims, they need explicit hedging in-line ("estimated", "up to", a
footnote to methodology) — currently the header/table cells present them as bare fact,
which is exactly the presentation style the original CHZ-AUD-010 audit flagged.

---

## What was checked and found clean (no separate write-up needed)

- **Legacy `llm-router` migration (RED2-4-01):** `_legacy_llm_router_paths()` is invoked
  from both `install()` and `uninstall()`; confirmed it only targets pre-rebrand
  `llm-router.md`/`llm-router-*.py` files that are never referenced by current code, so
  cleanup does not delete anything a current chuzom install still needs.
- **Rules-version propagation (focus area #3):** `src/chuzom/rules/chuzom.md` carries
  `<!-- chuzom-rules-version: 7 -->` on line 1; content matches what ships; version bump
  discipline is guarded by `test_rules_version_bumped_when_content_changes` (>=7).
- **CHZ-DRAFT-01 / enforce-mode honesty (focus area #4):** Live-tested both the
  direct-execution success path (all four enforce modes converge, correctly, since
  enforce-mode only governs the *fallback* advisory path) and the fallback path (forced
  via `CHUZOM_DIRECT_EXECUTION=false` + unreachable Ollama) — shadow/advise/suggest/hard
  diverge in wording proportionally to their real enforcement behavior, none claim a
  `"decision"` they don't have on the advisory-only path, and stdout never leaks a
  broker/socket file path.
- **Zero-provider fail-open (part of focus area #6):** `env -i` + unreachable Ollama
  (`CHUZOM_OLLAMA_URL=http://127.0.0.1:1`) → hook exits 0, emits an honest "suggestion
  only — nothing is blocked" message, no crash, no fabricated draft content.

No Critical findings were identified — nothing here breaks install on first run,
corrupts data, or leaks secrets/paths. The three High findings are all "the product does
something other than what a reasonable user would infer from 'uninstall' or from a
'fix this' banner," which the mandate's severity rubric places at High (misleading
output / broken cleanup), not Critical.
