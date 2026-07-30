# RED-2 Customer Reality & Failure Audit — Iteration 4

**Auditor:** RED-2 (fresh-context, independent, no anchoring on prior iterations)
**Repo:** `/Users/yaliandrona/Projects/Chuzom`
**Branch/HEAD at audit time:** `fix/v1.0.1-audit-mitigation` @ `c025f68`
**Mode:** READ-ONLY (no edits, no commits)
**Scope:** Chuzom's stated promise — an execution router that prefers local/cheap paths, uses paid APIs only as a pressure valve, never fabricates results/completion, keeps local-first privacy, and is honest about its own limits (advise, not block).

---

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 1 |
| HIGH | 1 |
| MEDIUM | 1 |
| LOW / INFO | 2 |

**Top 3, one line each:**

1. **RED2-4-01 (CRITICAL)** — A residual rules file from the product's pre-rebrand identity (`~/.claude/rules/llm-router.md`) is actively loaded into this real user's session right now and tells the model routing is a "HARD CONSTRAINT" it must obey — the exact opposite of the current product's "advise mode, never block" promise. Proven live: both files' full text appeared together in this very conversation's own injected context.
2. **RED2-4-02 (HIGH)** — The documented automatic rules self-update ("existing users get rule updates... without re-running install") cannot fix a previously-shipped fabricated claim ("costs 50–100× less") because the fix that reworded it never bumped `<!-- chuzom-rules-version -->`; `check_and_update_rules()`'s `src_version <= dst_version` gate treats the stale file as current and silently does nothing.
3. **RED2-4-03 (MEDIUM)** — `skills/routing/SKILL.md` still ships a live "saves ~50–100×" / "50× cheaper than o3" claim, in a file type (`skills/*.md`) that `scripts/lint_capability_claims.sh` never scans — the exact class of fabricated-magnitude claim the guard exists to catch, in a location the guard cannot see.

---

## RED2-4-01 — Orphaned pre-rebrand `llm-router.md` rules file directly contradicts the current "advise, never block" promise, and no install/upgrade/uninstall path is aware of it

**Severity:** CRITICAL
**Category:** Instruction integrity / false safety promise
**Affected promise:** "Routing is advise-only, never blocks. There is no 'blocked' state." (current `src/chuzom/rules/chuzom.md`, lines 2, 41)

### Affected surface
- `~/.claude/rules/llm-router.md` (real file on this user's disk, 4729 bytes, mtime 8 Jul 12:19) — loaded by Claude Code as global private instructions on every session, regardless of `settings.json` hook wiring (rules files under `~/.claude/rules/*.md` are auto-loaded; they don't need to be "registered" anywhere).
- Zero code in the current repo is aware this file exists: `grep -n "llm-router" src/chuzom/install_hooks.py` → **no matches**.

### Reproduction (observed, not theorized)
This exact conversation's own system context, at session start, rendered **both** files verbatim under the heading "Codebase and user instructions... IMPORTANT: These instructions OVERRIDE any default behavior":

- `~/.claude/rules/llm-router.md` (the orphaned file, active right now):
  > "## ROUTING HINT = HARD CONSTRAINT (NOT a suggestion)... a binding routing decision, not advice."
  > Table of "Forbidden actions": using Read/Grep/Glob, Bash, WebSearch/WebFetch, or the Agent tool "to answer the question yourself" once a hint fires — labeling Agent-tool use "the #1 violation."
  > "Do NOT treat 'I could do this better myself' as a reason to skip routing"

- `src/chuzom/rules/chuzom.md` (the current, intended file — version 6, confirmed via `Read`):
  > "# Chuzom — Global Routing Rules (advise mode: route everywhere, never block)"
  > "no tool is ever blocked" (line 6)
  > "Don't refuse or stall a task because a hint fired. There is no 'blocked' state in advise mode" (line 41)

These are not similar-but-different documents — they are **directly contradictory instruction sets for the identical trigger** (a `⚡ ROUTE:` hint), both live-loaded simultaneously on the same real machine, right now, in this exact session.

