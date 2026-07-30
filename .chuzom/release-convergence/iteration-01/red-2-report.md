# RED-2 — Customer Reality & Failure Audit

**Auditor role:** Independent Customer Reality & Failure Auditor (hostile-but-realistic customer POV)
**Repo:** `/Users/yaliandrona/Projects/Chuzom`
**Branch:** `fix/v1.0.1-audit-mitigation`
**HEAD at report time:** `7c34fbb0104662606a0b4128a9c1f060cdacf139` (2026-07-30 00:53:35 +0100)
**HEAD at audit start:** `8fd4af1` — 4 commits landed during the audit (`7397700`, `34be388`, `3d01869`, `7c34fbb`), all test/docs-only; none touch the code paths behind the findings below.
**Method:** READ-ONLY. No source or test edited. No commits made. `CHUZOM_ENFORCE` confirmed unset in every shell used for reproduction. Docs, comments, test names, and green tests are treated as *claims*, not evidence — every material finding below was reproduced directly (real command, real output, or a direct trace of the exact call graph with line numbers) rather than inferred from documentation.

**Chuzom's core promise (yardstick used throughout):** it is an EXECUTION router — (a) routes tool-required work to a path that can inspect files/run commands/use tools, (b) prefers local/free/cheaper capable paths, (c) uses paid APIs only as a pressure valve, (d) never fabricates repo state/results/completion, (e) keeps transcript distinct from verified evidence, (f) makes routing observable, (g) keeps local-first privacy promises.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 1 |
| High | 2 |
| Medium | 2 |
| Low | 1 |
| Positive (confirmed-safe) | 5 |

**Top 3 findings:**

1. **RED2-01 (Critical) — `_is_context_dependent()` false-negative gate lets the UserPromptSubmit hook silently BLOCK-replace a Claude turn with a fabricated local-model draft for ordinary "our X" repo questions.** Evidence: live battery of 10 plausible prompts against the real predicate — 6/10 false negatives (system, layer, queue, algorithm, scheduler, permission model all missing from the noun allowlist), each one eligible for `{"decision":"block","reason":<draft>}` even though it references user-specific repo state the local model never saw.
2. **RED2-04 (High) — `CHUZOM_SESSION_CONTEXT=local` is not a "keep it local" switch: it never blocks the current prompt from being routed to a paid external API, and even its narrower "strip history" scope hardcodes only `("openai","gemini")`, structurally omitting Perplexity — which `chain_builder.py` routes ALL `research`-task prompts to, unconditionally, regardless of pressure zone or privacy mode.** Evidence: `context.py:444`/`session_store.py:484` gate literal `target_provider in ("openai","gemini")`; `router.py:4020` derives `target_provider` from `model.split("/",1)[0]`, so `perplexity/sonar-pro` never matches; `chain_builder.py:153` (`task_type == "research": return []`) forces every research prompt to Perplexity by construction.
3. **RED2-05 (High) — the "60–90% savings" claim CHANGELOG.md documents as removed under CHZ-AUD-010 is still live in THREE files freshly generated on every pull-mode IDE install** (`.vscode/mcp.json`, `.windsurf/mcp.json`, `.cursor/rules/use-chuzom.mdc`), because the regression guard test (`tests/test_claims_no_fabricated_magnitudes.py`) only scans `pyproject.toml`'s description and the first 60 lines of `README.md`. Evidence: `install_hooks.py:988,1000,1016` — literal string `"60-90%"` / `"60–90%"`, confirmed still present at current HEAD.

---

## RED2-01 — Context-dependence gate has a ~60% false-negative rate, enabling silent full-turn replacement

