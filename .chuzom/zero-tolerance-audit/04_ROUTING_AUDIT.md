# RED-1 Routing Audit — Chuzom v1.1.1 (`c2c2882`)

Audited by: RED-1 (adversarial, zero-tolerance)
Worktree: `/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882`
Interpreter: `<worktree>/.venv-audit/bin/python` only. `Chuzom/.venv` never touched.
No reasoning was routed through `mcp__chuzom__*` (explicit conflict-of-interest prohibition honored throughout).

**Note on finding IDs**: this codebase already contains code comments referencing `RED1-01` through `RED1-11` and `RED2-01` through `RED2-11` from a *prior* audit round (e.g. `router.py:3736`, spend-cap chain-ordering bugs — unrelated to anything below). To avoid collision, all findings in this document are numbered `RED1-20` and up. They are new findings from this pass, not reopened old ones, though RED1-20/21 below are arguably the *same defect class* the HEAD commit's own `CHZ-SURF-01` claims to have fixed — see each finding's "Can this defect class exist elsewhere" section.

---

## Executive summary

The HEAD commit's flagship claim is **CHZ-SURF-01**: "resolve every emitted tool name against the active tier." That claim is **false as stated**. Direct execution against the live worktree proves:

1. The **primary onboarding artifact for 10 of 11 non-Claude-Code hosts** (`src/chuzom/rules/*.md`, installed via `cli._append_routing_rules()`) is written to disk **byte-for-byte with zero resolver call of any kind** — not `localize()`, not `route_tool()`, nothing. Every one of the 13 files in that directory teaches at least one tool name that is unregistered under the shipped default tier (`consolidated`); most teach 6–8 unregistered names simultaneously.
2. Even the in-code templates that *do* call `localize()` (`cli._COPILOT_AGENT_CONTENT`, `install_hooks._CURSOR_RULE_CONTENT`) still ship a live, unresolved `llm_reason(...)` reference, because `llm_reason` is absent from `tool_surface.DEPRECATED_TOOLS`, `KNOWN_TOOLS`, and `EMITTABLE_TOOLS` simultaneously — the exact three sets that gate `resolve()`'s degradation logic, `localize()`'s rewrite scope, and the `unregistered()` CI/startup guard's default scan set.
3. **Both CI guards that exist specifically to catch this class of bug pass clean on the live, broken worktree.** `scripts/lint_tool_surface.py` reports `CHZ-SURF-01: clean (409 files checked)`. `scripts/trace_northstar.py` reports `TRACE CLEAN`. Neither is lying about what it checked — both are correct but too narrow, and their narrowness is itself undocumented to a reader who trusts the green output.

This is not a cosmetic doc bug. A user on Cursor, VS Code/Copilot, Gemini CLI, Copilot CLI, OpenCode, OpenClaw, Trae, Pi, or Codex CLI who installs Chuzom today and follows the routing table their own tool was just taught will get `Error: No such tool available` for the majority of task categories, on the very first attempt, with the shipped default configuration.

---

## RED1-20 — `src/chuzom/rules/*.md` install path applies zero tool-name resolution (13 files, 10 hosts)