### Root cause
Confirmed via `git log --follow --name-only` at genesis commit `b15876c` ("v0.0.1: Genesis — private fork from llm-router..."): the repo originally shipped `src/tessera/rules/llm-router.md` alongside the ancestor of the current rules file, before the product was renamed Tessera → Chuzom (`cd70fd5`, "rebrand: Tessera → Chuzom"). The old `llm-router.md` template was dropped from the *repository*, but no migration/cleanup logic was ever written to remove it from *already-installed users' machines*. The only cleanup mechanism that exists at all (`_sync_legacy_hook_alias()` / `_legacy_alias_path()`, `install_hooks.py` ~279-310) is explicitly scoped to `.py` hook scripts with generic unprefixed names — it has no analog for `.md` rules files, and would not apply to this cross-product-identity scenario even if it did.

Confirmed this session: `uninstall()` (`install_hooks.py:765-820`) only ever removes `_RULES_DST / "chuzom.md"` (line 812-815) — it has no code path capable of removing `llm-router.md` either. **A full, clean `chuzom uninstall` on this exact machine would leave the contradictory file in place forever.** There is no install, upgrade, or uninstall path in the current product that can ever discover or remove this file.

### Customer impact
Any user who has had Chuzom installed since before the Tessera→Chuzom rename (or who received the file through any similar historical install) is currently operating under two simultaneously-loaded, contradictory global instruction sets. In practice the more restrictive, more recently-emphasized, or more attention-grabbing set of instructions (here: "HARD CONSTRAINT," "#1 violation," bold "forbidden" table) tends to dominate model behavior — meaning the product's central, repeatedly-advertised safety property ("advise mode, we never block you, you always keep the final call") is not reliably true for this class of user, and the user has no way to know it, since nothing in the product surfaces, warns about, or offers to clean up the conflicting file.

### Confidence
**Confirmed / reproduced.** Not a hypothesis — the contradictory content is visible, together, in this transcript's own operating context.

### Suggested acceptance test
1. On a machine with a pre-rebrand `~/.claude/rules/llm-router.md` (or any other now-orphaned rules artifact) present, run `chuzom install` (or trigger the automatic startup self-update) and assert the file is either removed or reconciled/merged so no contradictory instruction set survives.
2. `chuzom uninstall` must remove or at minimum warn about known-legacy rules/hook artifacts under `~/.claude/rules/` and `~/.claude/hooks/` that match Chuzom's historical naming lineage (`llm-router-*`, `tessera-*`), not only its current `chuzom-*` names.
3. Add a static/CI check enumerating every rules-file basename the product has ever shipped (via git history) and assert the current installer's uninstall/upgrade code references all of them, not just the current name.

### Impact flags
`[safety-promise-violation]` `[live-on-real-machine]` `[reproduced]` `[no-cleanup-path]` `[affects-all-legacy-lineage-users]`

---

## RED2-4-02 — Automatic rules self-update cannot propagate a claim fix because the fix commit never bumped the version marker; the documented "no re-install needed" promise is false for already-installed users

**Severity:** HIGH
**Category:** False completion / broken self-healing promise
**Affected promise:** Fabricated-magnitude claims, once found and fixed, actually reach existing installations ("...so existing users get rule updates ... without re-running install" — `check_and_update_rules()` docstring intent).

### Affected surface
- `src/chuzom/install_hooks.py::check_and_update_rules()` — version-gated rules sync, runs automatically on MCP server startup.
- `src/chuzom/rules/chuzom.md` line 1: `<!-- chuzom-rules-version: 6 -->`
- The real installed copy at `~/.claude/rules/chuzom.md` on this user's machine: also declares version 6, but (per this session's earlier direct read, preserved from before compaction) still contains the older "costs 50–100× less than Claude handling it directly" wording that the current repo template (confirmed by `Read` this session, line 22) has since softened to "can be much cheaper than Claude handling it directly."

### Reproduction
1. `git log --follow --format="%h %ad %s" -- src/chuzom/rules/chuzom.md` shows commit `ee9fe11` ("fix: iteration-3 Tier-A — honest downgrade render, claims, ledger order, quota bucket") is the commit that changed the wording.
2. The current repo template and the real installed file both declare `chuzom-rules-version: 6` — i.e. `ee9fe11` reworded the claim text but did **not** increment the version marker.
3. `check_and_update_rules()`'s gate is `if src_version <= dst_version: return None` — with both sides at 6, this is true, so the function is a silent no-op. The installed file is never touched by the automatic path.
4. A **separate, undocumented** escape hatch exists: `install()`'s manual rules-copy step (`install_hooks.py` ~707-717) does an unconditional `shutil.copy2(rules_src, rules_dst)` with no version check — so manually re-running `chuzom install` *does* fix it. But the product's own advertised behavior is that users get fixes automatically, without doing this.