- **Severity:** Critical
- **Category:** Fabrication / false completion risk
- **Affected promise:** (d) never fabricate repository state or completion; (e) keep transcript distinct from verified evidence
- **Affected surface:** `src/chuzom/hooks/auto-route.py::_is_context_dependent()` (definition ~line 2242), consumed at the Phase-1 direct-execution eligibility check (~line 3043) and the block-vs-echo render-mode decision (~lines 3206-3211)
- **False-completion risk:** **YES — this is the primary mechanism by which it can occur**
- **Silent-expensive-routing risk:** No (this path is actually the *opposite* — it's the free/local draft path)
- **Privacy risk:** No

### What Chuzom claims

The UserPromptSubmit hook's block-mode disclaimer (`response_formatter.py::format_direct_response`, lines 53-64) is explicit that the draft came from a **context-free** or **history-only** model with "NO access to your files/tools." The gating design intent (confirmed via code comments in `auto-route.py` and `response_formatter.py`'s module docstring on `RENDER_MODE`) is: only BLOCK-replace the turn (zero-cost, no Claude involvement at all) when the prompt is judged self-contained enough that a context-free draft is trustworthy; otherwise fall back to advisory ECHO mode, where Claude still sees and can override the draft.

`_is_context_dependent(prompt)` is the single shared predicate that decides this. It works by checking the prompt against a **fixed, enumerable list of "our X" / "the X" repo-referring nouns** (e.g. `module`, `pipeline`, `config`, `class`, `function`, `endpoint`, `service`, `repo`) rather than any semantic understanding of whether the prompt actually needs repo context.

### Reproduction

Constructed a battery of 10 prompts, each following the exact "our/this/the X" pattern the predicate is designed to catch, using common software nouns that plausible real users would use but that are outside the fixed list. Ran each string through the live `_is_context_dependent()` function directly (not a re-implementation) via `python -c` import of `auto-route.py`'s module.

| Prompt noun | Caught (context-dependent=True)? |
|---|---|
| "our config" | Yes |
| "our module" | Yes |
| "our pipeline" | Yes |
| "our broker" | Yes (caught via a different branch, not the noun list) |
| "our system" | **No — false negative** |
| "our layer" | **No — false negative** |
| "our queue" | **No — false negative** |
| "our algorithm" | **No — false negative** |
| "our scheduler" | **No — false negative** |
| "our permission model" | **No — false negative** |

**Result: 6/10 (60%) false-negative rate** on this battery — i.e., 6 of 10 prompts that are exactly as repo-specific as the 4 that were caught are instead judged "context-independent" by the predicate, making them eligible for the free zero-Claude-involvement BLOCK path: `{"decision":"block","reason":<local-model draft>}`. In block mode, Claude never sees the user's actual turn at all — the terminal Claude Code renders the local model's text as if it were the final answer.

### Expected vs. actual