```
ID: RED1-20
Severity: P0
Confidence: PROVEN
Area: Tool surface drift / host integration
Title: Every per-host onboarding rules file is installed verbatim with no resolver pass; all 13 teach at least one unregistered tool name under the shipped default tier
Claim/Invariant violated: HEAD commit CHZ-SURF-01 — "resolve every emitted tool name against the active tier"
Observed behavior:
  `cli._append_routing_rules(dest_path, rules_filename)` (src/chuzom/cli.py:125-169) does:
      rules_content = rules_file.read_text()
      ...
      dest_path.write_text(rules_content)   # or f.write("\n\n" + rules_content) on append
  There is no call to `localize()`, `route_tool()`, `resolve()`, or any other function
  from `chuzom.tool_surface` anywhere in this function or its call sites. Confirmed by
  reading the full function body and grepping its 10 call sites in cli.py.
  Executed against the live worktree (CHUZOM_SLIM unset -> "consolidated", the shipped
  default): every one of the 12 rules/*.md files plus chuzom.md contains at least one
  bare tool-name reference that `tool_surface.is_registered()` reports as NOT registered:
    chuzom.md            -> llm_query, llm_code, llm_analyze, llm_research, llm_generate
    codex-rules.md        -> + llm_reason, llm_auto
    copilot-cli-rules.md  -> + llm_reason, llm_savings, llm_auto
    copilot-rules.md      -> + llm_reason, llm_auto
    cursor-rules.md       -> + llm_reason, llm_auto
    desktop-rules.md      -> + llm_reason, llm_health, llm_auto
    gemini-cli-rules.md   -> + llm_reason, llm_savings, llm_auto
    gemini-rules.md       -> + llm_reason, llm_auto
    openclaw-rules.md     -> + llm_reason, llm_auto
    opencode-rules.md     -> + llm_reason, llm_auto
    pi-rules.md           -> + llm_reason, llm_auto
    trae-rules.md         -> + llm_reason, llm_savings, llm_auto
    vscode-rules.md       -> + llm_reason, llm_savings, llm_auto
  Under CHUZOM_SLIM=consolidated the ONLY registered tools are:
    chuzom_admin, chuzom_agent_route, chuzom_agent_start_session, chuzom_session,
    chuzom_status, llm, llm_act, llm_audio, llm_edit, llm_image, llm_route
  i.e. `llm_query`, `llm_code`, `llm_analyze`, `llm_research`, `llm_generate` — the
  five names EVERY SINGLE rules file recommends by name, in a routing table, as the
  primary how-to-call-chuzom instruction — are not callable tools under the default
  install. They ARE resolvable in principle (they're DEPRECATED_TOOLS keys, and
  localize() proven to rewrite them correctly elsewhere — see RED1-21) but this
  install path never runs that rewrite.
Expected behavior: every tool name taught to a host model in an installed artifact
  should resolve to a name that is actually registered under the tier the artifact
  was generated for, the same guarantee CHZ-SURF-01 claims for "every emitted tool
  name."
Why this matters to a real user: this is not a doc typo. These files ARE the
  system prompt / rules context the host model reads to learn how to call chuzom.
  A Cursor, Copilot, Gemini CLI, Codex CLI, OpenCode, OpenClaw, Trae, or Pi user
  who installs chuzom today, asks a coding question, and lets their host model
  follow the routing table it was just taught will get a tool-not-found error on
  the first attempt for 5 of 6 documented task categories. The entire value
  proposition of the product (route cheap, save money) fails at the first
  invocation for the majority of its supported hosts.
Exact reproduction:
  cd <worktree>
  ./.venv-audit/bin/python - <<'PY'
  import sys; sys.path.insert(0, "src")
  from chuzom import tool_surface as ts
  print(ts.active_slim())  # -> consolidated
  print(ts.is_registered("llm_code", "consolidated"))  # -> False
  PY
  # then inspect any file under src/chuzom/rules/*.md — e.g.:
  grep -n '`llm_code' src/chuzom/rules/vscode-rules.md
  # then confirm the install function never resolves it:
  grep -n "localize\|route_tool\|resolve(" src/chuzom/cli.py | grep -A2 -B2 _append_routing_rules
  # (no hits inside the function body)
