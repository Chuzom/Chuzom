# RED-2 Audit Report — Iteration 6 (commit 1dd7401)

Independent CUSTOMER-REALITY audit. No RED-1 output was read. All findings below were
reproduced live (install/uninstall against a scratch HOME, direct function execution,
and — for finding 1 — against my own real, already-installed `~/.claude` on this
machine) unless explicitly marked PLAUSIBLE.

## Summary

| ID | Severity | One-line |
|----|----------|----------|
| RED2-6-01 | **Critical** | Hook auto-update is silently a no-op for any hook whose content changed without a version-stamp bump — confirmed LIVE: my own real installed `session-start.py`/`auto-route.py` are running stale pre-fix logic (including missing security fixes) despite `check_and_update_hooks()` reporting nothing to update |
| RED2-6-02 | High | `chuzom uninstall` never calls `uninstall_claw_code()` — a full orphaned claw-code integration (14 hook files, 2 sidecars, a live MCP registration, and a leaked `CHUZOM_CLAW_CODE=true` flag) survives the documented uninstall command whenever claw-code was detected |
| RED2-6-03 | core-Medium | `check_and_update_rules()` shares the identical structural flaw as the hooks mechanism (version-stamp-gated, not content-diff-gated); its only guard is a static `>= 7` floor test that would not catch the next un-bumped content change — same failure class as RED2-6-01, currently latent (no active drift) but structurally unguarded |

**2 findings ≥ High, 1 core-Medium.** Iteration-5 fixes RED2-5-01/02/03/04 were verified
correct **in repo source** (see "iteration-5 fix verification" below) — the regression is
not in the fixes themselves, it's that the delivery mechanism doesn't ship them to
existing installs.

---

## RED2-6-01 — Critical: hook auto-update silently no-ops on content drift (confirmed live, on my own real machine)

**Surface:** `src/chuzom/install_hooks.py::check_and_update_hooks()` / `_hook_version()`
(lines ~115–190); affects `src/chuzom/hooks/session-start.py` and
`src/chuzom/hooks/auto-route.py` concretely, and by mechanism any hook file, going
forward.

**Claim vs. reality:** the docstring says update is
*"Called automatically on MCP server startup so existing users get hook updates after
`pip install --upgrade chuzom-router` without re-running install."* In reality, the
update decision is purely `src_v > dst_v` on a `# chuzom-hook-version: N` comment — it
never diffs content. If a commit changes hook behavior without bumping that comment, the
fix **never reaches already-installed users**, forever, silently, with no error and no
signal to the user that anything is stale.

**CONFIRMED, live, three ways:**