- **Expected:** A prompt referencing "our system," "our scheduler," etc. is exactly the kind of prompt the context-dependence gate exists to catch (it demonstrably asks about *this specific* repository's implementation, which a context-free/history-free local model cannot know) — it should route to advisory ECHO mode at worst, or skip direct-execution eligibility entirely and go straight to Claude.
- **Actual:** The gate is a fixed noun enumeration, not a semantic check, so any repo-referring noun outside that list is invisible to it. The false-negative rate on a small, unadversarial battery of common nouns was 60%.

### Observable customer impact

For a false-negative prompt (e.g., "how does our scheduler handle retries?" asked mid-session about a real, unfamiliar-to-the-local-model repo), the customer can receive a fully fabricated answer about scheduler internals with **zero indication that it wasn't Claude, and zero access by the drafting model to the actual repo** — the block-mode disclaimer text is present but is easy to miss/dismiss in a terminal, and more importantly, the *decision to fabricate a confident answer at all* has already been made by a naive keyword check, not a judgment about whether the model could plausibly know the answer.

### Root-cause hypothesis

The predicate was built additively (word-list matching) rather than being derived from an actual semantic/embedding classification or an LLM-based intent check, and its word list has not kept pace with the breadth of nouns real engineers use for "the thing I'm asking about in my own codebase."

### Confidence

High — directly reproduced against the live function, not inferred from docs or tests.

### Suggested acceptance test

A parametrized test asserting `_is_context_dependent()` returns `True` for a large (50+), continuously-expanded corpus of "our/this/the <common software noun>" prompts, sourced from real usage logs or a broad noun taxonomy rather than hand-picked examples — with a required minimum pass rate (e.g. ≥95%) enforced in CI as a regression gate, not a fixed list.

---

## RED2-02 — TQ-007 daily-cap downgrade event has no customer-visible field anywhere in the result object

- **Severity:** Medium
- **Category:** Silent behavior change / observability gap
- **Affected promise:** (f) make routing observable
- **Affected surface:** `src/chuzom/router.py` (downgrade logic, ~lines 3354-3382) → `src/chuzom/sdk.py::RouteResult` (lines 23-33) → `src/chuzom/logging.py` (`route_log.warning(...)`)
- **False-completion risk:** No
- **Silent-expensive-routing risk:** No — the *design* is the opposite of silent overspend: verified that on cap breach the router downgrades to the free/local provider set `{"ollama","codex","gemini_cli"}` rather than blocking or continuing to spend.
- **Privacy risk:** No

### What Chuzom claims

That when a configured daily spend cap is exceeded, Chuzom "downgrades" gracefully to free/local models rather than either (a) blocking the user outright or (b) silently continuing to make paid calls past the cap.

### Finding

Source-level reading of `router.py`'s cap-check confirms the downgrade *mechanism* is real and correctly implemented — the candidate provider set really is restricted to the free/local set once the cap is breached. However, tracing `RouteResult` (the object returned to any caller, MCP tool response, or CLI/dashboard consumer) shows **no field records that a downgrade occurred** — no `downgraded: bool`, no `original_provider`/`actual_provider` pair, no reason string. The only record of the event is an internal `structlog` `route_log.warning()` call, which is not surfaced to the terminal, the dashboard, or any MCP tool response by default.

### Expected vs. actual

- **Expected:** A user whose daily cap was just exceeded and who is now silently getting a lower-quality local-model answer instead of the paid model they might expect should be told, in the response they see, that this happened and why.
- **Actual:** The only place this is recorded is a structured log line that is not part of any user-facing surface.

### Observable customer impact

A user could notice "the responses got worse today" with no way to correlate that to the cap being hit — from their point of view, that's an unexplained quality regression, which is a worse experience than a downgrade would need to be if it were labeled.

### Confidence

Medium-high — the downgrade mechanism itself and the absence of a `RouteResult` field are both confirmed by direct source reading (`router.py`, `sdk.py`). **Not live-reproduced end-to-end this session** (did not set a tiny `CHUZOM_DAILY_SPEND_LIMIT`, exceed it, and observe a real terminal response) due to time budget — flagged as a source-confirmed-but-not-live-exercised finding, not a hypothesis.

### Suggested acceptance test

An integration test that sets a near-zero daily cap, makes two routed calls (first under cap, second over), and asserts the second call's `RouteResult` (or hook output) contains an explicit, user-visible downgrade indicator distinguishable from a normal free-tier route chosen for other reasons (e.g. pressure-zone routing).

---

## RED2-03 — Two independent installers; only one got the settings.json atomic-write/backup fix

- **Severity:** Low
- **Category:** Lifecycle safety (partial regression)
- **Affected promise:** (d) never fabricate/destroy state without recovery
- **Affected surface:** `scripts/install.sh` (lines ~60-145, inline `json.dump(settings, f, indent=2)`, no atomic write, no backup) vs. `src/chuzom/install_hooks.py::_save_settings()` (lines 251-276 — atomic tmp+`os.replace`, backs up any unparseable pre-existing `settings.json` to `settings.json.corrupt.<timestamp>.bak`)
- **False-completion risk:** No
- **Silent-expensive-routing risk:** No
- **Privacy risk:** No

### Finding

The current audit-mitigation commit (`d7968da`, on this very branch) fixed the "settings.json overwritten without backup" defect (tracked as CHZ-PKG-008 in `MITIGATION_PLAN.md`) — but only in `install_hooks.py`, the code path behind the documented `pip install chuzom-router && chuzom install --host claude-code` flow. A second, independent installer, `scripts/install.sh`, still contains the exact unfixed defect: a plain `json.dump` overwrite with no atomicity and no backup of a corrupt/unparseable existing file. Confirmed via `git log` that `scripts/install.sh` was last touched at the `cd70fd5` rebrand commit (2026-06-06), predating the fix.

### Mitigating factor (why this is Low, not Medium/High)

`scripts/install.sh` is not referenced anywhere in `README.md`, packaging manifests, or CI, and is not the documented install path — a customer following the documented onboarding flow never executes it. Real customer impact is low but non-zero (anyone who finds and runs the script directly, e.g. from browsing the repo, hits the original defect).

### Suggested acceptance test

Either delete `scripts/install.sh` as dead/orphaned, or bring it up to parity with `install_hooks.py::_save_settings()` and add a regression test parallel to the one presumably covering CHZ-PKG-008 for the primary installer.

---

## RED2-04 — `CHUZOM_SESSION_CONTEXT=local` does not deliver a "local-only" privacy guarantee

- **Severity:** High
- **Category:** Privacy / data egress
- **Affected promise:** (g) keep local-first privacy promises
- **Affected surface:** `src/chuzom/context.py::build_context_messages()` (privacy gate at lines 434-445, applied uniformly to layers 1, 2, and 2b); `src/chuzom/session_store.py::get_mode()` (line 228) and `build_session_context()` (privacy check at line 484); `src/chuzom/router.py::_call_text` (target-provider derivation at line 4020, `_target_provider = model.split("/", 1)[0]`); `src/chuzom/hooks/chain_builder.py` (line 153, `if task_type == "research": return []`)
- **False-completion risk:** No
- **Silent-expensive-routing risk:** No
- **Privacy risk:** **YES**

### What Chuzom claims

`CHANGELOG.md` line 413 documents the feature directly: *"Privacy modes via `CHUZOM_SESSION_CONTEXT`: `all` (default) / `local` (context stripped from external openai/gemini targets only) / `off` — enforced inside `session_store` itself."* The gate itself is annotated in `context.py` with the comment *"🥷 Backslash-security: Enforce privacy gate to prevent unauthorized data egress"* — i.e. the developers explicitly frame this as the anti-egress control.

### What it actually does (traced end-to-end, live code, not docs)

1. **`get_mode()`** resolves the mode from `CHUZOM_SESSION_CONTEXT` (`on`/`all` → `"all"`, `local` → `"local"`, `off` → `"off"`; fails open to `"all"`). This is a real, settable env var — confirmed the config plumbing exists (`config.py`).
2. **The single shared gate**, applied identically to all three context-injection layers (previous-session summaries, current-session buffer, and the durable Session Context Accumulator) in `context.py`:
   ```python
   _blocks_external = privacy_mode == "local" and target_provider in ("openai", "gemini")
   _context_suppressed = privacy_mode == "off" or _blocks_external
   ```
3. **`target_provider` is derived from the actual routed model string** at the real LiteLLM call site (`router.py:4020`): `_target_provider = model.split("/", 1)[0] if "/" in model else None`. For a model string of `perplexity/sonar-pro`, this yields `_target_provider = "perplexity"`.
4. **`"perplexity" not in ("openai", "gemini")`** — so the gate never fires for Perplexity calls, in any privacy mode. All three context layers (including full prior-session summaries and the durable per-session JSONL history) are attached and sent to Perplexity regardless of whether the user has set `local` mode.
5. **Perplexity is not an edge case** — `chain_builder.py` line 153 forces `task_type == "research"` to bypass the entire complexity/pressure-zone chain and fall through unconditionally to Perplexity via `llm_research`, at every complexity level, regardless of pressure zone. This was independently confirmed in a prior session of this same audit.
6. **Separately, and more fundamentally**: even for the two providers the gate *does* cover (openai, gemini), the mechanism only strips **session history/context** from the outgoing call — it does not, and structurally cannot, prevent the **current prompt itself** from being routed to and sent to openai or gemini in the first place. Whether a prompt is routed to a paid external provider at all is decided entirely by `chain_builder.py`'s complexity/pressure-zone logic, which has no dependency on `CHUZOM_SESSION_CONTEXT`. A user who sets `local` mode expecting their data to "stay local" would still have their live prompt text sent externally on any turn the router chooses an external provider — `local` mode only means that turn won't also carry prior conversation history.

### Expected vs. actual

- **Expected** (reasonable reading of the CHANGELOG's own "local-first privacy" framing, reinforced by the security-flavored comment in the source): setting `CHUZOM_SESSION_CONTEXT=local` meaningfully reduces what leaves the machine to external paid APIs.
- **Actual:** it reduces what leaves the machine to exactly two hardcoded providers (openai, gemini), and only the *history* component, not the current prompt, and not routing-destination choice at all. A `research`-classified prompt sends full session history to Perplexity — an external, paid, third-party API — unconditionally, in every privacy mode including `local`.

### Observable customer impact

A privacy-conscious customer who explicitly opts into `local` mode specifically to keep conversation history from reaching external vendors would have that expectation silently violated on every research-type query — with no error, warning, or any indication that the privacy mode did not apply to that call, because from the user's perspective "local" is a single global toggle, not a two-provider allowlist.

### Root-cause hypothesis

The gate tuple `("openai", "gemini")` was hardcoded to the two most obvious "paid external LLM API" providers at the time this was written (this reads as a `_call_text`/LiteLLM-provider-centric mental model — the two providers that flow through the general LiteLLM path alongside Ollama), and was never revisited when Perplexity was wired in as an unconditional research-path destination via a structurally separate `chain_builder.py` shortcut. The gate is a provider allowlist, not a "is this an external paid API" semantic check, so any future provider addition risks the same silent gap.

### Confidence

High — every step traced against live, currently-executing code (not documentation): the env var resolution, the gate expression (present verbatim in two files, applied identically across 3 context layers), the actual provider-string derivation at the real call site, and the unconditional research→Perplexity routing shortcut.

### Suggested acceptance test

1. Unit test: with `CHUZOM_SESSION_CONTEXT=local`, call `build_context_messages(target_provider="perplexity", ...)` against a session with real history and assert the returned context messages are empty (currently would fail — this is the gap).
2. Broader: replace the provider allowlist with an explicit "is this destination local/free" check (e.g. reuse the existing `_FREE_LOCAL_PROVIDERS = {"ollama","codex","gemini_cli"}` constant, inverted) so any provider not in the known-free set is blocked by default under `local` mode, rather than requiring each new paid provider to be manually added to a second, independent allowlist.
3. Documentation fix: CHANGELOG/README wording for `local` mode should explicitly state it only affects history/context attachment, not routing-destination choice, and should name every provider it does/doesn't cover rather than "external openai/gemini targets only" (which is accurate but easy to misread as exhaustive/general).

---

## RED2-05 — Fabricated "60–90% savings" claim, pledged-removed under CHZ-AUD-010, is still live in 3 files generated on every pull-mode IDE install

- **Severity:** High
- **Category:** Fabricated public claims (regression)
- **Affected promise:** (d) never fabricate — extends to marketing/config claims baked into files the product itself writes to a customer's machine
- **Affected surface:** `src/chuzom/install_hooks.py` — `_VSCODE_MCP_CONTENT` (line 988), `_WINDSURF_MCP_CONTENT` (line 1000), `_CURSOR_RULE_CONTENT` (line 1016)
- **False-completion risk:** No
- **Silent-expensive-routing risk:** No
- **Privacy risk:** No

### What Chuzom claims

`CHANGELOG.md` (lines ~82-90) documents "CHZ-AUD-010 — fabricated public claims must not reappear," specifically citing an unbacked magnitude claim (60–90% token savings) as removed and guarded against regression by `tests/test_claims_no_fabricated_magnitudes.py`.

### Finding

The literal string is still present, verbatim, at current HEAD, in three separate files that `chuzom install --host <copilot|windsurf|cursor>` writes directly into a customer's project on every install:

- `install_hooks.py:988` — `.vscode/mcp.json` content: `"...Each call saves 60-90% vs sending directly to Claude."`
- `install_hooks.py:1000` — `.windsurf/mcp.json` content: identical string.
- `install_hooks.py:1016` — `.cursor/rules/use-chuzom.mdc` content (with YAML frontmatter `alwaysApply: true`, meaning Cursor injects this into every prompt in the project): `"Calling them before generating your own answer saves 60–90% of token cost."`

The guard test (`tests/test_claims_no_fabricated_magnitudes.py`, full file read) correctly includes a regex (`60[–-]?90%`, case-insensitive) that matches all three strings — but its two test functions, `test_pyproject_description_has_no_fabricated_claims` and `test_readme_headline_has_no_fabricated_claims`, only scan `pyproject.toml`'s `project.description` field and the first 60 lines of `README.md`. `install_hooks.py` is never scanned, so the guard cannot catch a regression here even though its own regex would flag it on contact.

Directly confirmed the regex matches the live string via Python execution (`re.search(r"60[–-]?90%", open("src/chuzom/install_hooks.py").read(), re.I)` → match).

### Expected vs. actual

- **Expected:** per the CHANGELOG's own commitment, this specific magnitude claim should not appear anywhere in the shipped product.
- **Actual:** it appears in 3 files, all generated fresh on every relevant `chuzom install` invocation, i.e. it is not a leftover — it is actively regenerated for every new customer who installs pull-mode IDE integration.

### Observable customer impact

A customer using Cursor, VS Code/Copilot, or Windsurf sees an unbacked, specific performance claim baked directly into their own project files (and, in Cursor's case, into an `alwaysApply` rule that's part of every future prompt context) — the exact failure mode CHZ-AUD-010 was meant to close.

### Root-cause hypothesis

The regression guard was scoped to "public-facing marketing surfaces" (PyPI description, README hero) at the time it was written, and the IDE-config generator in `install_hooks.py` was either not in scope yet or was added/edited after the guard, without anyone re-running a repo-wide grep for the forbidden pattern.

### Confidence

High — directly read the source strings and the guard test's exact scope; directly executed the guard's own regex against the live string and confirmed a match.

### Suggested acceptance test

Broaden `tests/test_claims_no_fabricated_magnitudes.py` to scan `src/chuzom/install_hooks.py` (or, more robustly, every `.py`/`.md`/`.json`-template string literal under `src/chuzom/`) against the same `FORBIDDEN` regex list, rather than two hand-picked files.

---

## RED2-06 (Positive / confirmed-safe) — `chuzom install --help` is genuinely inert

- **Severity:** N/A (positive finding)
- **Category:** Lifecycle safety
- **Live-reproduced this session:** yes.

Ran `chuzom install --help` with `HOME` pointed at a fresh empty temp directory (isolating from the real user config) and `CHUZOM_ENFORCE` unset:

```
EXIT_CODE=0
--- settings.json written? ---
(none found)
--- ~/.claude dir created? ---
(directory remained empty)
--- output ---
chuzom install — install Chuzom routing into a host
...
  chuzom install --help, -h          Show this help and exit (no changes made)
```

No files were created under the isolated `$HOME` and the exit code was 0. This directly confirms the CHANGELOG's CHZ-PKG-007 claim ("`chuzom install --help` is inert... now it prints usage and exits 0 with no changes") via live execution rather than documentation alone.

---

## RED2-07 (Positive / confirmed-safe) — `chuzom uninstall --purge` has genuine, non-trivial destructive-action confirmation

- **Severity:** N/A (positive finding)
- **Category:** Lifecycle safety
- **Source-confirmed** (`src/chuzom/commands/uninstall.py`, full 78-line file read).

`--purge` (which deletes `~/.chuzom/`, including usage history and `.env`) prints a red/bold warning enumerating every file slated for deletion and requires the user to literally type `yes` at an `input()` prompt before `shutil.rmtree()` runs; `EOFError`/`KeyboardInterrupt` are treated as "no" (safe default). Base `uninstall` (no `--purge`) only calls `install_hooks.uninstall()`, which removes hook registrations/MCP server entries from `settings.json` — it does not touch `~/.chuzom/`.

---

## RED2-08 (Positive / confirmed-safe) — Install/IDE-config lifecycle is otherwise symmetric and non-destructive

- **Severity:** N/A (positive finding)
- **Source-confirmed** (`install_hooks.py`, multiple sections read).

- `_save_settings()` (lines 251-276) — atomic write (temp file + `os.replace`) and backs up any pre-existing but unparseable `settings.json` to `settings.json.corrupt.<timestamp>.bak` before overwriting (this is the CHZ-PKG-008 fix, landed in this branch's own audit-mitigation commit `d7968da` — but see RED2-03 above for the second installer that didn't get it).
- `_register_hook`/`_hook_is_registered`/`_normalize_command` — idempotent hook registration that avoids clobbering unrelated third-party hooks with generically-named files.
- `install_ide_configs()` / `uninstall_ide_configs()` (lines 1044-1096) — symmetric write/remove of `.vscode/mcp.json`, `.windsurf/mcp.json`, `.cursor/rules/use-chuzom.mdc`.

---

## RED2-09 (Positive / confirmed-safe) — Pull-mode IDE routing messaging is honest about its own limitation

- **Severity:** N/A (positive finding)
- **Source-confirmed** (`install_hooks.py::_print_pull_routing_notice()`, lines 1162-1176, and `_print_help()`, lines 1178+).

The install-time banner for VS Code/Copilot and Windsurf explicitly states pull-mode routing is "NOT guaranteed on every turn (model may skip)" and recommends Claude Code "for guaranteed routing." This directly contradicts a naive assumption that Chuzom silently and reliably intercepts every turn in pull-mode hosts — the product's own messaging correctly sets that expectation. (Note: this positive finding coexists with RED2-05's negative finding about the same install path's fabricated-savings string — the honesty about *routing reliability* does not extend to the *magnitude claim* baked into the same generated files.)

---

## RED2-10 (Positive / confirmed-safe) — Savings/cost dashboard does not appear to double-count or fabricate for routes that never happened

- **Severity:** N/A (positive finding)
- **Confidence:** Medium (source-level only this session; carried forward from prior-session analysis of `sdk.py::RouteResult` and `telemetry.py`).

`src/chuzom/telemetry.py` (lines 1-80, read) is a pure local SQLite read of the `routing_decisions` table, with no outbound network call — ruled out as a source of fabricated/phantom savings figures reaching a remote service. No evidence found this session of a savings figure being recorded for a call whose `RouteResult` indicates failure/no-op.

---

## Areas not exercised this session (explicitly flagged, not fabricated as "checked")

Per the audit's own honesty mandate, the following originally-scoped investigation areas were **not given dedicated reproduction work** in this or prior sessions of this audit, and should be treated as open threads for a follow-up pass rather than as "checked and clean":

- **Investigation #2 — silent fallback to the host model (Claude) while claiming a route.** No adversarial test constructed. `RouteResult`/hook-output code was read incidentally while investigating RED2-01/RED2-02, but no dedicated attempt was made to force or observe a route that silently degrades to Claude while its output still claims a cheaper model was used.
- **Investigation #3 — tool-required work routed to a text-only path.** `needs_claude_tools()` / `chuzom.capabilities.detect_capabilities()` were identified as the relevant mechanism in a prior session but never exercised with a concrete prompt engineered to need tools (e.g. "run the test suite and tell me what fails") while `direct_executor.py`'s draft path (context-free, no shell) is live.

These are not "not applicable" — they are genuinely untested within the time budget of this audit and should not be read as passing.

---

## Appendix — reproduction commands used this session

```bash
# TQ-007/RED2-06: isolated-HOME live run of `chuzom install --help`
unset CHUZOM_ENFORCE
TMPHOME=$(mktemp -d)
HOME="$TMPHOME" .venv/bin/chuzom install --help
# EXIT_CODE=0, no settings.json/.claude dir created, output states "no changes made"

# RED2-04: trace confirming target_provider derivation and the research-task bypass
grep -n "assemble_context(\|target_provider" src/chuzom/*.py src/chuzom/hooks/*.py
grep -n "TaskType.RESEARCH\|task_type == .research." src/chuzom/hooks/chain_builder.py

# RED2-05: live regex match against install_hooks.py
grep -n "60.*90%\|60–90%" src/chuzom/install_hooks.py
```