Evidence:
  - src/chuzom/cli.py:125-169 (`_append_routing_rules`, full body, zero resolver call)
  - src/chuzom/cli.py: 10 call sites, `grep -n '_append_routing_rules(' src/chuzom/cli.py`
  - src/chuzom/rules/*.md (13 files) — table rows with bare backtick-wrapped tool names
  - /Users/yaliandrona/Projects/Chuzom/.chuzom/zero-tolerance-audit/evidence/red1/repro_full_tool_surface_scan.py
  - /Users/yaliandrona/Projects/Chuzom/.chuzom/zero-tolerance-audit/evidence/red1/repro_full_tool_surface_scan.OUTPUT.txt (full captured run, all 13 files enumerated with their exact unresolved-name lists)
Root cause: `_append_routing_rules()` was written as a pure file-copy utility before
  the tool_surface/localize() resolver machinery existed, and was never updated when
  that machinery was introduced. It is structurally identical in intent to the
  in-code `localize("""...""")`-wrapped string constants elsewhere in the same file
  (`_COPILOT_AGENT_CONTENT`, `kimi_rules`) but was missed because it reads from an
  external template file rather than an inline string literal — a different code
  shape that neither a human reviewer skimming for `localize(` call sites nor
  `lint_tool_surface.py`'s AST scan of `cli.py`'s own string constants would think
  to check (the guarded strings live in a DIFFERENT FILE, loaded at runtime).
Why existing tests/gates missed it:
  `scripts/lint_tool_surface.py` scans `.py`/`.yml`/`.yaml`/`.sh` files for raw
  GUARDED-name string literals; it does not scan `.md` files at all (confirmed:
  `main()`'s default scan set is `src/chuzom/**/*.py` + `.github/workflows/*` +
  `scripts/*.sh` — no `src/chuzom/rules/*.md` anywhere in scope).
  `scripts/trace_northstar.py` only exercises `hooks/auto-route.py`'s hint-emission
  path against the live server registry; it has no code path that touches `cli.py`'s
  install functions or the rules/*.md files at all.
  No test in the suite renders `_append_routing_rules()`'s output and checks it
  against `tool_surface.is_registered()` (grep of `tests/` for `_append_routing_rules`
  and for `rules/*.md` file names turned up no such test — not independently
  re-verified by a full test-suite read in this pass, flagged as NOT FULLY TESTED
  below).
Blast radius: 10 of 11 supported hosts' PRIMARY onboarding artifact (VS
  Code/Copilot via `.github/copilot-instructions.md`, Cursor via
  `~/.cursor/rules/chuzom.md`, OpenCode, Gemini CLI, Copilot CLI, OpenClaw, Trae,
  Pi, Codex CLI). Only Claude Code (which uses a different, hook-directive-based
  mechanism per `trace_northstar.py`'s proven-clean scope) and whichever hosts
  don't consume these specific files are unaffected by this specific channel.
Can this defect class exist elsewhere?: Yes — see RED1-21 (in-code
  `localize()`-wrapped templates still miss `llm_reason`) and RED1-22
  (`lint_tool_surface.py`'s own GUARDED tuple independently drifts from
  DEPRECATED_TOOLS). This is a *pattern*: every place a tool name can be taught to
  a host is a separate, hand-maintained channel, and the audit found three
  structurally distinct channels (raw file copy, localize()-wrapped inline
  constant, and a hand-maintained CI allowlist) each independently under-covered.
  A fourth channel (`install_hooks._VSCODE_MCP_CONTENT`) was checked and found
  CORRECT — it was rewritten at some point to use the new `llm(task="code")`
  syntax directly rather than a legacy bare name, proving the fix pattern that
  should have been applied everywhere was known and used inconsistently.
Recommended systemic fix: (1) route `_append_routing_rules()`'s file content
  through `localize(rules_content, active_slim())` before writing, same as every
  other generated template. (2) Extend `lint_tool_surface.py`'s scan set to include
  `src/chuzom/rules/*.md` (and any other `.md` template directories that get
  installed verbatim — audit further). (3) Add `llm_reason` and every other
  genuinely-emittable-but-not-DEPRECATED_TOOLS name to a canonical, single set, and
  make `EMITTABLE_TOOLS`/`DEPRECATED_TOOLS`/`lint`'s `GUARDED` all derive from that
  one set instead of being three independently hand-maintained collections (see
  RED1-22 for the third one).
Regression test that would actually prevent recurrence: a test that, for every
  file `cli._append_routing_rules()` can write (enumerate via the 10
  `rules_filename` call-site arguments) and for every shipped tier
  (`core`/`routing`/`consolidated`), renders the installed content and asserts
  `tool_surface.is_registered(name, tier)` is True for every backtick-wrapped
  `llm_*`/`chuzom_*` token found in it. This test would fail today on all 13
  files under `consolidated` and must pass before this is closed.
Release blocking? YES
```

---

## RED1-21 — `llm_reason` is invisible to `resolve()`, `localize()`, and `unregistered()` simultaneously; CHZ-SURF-01's in-code fix is incomplete

```
ID: RED1-21
Severity: P1
Confidence: PROVEN
Area: Tool surface drift
Title: llm_reason is absent from DEPRECATED_TOOLS, KNOWN_TOOLS, and EMITTABLE_TOOLS at once, so it survives localize() untouched in every template that mentions it
Claim/Invariant violated: CHZ-SURF-01
Observed behavior: `llm_reason` is a real, importable tool function
  (`src/chuzom/tools/text.py`, gated by `should_register("llm_reason")`) that is
  registered ONLY under `CHUZOM_SLIM=off` — never under core/routing/consolidated.
  It does not appear in `tool_surface.DEPRECATED_TOOLS` (24 keys), so:
    - `resolve("llm_reason", "consolidated")` hits the "unknown name" passthrough
      branch and returns the name UNCHANGED (confirmed: `call.name == "llm_reason"`,
      `is_registered(call.name, "consolidated") == False`).
    - `localize(text, "consolidated")` — both its call-form regex pass and its
      bare-name replacement loop are scoped to `DEPRECATED_TOOLS.keys()` only —
      leaves any occurrence of `llm_reason` byte-for-byte unresolved. Proven on
      the EXACT text shipped in three separate places:
        cli.py:192  (`_COPILOT_AGENT_CONTENT`, -> .github/agents/chuzom.agent.md)
        cli.py:495  (kimi_rules -> KIMI.md)
        install_hooks.py:1319 (`_CURSOR_RULE_CONTENT` -> <project>/.cursor/rules/use-chuzom.mdc)
      All three are wrapped in `localize(...)` at call time — i.e. the author DID
      apply the CHZ-SURF-01 fix mechanism to these strings — and it still ships
      broken, because the fix's scope (DEPRECATED_TOOLS) does not include this name.
    - `unregistered()`, the CI/startup guard, scans `EMITTABLE_TOOLS` by default,
      which also omits `llm_reason` — so the guard cannot flag it even in principle.
Expected behavior: any tool name that is taught in a `localize()`-protected
  template but is not actually registered under the tier that template targets
  should either be rewritten to a real substitute or cause the guard to fail
  loudly (per tool_surface.py's own module docstring: "an unroutable name fails
  loudly instead of silently costing money").
Why this matters to a real user: Copilot (via chuzom.agent.md), Kimi Code (via
  KIMI.md), and Cursor project rules (via use-chuzom.mdc) users are taught to
  call `llm_reason(...)` for "deep reasoning / proofs / root cause" tasks — one of
  the higher-value, more expensive task categories the router exists to route
  correctly — and it will fail with "no such tool" on the shipped default tier,
  every single time, with no fallback.
Exact reproduction: see
  /Users/yaliandrona/Projects/Chuzom/.chuzom/zero-tolerance-audit/evidence/red1/repro_llm_reason_surface_gap.py
  Run: <worktree>/.venv-audit/bin/python repro_llm_reason_surface_gap.py
  All 10 numbered assertion blocks pass; the script raises AssertionError if the
  bug is ever fixed accidentally-in-a-way-that-breaks-the-repro, so it is a
  faithful, currently-green reproducer of the live defect.
Evidence:
  - src/chuzom/tool_surface.py (DEPRECATED_TOOLS dict, `resolve()`, `localize()`, `unregistered()`)
  - src/chuzom/tools/text.py (`def llm_reason(...)`, `should_register("llm_reason")` gate)
  - src/chuzom/cli.py:192, 495
  - src/chuzom/install_hooks.py:1319
  - evidence/red1/repro_llm_reason_surface_gap.py + .OUTPUT.txt (full captured run)
Root cause: `DEPRECATED_TOOLS` was populated with the specific legacy names known
  at the time CHZ-SURF-01 was authored (the 5 completion tools + savings/admin/
  session-lifecycle tools that were consolidated). `llm_reason` is a NEWER or
  SEPARATELY-tiered tool (only ever existed under the `off`/legacy full surface)
  that was never a "deprecated" name being collapsed into a door — it's simply an
  optional tool that isn't in the default tier at all. The fix's mental model
  ("rewrite legacy names to their new door") doesn't cover "name that was never
  legacy, just isn't registered under this tier."
Why existing tests/gates missed it: same root cause as RED1-20's guard analysis —
  `lint_tool_surface.py`'s `RESOLVER_CALLS` trust model exempts ANY string passed
  to `localize()` from further scanning, on the assumption that `localize()`
  handles it. That assumption is false for this specific name. This is a
  structural blind spot in the lint's own design, not just a missed entry (see
  RED1-22).
Blast radius: 3 confirmed emission sites (Copilot agent file, KIMI.md, Cursor
  project rules), likely more given the same name appears in all 13 rules/*.md
  files (RED1-20) and `install_hooks._WINDSURF_MCP_CONTENT` was not checked in
  this pass (NOT TESTED — flagged below).
Can this defect class exist elsewhere?: Yes — any tool that exists in the full
  (`off`-tier) surface but isn't a DEPRECATED_TOOLS key and isn't in the target
  tier's tool set is invisible to this entire mechanism. Not audited: whether
  other `off`-only tools (full grep of `should_register` gates in
  `src/chuzom/tools/*.py` was not performed in this pass) are referenced in any
  template — llm_reason was found via the mandate's own hint plus grep, not via
  an exhaustive enumeration of all off-tier-only tools. This is explicitly a gap
  in this audit, not a claim that llm_reason is the only instance.
Recommended systemic fix: same as RED1-20 fix #3 — unify the source of truth so
  a template author cannot introduce a new tool reference that silently escapes
  all three protection mechanisms at once.
Regression test that would actually prevent recurrence: for every tool name
  `should_register` can gate in `src/chuzom/tools/*.py`, assert it is either (a)
  registered under at least one of core/routing/consolidated, or (b) present in
  DEPRECATED_TOOLS with a door that IS registered, or (c) explicitly allowlisted
  as "off-tier only, never taught in any template" with a companion test that
  greps all template sources (rules/*.md + in-code constants) and fails if that
  name appears anywhere.
Release blocking? YES
```

---

## RED1-22 — `lint_tool_surface.py`'s trust model and hand-maintained allowlist both independently drift from the thing they're supposed to guard

```
ID: RED1-22
Severity: P1
Confidence: PROVEN
Area: CI gate integrity
Title: The CHZ-SURF-01 CI guard passes clean on a worktree proven broken by RED1-20/21, for two independent structural reasons
Claim/Invariant violated: CHZ-SURF-01 ("resolve every emitted tool name..."), and
  the implicit claim that a green `scripts/lint_tool_surface.py` run means the
  class of bug it names is absent.
Observed behavior: executed for real against the live worktree:
    ./.venv-audit/bin/python scripts/lint_tool_surface.py
    -> "CHZ-SURF-01: clean (409 files checked)"
  This is true and not a bug in the lint's execution — but it is misleading
  about coverage, for two independent, provable reasons:
  (1) `main()`'s default scan set is `src/chuzom/**/*.py` + `.github/workflows/*`
      + `scripts/*.sh`. It never scans `src/chuzom/rules/*.md` — the exact file
      family RED1-20 proves is broken. Markdown is not a scanned extension at all.
  (2) Even within scanned `.py` files, `RESOLVER_CALLS = {"route_tool",
      "route_call", "route_call_with_complexity", "call_parts", "resolve",
      "resolve_name", "is_registered", "_door_for", "localize",
      "_localize_banner"}` causes `_resolver_args()` to walk into and EXEMPT any
      string literal passed as an argument to `localize(...)` from the raw-string
      GUARDED-name scan — on the assumption that `localize()` already made it
      safe. RED1-21 proves that assumption is false for `llm_reason`. This is a
      structural blind spot: the lint cannot catch a scope gap inside the very
      function it trusts to have already fixed the problem.
  (3, secondary but confirmed) the lint's own hardcoded `GUARDED` tuple (13
      names) is independently missing 11 of `DEPRECATED_TOOLS`'s 24 keys —
      `llm_providers`, `llm_gain`, `llm_dashboard`, `llm_import_profile`,
      `llm_cache_clear`, `llm_policy`, `llm_budget`, `chuzom_agent_list`,
      `chuzom_agent_check_budget`, `chuzom_agent_complete_session`,
      `chuzom_agent_lineage` — all 11 confirmed unregistered under
      core/routing/consolidated. A raw (non-localize()-wrapped) hardcoded
      occurrence of any of these 11 names anywhere in a scanned `.py` file would
      sail through the lint completely undetected, violating `tool_surface.py`'s
      own stated "single source of truth" design principle (GUARDED duplicates
      DEPRECATED_TOOLS.keys() by hand instead of importing it).
Expected behavior: a CI guard whose entire purpose is "prove every emitted tool
  name resolves against the active tier" should either scan every file type that
  can emit a tool name, or explicitly and loudly document what it does NOT cover
  so a reader doesn't mistake "clean" for "safe."
Why this matters to a real user: nobody currently reviewing this codebase's CI
  output would learn about RED1-20 or RED1-21 from a red X — they'd see green and
  move on. The gate that exists specifically to prevent silent tool-name drift is
  itself silently incomplete in exactly the same way.
Exact reproduction:
  cd <worktree>
  ./.venv-audit/bin/python scripts/lint_tool_surface.py
  # -> "CHZ-SURF-01: clean (409 files checked)" despite RED1-20/21 being live bugs
  # GUARDED vs DEPRECATED_TOOLS diff:
  ./.venv-audit/bin/python evidence/red1/repro_llm_reason_surface_gap.py
  # section 9-10 prints the exact 11-name diff
Evidence:
  - scripts/lint_tool_surface.py (GUARDED tuple, RESOLVER_CALLS set, main()'s scan-path construction, _resolver_args())
  - evidence/red1/lint_tool_surface_ACTUAL_RUN.txt (captured real "clean" output)
  - evidence/red1/repro_llm_reason_surface_gap.OUTPUT.txt (section 9-10, GUARDED vs DEPRECATED_TOOLS diff)
Root cause: the lint was built to catch *hardcoded raw strings that bypass the
  resolver*, and correctly does that for the specific 13 names someone thought to
  list. It was never extended to (a) treat "passed through localize()" as "proven
  safe" rather than "assumed safe," or (b) cover non-Python template files.
Why existing tests/gates missed it: this IS the gate. There is no second-order
  gate checking the gate's own scan coverage.
Blast radius: every future tool-name emission bug of this shape (new deprecated
  tool, new template file type, new install path) is equally invisible to CI
  until a human manually greps for it, exactly as this audit had to.
Can this defect class exist elsewhere?: Yes — any CI lint whose allowlist is
  hand-maintained rather than derived from the same source of truth as the
  runtime behavior it's checking is subject to this exact drift. Worth auditing
  other `scripts/lint_*.py` files for the same anti-pattern (NOT TESTED in this
  pass — flagged below).
Recommended systemic fix: (1) `GUARDED = tuple(tool_surface.DEPRECATED_TOOLS)` —
  derive, don't duplicate. (2) Change the RESOLVER_CALLS trust model: instead of
  exempting `localize()`-wrapped strings unconditionally, actually RUN
  `localize()` on extracted string constants at lint time and re-scan the OUTPUT
  for remaining GUARDED-name matches — a name that survives localize() should
  still fail the lint. (3) Extend the scan to `src/chuzom/rules/*.md` and any
  other installed template file type.
Regression test that would actually prevent recurrence: a test asserting
  `set(lint_tool_surface.GUARDED) == set(tool_surface.DEPRECATED_TOOLS)`, plus a
  lint self-test that plants a known-bad `llm_reason`-style name inside a
  `localize()`-wrapped string in a fixture file and asserts the lint FAILS on it
  (a red-team test of the lint itself — currently absent, since the lint passes
  clean on the actual live bug).
Release blocking? YES
```

---

## RED1-23 — `scripts/trace_northstar.py`'s clean result creates false confidence beyond its actual (narrow, correct) scope

```
ID: RED1-23
Severity: P2
Confidence: PROVEN
Area: CI gate integrity / documentation honesty
Title: The other CHZ-SURF-01 verification script only covers the hooks/auto-route.py -> server hint path, and nothing in its output communicates that scope boundary to a reader
Observed behavior: `scripts/trace_northstar.py` runs the real
  `hooks/auto-route.py` hook against 3 hardcoded prompts, extracts the emitted
  tool hint, and checks it against `chuzom.server.mcp.list_tools()` (a live
  registry query, correctly NOT using `tool_surface.py` as its own oracle — this
  part of its design is sound and deliberately avoids the "two components agree
  on the same wrong assumption" trap the audit mandate calls out). Executed for
  real: `TRACE CLEAN — every emitted hint names a tool the server registers`.
  This is TRUE and not misleading about what it tested. But it has zero code path
  that touches `cli.py`'s or `install_hooks.py`'s install-time template
  generation — a structurally separate emission channel — so its "clean" result
  says nothing about RED1-20/21/22, and nothing in its output or the 3 hardcoded
  prompts communicates that boundary.
Expected behavior: a script named `trace_northstar` that's positioned (by the
  HEAD commit's own framing) as proof of CHZ-SURF-01 should either cover all
  emission channels or state explicitly, in its own output, which channels it
  does and doesn't cover.
Why this matters to a real user: same false-confidence mechanism as RED1-22, one
  layer up — a maintainer citing "trace_northstar passes" as evidence the
  tool-surface problem is solved would be citing evidence that doesn't speak to
  the actual, live defect.
Exact reproduction:
  ./.venv-audit/bin/python scripts/trace_northstar.py --tier consolidated
  # -> TRACE CLEAN (true, but scope-limited to the hook-directive path)
Evidence:
  - scripts/trace_northstar.py (full read: server_registered_tools(), run_hook(), CASES — only invokes hooks/auto-route.py)
  - evidence/red1/trace_northstar_consolidated.txt (captured real run)
Root cause: scope creep of trust — a correctly-scoped test being read as a
  broader guarantee than it provides.
Why existing tests/gates missed it: N/A — this finding is about the gate itself.
Blast radius: documentation/confidence risk, not a runtime defect by itself.
Can this defect class exist elsewhere?: Likely — any narrowly-scoped
  verification script whose name implies broader coverage than it has.
Recommended systemic fix: rename or annotate the script's output to state its
  scope explicitly ("hook-directive path only; does not cover cli.py/
  install_hooks.py template generation"), and add a companion trace for the
  install-time channel.
Regression test that would actually prevent recurrence: N/A (this is a
  documentation/scope-honesty fix, not a code-behavior fix).
Release blocking? NO
```

---

## RED1-24 — Aggregate savings/routing telemetry cannot distinguish "routed" from several classes of early-exit silent bypass

```
ID: RED1-24
Severity: P2
Confidence: STRONG EVIDENCE
Area: Silent bypass / observability
Title: Several sys.exit(0) early-return paths in hooks/auto-route.py are recorded only in an unstructured, non-aggregated debug log, invisible to the user-facing savings dashboard
Claim/Invariant violated: the audit's central question — "can the system
  distinguish 'routed successfully' from 'we never observed what happened'?" — is
  answered "not fully" for a specific, enumerable set of paths.
Observed behavior: reading `hooks/auto-route.py`'s `main()`, there are at least
  six distinct `sys.exit(0)` early-return points before any routing directive is
  computed or a "pending" state file is written: JSON-parse failure (non-zero-
  Claude branch), empty/whitespace prompt (non-zero-Claude branch), self-reference
  bypass, sidecar pre-execution success, continuation bypass, and explicit-native
  prefix (zero-Claude only). Each of these is logged ONLY via `_debug_log()`,
  which appends free-text lines to `~/.chuzom/auto-route-debug.log` — a diagnostic
  log with no aggregation, no counter, and no surface in `chuzom_status`/
  `llm_savings`/the dashboard (confirmed: this file's writes are not the same
  code path as the structured "routes today" counter, nor the same as
  `_log_unrouted_turn()`'s `_ENFORCEMENT_LOG_PATH`, which is a NARROWER
  mechanism that only fires when a prior turn's `pending` directive existed and
  went unfulfilled — it cannot fire for these six early-exit paths because they
  return before any pending state is ever written).
  This means: the user-facing "N routes today / $X saved" dashboard (the exact
  style of banner injected into this very audit session's SessionStart hook)
  has no first-class, queryable answer to "what fraction of my turns this
  session hit one of these six early-exit paths and were never even attempted to
  route." A user (or this auditor) cannot distinguish, from the dashboard alone,
  "chuzom routed every turn perfectly" from "chuzom's classifier is silently
  bailing out on N% of turns via a bypass path" without manually grepping a raw
  debug log file whose existence isn't advertised anywhere in the dashboard UI.
Expected behavior: per `tool_surface.py`'s own stated design philosophy ("an
  unroutable name fails loudly instead of silently costing money"), an
  unrouted-by-design-bypass should be at least as visible in aggregate telemetry
  as a successfully-routed turn, so the two are distinguishable without manual
  log spelunking.
Why this matters to a real user: this is precisely the "silent bypass" scenario
  the audit mandate flags as highest priority — not because these six bypass
  paths are wrong to exist (several are clearly intentional and correct, e.g.
  self-reference bypass avoiding a circular dependency when debugging chuzom
  itself), but because their EXISTENCE and FREQUENCY are invisible in the
  product's own headline metric.
Exact reproduction: NOT independently execution-verified end-to-end in this pass
  (see "why existing tests missed it" / confidence caveat below) — this finding
  is grounded in direct reading of the exact `sys.exit(0)` call sites and the
  `_debug_log()`/`_log_unrouted_turn()` implementations, not in a live session
  trace showing the dashboard undercounting. To fully verify: instrument a
  session that deliberately triggers each of the six bypass paths, then diff
  `~/.chuzom/auto-route-debug.log` entry counts against whatever number
  `chuzom_status`/`llm_savings` reports for "turns this session" or equivalent.
Evidence:
  - src/chuzom/hooks/auto-route.py:2599-2676 (`_debug_log`, unconditional free-text append, no aggregation)
  - src/chuzom/hooks/auto-route.py:1903-1921 (`_log_unrouted_turn`, narrower structured log, only fires post-pending-directive)
  - src/chuzom/hooks/auto-route.py: six `sys.exit(0)` call sites (self-reference ~2781, sidecar ~2864, continuation ~2899, JSON-parse-failure ~2765, empty-prompt ~2777, explicit-native ~2827) — line numbers approximate, read via sed excerpts in this session, not re-verified with a fresh grep pass in this write-up
Root cause: the debug log and the enforcement/savings ledger were built for
  different purposes (developer diagnostics vs. user-facing dashboard) and were
  never unified into one source of truth for "was this turn routed, bypassed-
  intentionally, or bypassed-due-to-failure."
Why existing tests/gates missed it: no test asserts a relationship between
  debug-log bypass-event counts and dashboard-reported route counts (not
  independently confirmed by a full test-suite grep in this pass — flagged as
  NOT FULLY TESTED).
Blast radius: affects trust in the product's headline "X% routed / $Y saved"
  claim under any workload with a meaningful rate of self-reference, sidecar, or
  continuation-bypass prompts.
Can this defect class exist elsewhere?: Plausibly in `enforce-route.py`'s
  various early `sys.exit(0)` paths (e.g. `pending is None` self-healing branch)
  — NOT independently traced in this pass.
Recommended systemic fix: add a structured, aggregated counter (not just
  free-text log lines) for each bypass reason, and surface a "N turns
  bypassed (self-reference/sidecar/continuation/etc.)" line in
  `chuzom_status`/the dashboard alongside "N turns routed," so the two numbers
  are visibly reconcilable against total prompt count.
Regression test that would actually prevent recurrence: a test that runs a
  simulated session through each bypass path and asserts a structured counter
  (not just a debug-log line) increments and is retrievable via the same
  status/savings API surface used for successful routes.
Release blocking? NO (this is an observability gap, not a functional routing
  failure — downgraded from P1 to P2 because, unlike RED1-20/21, no user-visible
  error occurs; only the ability to detect/measure the gap is missing)
```

---

## What mandate areas 1, 4, 5, 6 received (honest scope statement)

This pass concentrated almost all available effort on mandate area 3 (tool surface
drift), because the very first files read (`tool_surface.py`, `lint_tool_surface.py`,
`cli.py`, `install_hooks.py`) immediately produced PROVEN, executable evidence of a
P0-class defect that kept expanding in scope on every subsequent file read (from "2
lines in cli.py" to "13 files, 10 hosts"). Given the size of the remaining mandate
(`router.py` 4967 LOC, `hooks/auto-route.py` 3790 LOC, `hooks/enforce-route.py` 1603
LOC, `hooks/agent-route.py` 1155 LOC, `classify.py`/`classifier.py`, `policies/`,
`hosts/`), a full call-graph trace (area 1), exhaustive adversarial classification-
boundary testing (area 4), and a formal per-host tool-call-schema matrix (area 5)
were **not completed** — see the honesty section in the final message for specifics.

What WAS done for areas 1/2/6, opportunistically, while reading the above files for
area 3 context:

- Confirmed `hooks/enforce-route.py`'s enforcement-mode dispatch structure
  (`off`/`shadow` -> pure no-op; `advise`/`advisory` -> never blocks, but does
  attempt best-effort adoption recording; `suggest` -> aliased to `soft`; `strict`
  -> aliased to `hard` with escape valves disabled; `hard`/`smart` -> the two modes
  that can actually emit `permissionDecision: "deny"`) by reading `main()`
  (src/chuzom/hooks/enforce-route.py:853-1000+). This matches the documented
  behavior in `~/.claude/rules/chuzom.md`'s own description of `smart` vs `hard`
  at a structural level, but **the actual deny/allow behavior was not exercised
  end-to-end with real PreToolUse JSON payloads in this pass** — confidence for
  "enforcement modes behave as documented" is STRUCTURAL READING ONLY, not
  PROVEN. Flagged as NOT FULLY TESTED.
- Confirmed (RED1-24 above) a concrete, code-grounded observability gap for
  mandate area 2 (silent bypass), distinct from the RED1-20/21/22 tool-surface
  findings — this is a different failure mode (turns that are correctly not
  routed by design, but whose bypass is invisible in aggregate telemetry) than
  RED1-20/21 (turns that ARE attempted to route but resolve to a broken tool
  name).
- Mandate area 4 (adversarial classification-boundary prompt testing) and area 5
  (formal host x tier matrix with args/schema verification) were **not performed**
  as dedicated test passes in this session. The RED1-20 finding provides strong,
  proven evidence for a SLICE of area 5 (every non-Claude-Code host's onboarding
  artifact teaches unregistered tools), but does not constitute the full matrix
  the mandate asks for (argument schema validation, actual callability proof per
  host, etc. — see 05_HOST_INTEGRATION_AUDIT.md for what could be inferred vs.
  what remains untested).