1. **Version-stamp comparison, direct:**
   ```
   $ head -5 ~/.claude/hooks/chuzom-session-start.py | grep -i version
   # chuzom-hook-version: 17
   $ head -5 src/chuzom/hooks/session-start.py | grep -i version
   # chuzom-hook-version: 17
   ```
   Identical version (17 == 17) — `check_and_update_hooks()` will treat these as
   equivalent — yet a full diff shows the installed copy is running the **old,
   pre-RED2-5-03 `_preflight_check()`** (`issues`/`ok` list pattern, "Fix before
   starting implementation." wording) while the repo has the **new, fixed**
   `paths`/`optional_missing` pattern that iteration 5 explicitly shipped to stop
   telling users to "fix" a merely-missing optional provider.

   Same story for `auto-route.py` (version 26 == 26 on both sides), but the drift is
   far larger and includes **security fixes**: `_safe_sid()` path-traversal
   sanitization (CHZ-ST-001/CHZ-SEC-08 — an unsanitized `session_id` could escape
   `~/.chuzom` and enable arbitrary file writes), `_scrub_secrets_text()` /
   0600-permission transcript writes (CHZ-SEC-01 — the installed hook still writes
   **unredacted prompts/drafts world-readable at 0644**), the `CHZ-DRAFT-01` /
   `RED1-5-03` render-mode fix, the `CHZ-ST-003` fail-open wrapper around `main()`
   (installed hook can still crash a turn instead of failing open), and the
   `RED1-06`/`RED1-2-03` route-id collision fix.

2. **`check_and_update_hooks()` executed directly against my real, already-installed
   `~/.claude`:**
   ```python
   >>> ih.check_and_update_hooks()
   []
   ```
   Empty list = "nothing needed updating." This is the function a real user's MCP
   server calls on every startup, run against a real installed system that is
   demonstrably missing multiple fixes including security fixes.

3. **Live user-facing symptom, observed twice this session as an actual SessionStart
   banner injected into my own real Claude Code session** (not a simulation):
   ```
   ⚠️  Pre-flight issues:
     ✗ GEMINI_API_KEY missing
     Fix before starting implementation.
   ```
   This is the exact dishonest pattern RED2-5-03 was supposed to have eliminated
   (Gemini is one of several optional providers; OpenAI/Anthropic-subscription/Ollama
   were all available) — reproduced on a real machine, not a lab condition, precisely
   because the fixed source never made it into `~/.claude/hooks/chuzom-session-start.py`.

**Root cause:** no CI/test guard exists that fails when a hook's tracked content
changes without a corresponding version bump. `git show --stat 1dd7401` touched exactly
these two hook files (9 and 57 lines) and neither had its version stamp bumped. This is
not a one-off slip — `auto-route.py`'s drift spans several historical fixes
(CHZ-ST-001, CHZ-SEC-01/08, CHZ-ST-003, RED1-5-03, RED1-06), meaning the stamp has been
stale across **multiple** releases, not just this one commit.

**Why Critical, not High:** this silently defeats the update path for security fixes
(unsanitized session-id path traversal, plaintext-at-0644 prompt/draft persistence) on
every already-installed user's machine, with the product's own mechanism reporting
"nothing to do" — there is no user-visible signal that anything is wrong, and the stated
remediation ("`pip install --upgrade`, no reinstall needed") does not work.

**Suggested fix:** make the update decision content-hash-based (or content-diff-based)
in addition to/instead of the version-stamp gate — e.g., store a hash of each shipped
hook's content at install time and re-copy whenever the bundled hash differs, regardless
of the version comment. At minimum, add a CI test (mirroring
`test_rules_version_bumped_when_content_changes` but content-hash-aware, not a static
floor) that fails whenever a hook file's diff is non-trivial but its `chuzom-hook-version`
line is unchanged in the same commit — today `tests/test_install_hooks.py` only tests
`_hook_version()`'s parsing and the copy-decision logic *given* a stamp, never that real
stamps are bumped when they should be, unlike the (weaker, but present) `chuzom.md`
rules-version guard. Also consider a startup diagnostic (`chuzom doctor`) that flags
"installed hook differs from bundled hook but version matches" so an operator can at
least detect drift even before the mechanism is fixed.

---

## RED2-6-02 — High: `chuzom uninstall` leaves a full orphaned claw-code install behind (confirmed live, tmp-HOME repro)

**Surface:** `src/chuzom/commands/uninstall.py::_run_uninstall()` — calls only
`install_hooks.uninstall()` (+ optional `--purge`); never calls
`install_hooks.uninstall_claw_code()` or `uninstall_ide_configs()`.

**Repro (tmp HOME, real CLI entry points, not lower-level helpers):**
```
mkdir -p "$TMPHOME/.claw-code"            # claw-code auto-detection marker
_run_install([])                          # → auto-detects claw-code, installs BOTH
                                           #   the primary Claude Code integration
                                           #   AND a full parallel claw-code copy
_run_uninstall([])                        # → the documented uninstall command
diff before/after → 16 chuzom-authored files still present under $TMPHOME/.claw-code/
```

**Confirmed leftover (all genuinely chuzom-attributable, verified by content not just
existence):**
- `.claw-code/.env` — **still contains `CHUZOM_CLAW_CODE=true`** verbatim (verified via
  `cat`)
- `.claw-code/hooks/chuzom-*.py` × 12 (all hook files) + `start-ollama.sh` +
  `start-pxpipe.sh` (2 sidecars) = 14 files
- `.claw-code/settings.json` — **still registers all chuzom hooks** (SessionStart,
  UserPromptSubmit ×2, PreToolUse ×2, SubagentStart, ...) — verified by parsing the JSON
  and confirming live hook command entries pointing at the (leftover) hook files

The uninstall's own stdout confirms it correctly cleans the *primary* Claude Code
surfaces it does touch (`~/.claude/hooks/chuzom-*.py`, both MCP registration files
`~/.claude/settings.json` and `~/.claude.json`, `~/.claude/rules/chuzom.md`, the
statusline, Claude Desktop's `claude_desktop_config.json`) — independently
content-verified this session (`grep -i chuzom` on all three returns nothing, and the
Claude Desktop config's `mcpServers` is `{}`). The gap is scoped exactly to claw-code:
zero mentions of `.claw-code` anywhere in the uninstall's output, and the entire
parallel install (including a live MCP server registration and an environment flag)
survives untouched.

**User impact:** anyone who has claw-code installed alongside Claude Code (or who once
had a `~/.claw-code/` directory present for any reason at install time — detection is
directory-existence only, not a real-installation check) runs `chuzom uninstall`,
believes chuzom is gone, but chuzom's hooks remain registered and active in claw-code
indefinitely, plus a stray `CHUZOM_CLAW_CODE=true` env flag.

**Suggested fix:** `_run_uninstall()` should call `uninstall_claw_code()` (and
`uninstall_ide_configs()`) unconditionally, mirroring the auto-detect-on-install
symmetry — uninstall should clean up everything install could have created, not only
what the primary Claude Code path created. Minor/related: `.claude/backups/` accumulates
`.claude.json.backup.<timestamp>` files across install cycles with no cleanup on
uninstall — noted for completeness, not scored as its own finding (no functional/
security impact, just cruft).

---

## RED2-6-03 — core-Medium: `check_and_update_rules()` has the same structural flaw, only weakly guarded

**Surface:** `src/chuzom/install_hooks.py::check_and_update_rules()` (version-stamp
comparison via `_RULES_VERSION_RE` on `<!-- chuzom-rules-version: N -->`, structurally
identical to the hooks mechanism in RED2-6-01) and
`tests/test_claims_no_fabricated_magnitudes.py::test_rules_version_bumped_when_content_changes`.

**Current state — no active drift:** `git show --stat 1dd7401` did not touch
`rules/chuzom.md`; repo (`src/chuzom/rules/chuzom.md`) and my real installed
(`~/.claude/rules/chuzom.md`) copies are byte-identical at version 7 (`diff` empty).
This is **not** a live finding today.

**Why it's still worth flagging:** the one guard that exists for this class of bug
(`test_rules_version_bumped_when_content_changes`) only asserts the version number is
`>= 7` — a static floor, not a check that content changes are accompanied by a version
bump. It would not have caught, and will not catch, the *next* content edit to
`chuzom.md` that forgets to bump the version — exactly the failure mode RED2-6-01
demonstrates is live and already happening for hooks, which have **no analogous guard
test at all** (confirmed: `grep -rn "def test_" tests/` finds only hook-version
*parsing* tests in `test_install_hooks.py`/`test_doctor.py`, none that check stamps are
bumped when content changes). Given RED2-6-01 proves this exact class of bug already
shipped silently and undetected for real hook files, the rules path — sharing the same
mechanism and an equally weak guard — is a latent recurrence risk, not a hypothetical
one.

**Suggested fix:** replace/augment the floor-test with a real content-diff-aware check
(same recommendation as RED2-6-01): compare a hash of `chuzom.md`'s content at HEAD vs.
the version last bumped (e.g. via git blame on the version line, or a stored
content-hash), and fail CI if content changed since the last version bump.

---

## Iteration-5 fix verification (source-level — all correct; the gap is propagation, not correctness)

- **RED2-5-01/02 (uninstall statusline/sidecar cleanup):** confirmed still correct via
  this session's tmp-HOME repro — statusline and sidecar scripts are properly removed
  from the **primary** `~/.claude` path. (The gap found this iteration, RED2-6-02, is
  scoped specifically to the claw-code path never being invoked at all, not a regression
  in the primary-path fix.)
- **RED2-5-03 (`_preflight_check` honesty):** re-verified against **current repo
  source** across the full requested env matrix, using a corrected harness (tmp HOME
  with no real `~/.chuzom/.env`, `PATH` pointed at an empty dir to neutralize the real
  `ollama` binary, `CHUZOM_CLAUDE_SUBSCRIPTION` unset so `_CC_MODE` is genuinely False):
  - Zero keys + Ollama unreachable + no CC subscription → **correctly** emits the
    actionable `⚠️  No routing paths available — Chuzom cannot route. Set an API key
    (OpenAI/Gemini/Anthropic) or start Ollama before starting.`
  - Any one path available (OpenAI only; OpenAI+Anthropic; CC-subscription-only) with
    Gemini missing → **correctly** stays informational (`ℹ️  Optional providers not
    configured: Gemini — routing works via …`), never says "fix"
  - `CHUZOM_ENFORCE=hard` → **correctly** demoted to a heads-up line, never bucketed as
    an "issue"
  This confirms the fix is logically sound in source. It is the **installed** copy on a
  real machine that still exhibits the old, dishonest behavior — see RED2-6-01, which is
  the actual live-reproducible bug for this area now.
- **RED2-5-04 (README claims guard):** read `tests/test_claims_no_fabricated_magnitudes.py`
  in full. The whole-README scan (`test_readme_full_has_no_unqualified_magnitude_claims`)
  and the carve-out-requires-its-disclaimer guard
  (`test_readme_estimates_carveout_requires_its_disclaimer`) are both present and
  correctly wired: the carve-out only exempts the "Estimated savings by workload"
  section, and only for as long as its `"illustrative estimates — directional, not
  measured"` disclaimer string is present in the file — if the disclaimer is removed,
  the whole README (including that section) is scanned. This is not trivially abusable:
  moving/duplicating the disclaimer elsewhere in the README doesn't help an attacker
  smuggle in a bare claim, since the carve-out's boundary is the heading-to-next-heading
  span, not disclaimer-presence-anywhere. Did not find additional unscanned surfaces
  within the audit's time budget beyond what `test_no_fabricated_magnitude_claims_anywhere_in_src`
  already covers (`src/chuzom/**/*.{py,md,mdc}` and `skills/**/*.{md,mdc}`) — this is a
  reasonably broad sweep. No new finding here.

## Checked, no finding (time/effort budget did not permit exhaustive coverage of every
listed item — noted for the next iteration if desired)
- IDE-config templates (`_VSCODE_MCP_CONTENT`/`_WINDSURF_MCP_CONTENT`/
  `_CURSOR_RULE_CONTENT`) — not independently re-scanned for magnitude claims beyond what
  the existing guard test already covers.
- `agentic_registry.py` state-file cleanup on uninstall — not investigated.
- `~/.chuzom/settings.json.corrupt.*.bak` accumulation — not investigated.
- `cap_downgraded` telemetry rendering — not investigated.
- Functional (not just banner-text) zero-provider fail-open behavior at actual routing
  time — not independently exercised this session (the `CHZ-ST-003` fail-open wrapper
  discovered in the `auto-route.py` diff during RED2-6-01's investigation is itself
  further evidence supporting RED2-6-01: it exists in repo source but is **not** present
  on my real installed hook, so a real crash-path scenario would behave differently
  installed vs. as-shipped — folded into RED2-6-01 rather than reported separately).

None of these reached a reproduced or clearly-plausible Critical/High/core-Medium finding
within this audit's scope, so they are listed as unchecked/out-of-budget rather than
"clean."