### Root cause
Version-gate-vs-content mismatch: the fix changed content without changing the version number that gates whether that content is redistributed. This is a process gap (whoever authored `ee9fe11` didn't bump the marker), not a logic bug in the gate itself — the gate is doing exactly what it's coded to do.

### Customer impact
This is a **regression of a previously-claimed-fixed issue**: `docs/.chuzom/release-convergence/iteration-03/` paperwork shows this exact "50–100x" wording was flagged (RED2-3-02 / Q3-CLAIMS2) and marked fixed in `ee9fe11`. That verification checked the *source template* but apparently never checked whether the fix actually *reaches* an already-installed user via the mechanism the product itself advertises as sufficient. Any user who installed Chuzom before `ee9fe11` and has not manually re-run `chuzom install` since is still being shown a fabricated "50-100x" savings claim as part of their loaded global instructions, believing (per the product's own docstring promise) that they are automatically up to date.

### Confidence
**Confirmed via direct code read + real installed-file inspection**, both performed this session and the session before compaction. Not yet re-verified in *this exact* segment by re-reading the live file byte-for-byte (it was read in full pre-compaction), so flagged as high-confidence-but-not-re-executed-this-turn.

### Suggested acceptance test
1. CI check: for every commit touching `src/chuzom/rules/chuzom.md`'s body content, assert `<!-- chuzom-rules-version -->` was incremented relative to the previous commit touching that file. Fail the build otherwise.
2. Integration test: simulate an installed file at version N with old content, ship a new template at version N (content changed, version not bumped) — assert `check_and_update_rules()` either updates anyway (content-hash based, not just version-based) or the CI gate above prevents this state from ever being committed.

### Impact flags
`[false-completion-of-prior-fix]` `[silent-no-op]` `[undocumented-workaround-exists]`

---

## RED2-4-03 — `skills/routing/SKILL.md` ships a live, unguarded "saves ~50–100×" fabricated-magnitude claim, invisible to the claim-lint guard; delivery-to-real-users is unconfirmed

**Severity:** MEDIUM (downgraded from what would otherwise be HIGH, specifically because delivery to an actual user's machine could not be confirmed — see caveat below)
**Category:** Fabricated magnitude claim
**Affected promise:** No fabricated NNx/%% savings claims baked into files the product ships.

### Affected surface
`/Users/yaliandrona/Projects/Chuzom/skills/routing/SKILL.md` (47 lines, read in full this session):
```
| Simple factual question | `llm_query` | Gemini Flash / Groq — 50× cheaper than o3 |
...
## Cost Impact
Routing simple tasks to Gemini Flash instead of o3 saves ~50–100×.
```
Frontmatter description also still reads `"...route tasks to the cheapest capable model automatically via the llm-router MCP tools"` — another trace of the pre-rebrand identity (should say "chuzom MCP tools").

### Reproduction
1. `grep -n "50\|100\|saves\|×" skills/routing/SKILL.md` confirms both strings are present verbatim, unguarded, in current HEAD.
2. `scripts/lint_capability_claims.sh` (per `docs/correctness-reset/00_CURRENT_STATE.md` §8.1, independently spot-checked) only scans `README.md` + `.md` under `docs/Docs`. `skills/*.md` is out of scope. This was re-confirmed this session: `grep -n "\"skills\"\|'skills'\|SKILL.md" src/chuzom/*.py src/chuzom/commands/*.py` → no matches, i.e. nothing in the shipped runtime even references this directory, consistent with the lint script also never touching it.

### Delivery caveat (important — investigated and must be stated precisely)
This session traced whether this file actually reaches an end user's machine:
- `grep -n "skills/" src/chuzom/install_hooks.py src/chuzom/commands/install.py` → **empty**. Neither the primary Claude Code installer nor the multi-IDE installer (`commands/install.py`, covering opencode/gemini-cli/copilot-cli/openclaw/trae/vscode/cursor/factory) copies anything from `skills/`.
- `pyproject.toml` line 172 includes `/skills/` in what looks like a packaging/MANIFEST-style inclusion list — meaning it likely ships inside the **source/wheel package** — but that is distinct from being *installed into a user's Claude Code skills directory*.
- On this real machine, `find ~/.claude/skills -iname "*routing*" -o -iname "*llm-router*"` and `ls ~/.claude/skills/` found **no such file** — only an unrelated `council` skill.

**Conclusion:** this claim is live and unremediated in-repo, but is **not currently confirmed to reach any user via the audited install paths** on this evidence. It may still be surfaced to users who run Claude Code directly from within a checked-out Chuzom repo (project-local skill auto-discovery), which was not fully ruled out, but that is a materially different and narrower exposure than a claim shipped by the installer to every user. Framed conservatively as MEDIUM rather than HIGH pending that narrower confirmation.

### Root cause
Same structural gap as `00_CURRENT_STATE.md` §8.1 describes for other locations: the claim-guard's scope was defined around `README.md`/`docs/Docs`, and no equivalent guard (or install-path audit) was ever extended to `skills/*.md` when that directory was introduced.

### Confidence
**Confirmed for "claim exists in-repo, unguarded."** **Unconfirmed** for "reaches a real user" — explicitly labeled as such above, per audit honesty requirements.

### Suggested acceptance test
1. Widen `scripts/lint_capability_claims.sh`'s scan set to include `skills/**/*.md` (and any other directory later added to the product).
2. Add an explicit, tested install/no-install assertion for `skills/`: either (a) confirm and document that skills are never installed to a user's `~/.claude/skills/` and delete the stale `pyproject.toml` packaging reference if it's dead weight, or (b) if skills *are* meant to be delivered by some other means, wire that path into the same claim-guard coverage before it ships.

### Impact flags
`[fabricated-magnitude-claim]` `[guard-scope-gap]` `[delivery-unconfirmed]`

---

## RED2-4-04 — Nine orphaned `llm-router-*.py` hook scripts + 2 stray `.bak` files sit inertly in `~/.claude/hooks/` (same root cause as RED2-4-01, lower severity — confirmed dormant)

**Severity:** LOW / INFO
**Category:** Disk hygiene / product-lineage clutter (not a live behavior bug)

### Affected surface
`~/.claude/hooks/llm-router-agent-route.py`, `llm-router-auto-route.py`, `llm-router-bash-compress.py`, `llm-router-cc-usage-track.py`, `llm-router-enforce-route.py`, `llm-router-playwright-compress.py`, `llm-router-session-end.py`, `llm-router-session-start.py`, `llm-router-status-bar.py`, `llm-router-subagent-start.py`, `llm-router-usage-refresh.py` (all dated 8 Jul 12:19, same install event as the orphaned rules file), plus `chuzom-auto-route.py.bak.v24` and `chuzom-enforce-route.py.bak-pre060`.

### Reproduction
- `ls -la ~/.claude/hooks/` — files confirmed present this session.
- Inline inspection of `~/.claude/settings.json`'s active `hooks` block confirmed only `chuzom-*.py` files (+ one unrelated third-party `council-advisor.mjs`) are actually registered for any event (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `SubagentStart`, `PostToolUse`, `Stop`). None of the `llm-router-*.py` files appear anywhere in the registration.

### Why this is lower severity than RED2-4-01
Unlike `llm-router.md` (a rules file, which Claude Code auto-loads regardless of any registration), hook `.py` scripts only execute if wired into `settings.json`'s `hooks` block. These are confirmed **not** wired in — they are inert disk clutter, not a live behavioral bug. Grouped here because it's the same root cause (incomplete rebrand migration) and worth fixing in the same pass, and because a user who manually inspects `~/.claude/hooks/` (e.g., for security review) would reasonably be confused/alarmed to find a parallel set of scripts from a product name they don't recognize as still-current.

### Suggested acceptance test
`chuzom uninstall` (or a new `chuzom doctor --clean-legacy` command) enumerates and offers to remove any file under `~/.claude/hooks/` matching a known-historical Chuzom naming prefix that is not currently registered in `settings.json`.

### Impact flags
`[dormant]` `[confirmed-inert]` `[hygiene]`

---

## RED2-4-05 — `uninstall()` cannot deliver a genuinely clean uninstall for any user carrying legacy-lineage artifacts

**Severity:** LOW / INFO (documented here as a distinct, narrower point from RED2-4-01, since it's specifically about the uninstall promise rather than the ongoing contradiction)

### Affected surface
`src/chuzom/install_hooks.py::uninstall()` lines 765-820.

### Finding
`uninstall()` only removes `_RULES_DST / "chuzom.md"` (line 812-815) and only unregisters/deletes hooks listed in `_HOOK_DEFS` (the current, active hook set). It has no awareness of `llm-router.md` or `llm-router-*.py`. A user who runs `chuzom uninstall` today, expecting Chuzom fully removed from their machine, is left with the CRITICAL contradictory rules file from RED2-4-01 still active and loaded in every future Claude Code session — indefinitely, with the actual "chuzom" product gone and thus no future `chuzom install`/upgrade ever able to fix or even surface it again.

### Confidence
**Confirmed** via direct read of `uninstall()` this session.

### Suggested acceptance test
Same as RED2-4-01's acceptance test #2.

### Impact flags
`[incomplete-uninstall]` `[confirmed]`

---

## Areas investigated and found consistent with the product's promises (no violation found — stated explicitly per audit honesty requirements)

- **Daily-cap downgrade honesty / smart-soft-mode Claude-only fallthrough** (`router.py`, `types.py` — `LLMResponse.cap_downgraded`/`cap_downgrade_reason`, `_cap_downgrade_target()`): code-reviewed and appears to correctly implement the fix for prior findings RED2-2-01/RED2-2-02/RED2-3-01 (late-stage filter confines the chain to free-local providers, or Claude-only under smart/soft with no free-local available, or hard-blocks under hard mode). **Not independently live-reproduced this iteration** via a throwaway script — this remains a code-review-level confirmation, not an executed-and-observed one, and should be treated with correspondingly lower certainty than the fully-reproduced findings above.
- **UserPromptSubmit draft generation never silently escalates to a paid model**: `_FREE_DRAFT_PROVIDERS = frozenset({"ollama", "codex", "gemini_cli"})` and `_free_tier_draft_chain()` in `auto-route.py` structurally confine any pre-generated stateless draft to free/local providers, with explicit anti-fabrication commentary elsewhere in the file (e.g. "draft was generated (it would be fabrication)"). Reviewed at grep/structural level; the full body (~1188-3630) was not read in exhaustive line-by-line detail this iteration, so an edge-case bypass cannot be fully ruled out, but nothing found points to one.
- **Perplexity / research-task egress**: grepped across `onboard.py`, `install_hooks.py`, `benchmark_fetcher.py`, `config.py`, `token_budget.py`, `auto_profile.py`, `safe_config.py`. Consistent picture of an opt-in-only design — Perplexity is only added to the routing pool when the user has explicitly configured `perplexity_api_key` (`auto_profile.py` ~94-95/202-204). No evidence of a default/silent leak found. **Caveat:** a full end-to-end trace of the actual `llm_research` runtime call path was not completed this iteration (time-boxed out in favor of writing up the higher-confidence findings above) — this should be treated as "no red flag found on the evidence gathered," not as an exhaustively-proven clean result.
- **Cap-exhaustion error semantics**: `BudgetExceededError`, `CostBudgetExceeded`, `WallClockExceeded`, `DeadlineExceeded` (types.py) each have dedicated raise sites in `router.py` (~1806, 2820-2827, 3663-3671, 3763). Locations enumerated; exact message-string wording was not critically read for accuracy this iteration — open item, not a finding.
- **`replay.py`'s "SUMMARY — ... $1.847 saved (90%)" string**: confirmed to sit inside the module's top-of-file docstring under an explicit "Example output:" header — illustrative documentation, not a live hardcoded/user-facing value. Classified as benign, not a finding.
- **`src/chuzom/commands/install.py` (multi-IDE installer)**: spot-checked function inventory; no `--dry-run` flag exists anywhere in either installer. Not flagged as a standalone finding (dry-run absence is a UX/safety-margin gap, not a false claim — the product doesn't advertise a dry-run mode), but noted as an open area for a future iteration focused specifically on install-time reversibility.

## Explicitly out of scope / not reached this iteration (stated for transparency, not findings)
- Full `auto-route.py` `main()`/stdout-JSON-payload read (lines 1188-3630) — only structurally/grep reviewed.
- Full sweep of the ~15 additional `README.md` "savings/saves" grep hits beyond the sections already spot-checked.
- Whether `check_and_update_hooks()` (the hook-file analog of the buggy `check_and_update_rules()`) has ever suffered the same version-bump-missed defect for any specific active `chuzom-*.py` hook.
- Live, reproduced (not code-reviewed) exercise of the daily-cap downgrade path via a throwaway script.

---

*End of report. Written by RED-2, iteration 4, in READ-ONLY mode. No files were modified during this audit.*
