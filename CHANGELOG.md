# Changelog

## v0.5.6 — 2026-06-24 — Fix: public package import without enterprise

### Fixes

- **Public distribution import crash** — `chuzom.server` / `chuzom.router` (and the `chuzom`
  MCP entrypoint) failed to import when installed from PyPI with
  `ModuleNotFoundError: No module named 'chuzom.enterprise'`. The `enterprise/` package is
  intentionally excluded from the published wheel/sdist, but five modules
  (`audit_routing`, `rbac_routing`, `admin_api`, `scim_api`, `commands/audit`) imported it at
  top level without a guard. These imports are now wrapped in `try/except ImportError` so the
  public package imports and routes cleanly; enterprise features remain gated behind
  `is_enterprise()`. Adds `tests/test_public_import.py`, which imports the core modules with
  `chuzom.enterprise` forced absent to prevent regressions.

---

## v0.5.5 — 2026-06-24 — Agentic model routing

### New features

- **`CHUZOM_AGENTIC_MODEL` / `agentic_model` routing pin** — designate a preferred model for
  agentic / tool-reasoning tasks (`analyze`, `generate`, `query`, `research`). When set, it is
  pinned at the absolute front of the routing chain for those task types — ahead of the generic
  Ollama injection and every other reorder — so a strong tool-calling model (e.g. Hermes) leads
  agent work. `CODE` is intentionally excluded so dedicated coder models still win coding tasks.
  Configure via the `CHUZOM_AGENTIC_MODEL` env var or the `agentic_model:` key in
  `~/.chuzom/routing.yaml` (env > repo > user precedence). Example:
  `CHUZOM_AGENTIC_MODEL=ollama/hermes3:8b`. The `agent-route` hook surfaces the pinned model in
  its route indicator.

### Fixes & docs

- **Ghost-model fix** — `auto_profile` no longer hardcodes `ollama/qwen3.5:latest` (and other
  example tags) into the free-local tier when those models are not installed. It now prefers the
  models actually discovered from the running Ollama instance, falling back to the example list
  only before discovery has run. Prevents routes to a model the user doesn't have.

---

## v0.5.4 — 2026-06-17 — PyPI metadata & discoverability improvements

### Improvements

- **PyPI metadata**: bumped classifier from `3 - Alpha` to `4 - Beta`; added keywords
  `claude`, `anthropic`, `ollama`, `token-optimization`, `cost-saving`, `quota-saver`,
  `ai-routing`, `llm-proxy`, `copilot`, `windsurf` for search discoverability.
- **Project URLs**: fixed `Bug Tracker` and `Changelog` links (previously pointed to
  personal fork instead of `Chuzom/Chuzom` org repo); added `Documentation` link.
- **Short description**: now mentions Cursor and Copilot explicitly alongside Claude Code.
- **README**: hero image now uses absolute GitHub URL — was previously broken on PyPI
  (relative `assets/` paths do not resolve in PyPI's renderer).

---

## v0.5.1 — 2026-06-14 — GitHub Copilot & Windsurf IDE support

### New features

- **`chuzom install --host copilot`** — installs full VS Code / GitHub Copilot pull-routing
  stack: user-level `~/Library/Application Support/Code/User/mcp.json`, workspace
  `.vscode/mcp.json`, `.github/copilot-instructions.md` (instructs Copilot to call
  Chuzom tools first), and `.github/agents/chuzom.agent.md` (Copilot agent with
  `tools: ['chuzom']` for strongest tool-first enforcement in Agent mode).

- **`chuzom install --host windsurf`** — installs Windsurf / Cascade pull-routing stack:
  global `~/.codeium/windsurf/mcp_config.json`, workspace `.windsurf/mcp.json`, and
  `.github/copilot-instructions.md` (also read by Windsurf).

- **`install_hooks.py ide` subcommand** — `python install_hooks.py ide` writes
  `.vscode/mcp.json`, `.windsurf/mcp.json`, and `.cursor/rules/use-chuzom.mdc` to the
  project root. `python install_hooks.py ide --uninstall` removes them.

### Architecture

- **Push vs pull routing** explained clearly in README: Claude Code uses push routing
  (hooks intercept 100% of prompts automatically); Copilot/Cursor/Windsurf use pull
  routing (model must choose to call the tool). IDE support matrix added.

- **`--host all`** now includes `windsurf` in the installation loop.

### Bug fixes

- `--host copilot` previously called `_print_vs_code_copilot_config()` (print-only);
  now correctly calls `_install_vscode_files()` which writes all config files.

---

## v0.5.0 — 2026-06-14 — Deep Reasoning tier (DeepSeek-R1 · o3 · Gemini thinking)

### New features

- **`RoutingProfile.REASONING` — dedicated 4th routing tier.** `Complexity.DEEP_REASONING` previously mapped to `PREMIUM` (identical chain to `complex`). It now maps to a dedicated `REASONING` profile with a cost-ordered chain prioritising native reasoning models:
  `ollama/qwen3.6:27b → deepseek/deepseek-reasoner → openai/o3 → gemini/gemini-2.5-pro → anthropic/claude-opus-4-6 → anthropic/claude-sonnet-4-6`.
  DeepSeek-R1 costs $0.0014/1K vs $0.04/1K for general frontier models — 28× cheaper for deep-reasoning tasks.

- **`llm_reason` MCP tool (6th text tool).** Always routes with `complexity="deep_reasoning"`. No caller-supplied complexity parameter — the tool always invokes the REASONING chain. Best for: formal proofs, mathematical derivations, step-by-step reasoning, root-cause analysis.

- **Gemini 2.5 Pro extended thinking via `thinkingConfig`.** When `use_thinking=True` (set automatically for `deep_reasoning` tasks), Gemini 2.5 Pro now receives `thinkingConfig: {thinkingBudget: 8192}` in addition to the existing Anthropic `thinking: {type: enabled, budget_tokens: 16000}` block. No temperature constraint is needed for Gemini (unlike Anthropic which requires `temperature=1`).

- **Expanded `COMPLEXITY_DEEP_REASONING` regex.** Natural-language chain-of-thought triggers added alongside the existing formal/academic vocabulary: `step by step`, `think through`, `walk me through the reasoning`, `chain of thought`, `root cause analysis`, `show your work`, `first principles`, and more. Same regex applied in both `auto-route.py` and the RouterArena submission router.

- **`CHUZOM_REASONING_TIMEOUT` env var (default: 300s).** Dedicated timeout for deep reasoning API calls. DeepSeek-R1 and o3 can take 60–300s for complex proofs; the existing `CHUZOM_REQUEST_TIMEOUT` (120s) was insufficient.

### Architecture SVG

- Hero diagram updated with a 4th tier card (purple, "🧠 Deep Reasoning") and animated routing dot.

### Migration notes

> **If you use `match profile:` with exhaustive case arms**, add a `case RoutingProfile.REASONING:` branch.
> The new value is the string `"reasoning"`. Code that passes `profile="reasoning"` to `ChuzomAgent` or `_resolve_profile()` will now correctly resolve to the REASONING chain rather than falling back to BALANCED.

### Internal

- `agno.py`: `_PROFILE_MAP` now includes `"reasoning": RoutingProfile.REASONING`.
- `memory/profiles.py`: `tool_to_task` map now includes `"llm_reason": TaskType.ANALYZE`.
- `tools/routing.py`: `valid_tools` set in `llm_reroute` now includes `"llm_reason"`.
- `release.py`: `_EXTRA_VERSION_FILES` now wires `tui/__init__.py` into the release script so its hardcoded `__version__` is never left behind.

---

## v0.4.2 — 2026-06-14 — Dashboard polish, inversion fix, routing signals

### Bug fixes

- **MODELS panel showed routing method names instead of model names.** Commit `dc0ccea` removed `tools_data = report_data.get("tools", {})` when refactoring `model_breakdown` to use a DB query, but left the block that still referenced it. The resulting `NameError` caused the Rich renderer to crash and fall back to a legacy path that populated `model_breakdown` with method names. Fixed by restoring the variable assignment.

- **UP-inversions reduced from ~16% to near-zero.** Complex tasks (deep analysis, code) were leading with Ollama in all pressure zones. Reordered `chain_builder.py` so `mid_externals` (GPT-4o, Gemini Pro) lead before Ollama for complex tasks in yellow/orange/red/critical zones.

- **DOWN-inversions eliminated for Codex/Gemini CLI.** `codex/*` and `gemini_cli/*` model prefixes were mapping to `Tier.MID/PREMIUM`, producing false DOWN-inversions when those free-subscription models handled simple tasks after Ollama failed. Now mapped to `Tier.CHEAP`.

### Dashboard

- **SAVINGS panel now shows token counts.** Each period (today, this week, this month, lifetime) shows `$X.XX label` on one line and `N tok` on the next in dimmed text.

### RouterArena classifier

- `failure modes?` added to `_COMPLEXITY_COMPLEX` so prompts asking to "cite failure modes" are correctly classified as complex analysis.
- `brief` removed from `_COMPLEXITY_SIMPLE` — it is a format instruction ("Keep it brief"), not a complexity signal; length-based classification handles the rest.
- `approach` removed from `analyze.topic` — too generic; appeared in ML explanation prompts ("each approach in a domain") causing false positives.

### CI

- All plugin manifests (`.claude-plugin`, `.codex-plugin`, `.factory-plugin`) synced to `0.4.2`.

---

## v0.4.1 — 2026-06-13 — CI fixes, session summary visible, deadline guard

### Bug fixes

- **Session summary now visible in Claude Code UI.** Root cause: `Console(record=True)` without `file=` defaults to writing to stdout AND recording simultaneously. Claude Code's Stop hook contract requires exactly one JSON line on stdout — anything else on stdout before the `{"systemMessage": ...}` line is silently discarded, causing the summary to never appear. Fixed by redirecting Rich to `io.StringIO()` (`file=_rich_buf`) so stdout stays clean for the JSON envelope. Colored output is saved to `~/.chuzom/last_summary.ansi` and visible via `cat ~/.chuzom/last_summary.ansi` or `chuzom summary` in a real terminal.

- **`test_min_cap_wins_when_both_set` deadline guard.** When a workflow deadline expires *during routing setup* (chain-build, idempotency check, budget lock acquisition) rather than during dispatch, the computed `_dl_remaining_at_dispatch` went negative. The `_effective_timeout > 0` guard then silently skipped `asyncio.wait_for`, running the dispatch coroutine without any timeout and never raising `DeadlineExceeded`. Fixed by adding a pre-dispatch deadline re-check that raises `DeadlineExceeded` immediately when remaining time ≤ 0 at dispatch entry. Test deadline increased from 50 ms to 500 ms to reliably exercise the `asyncio.wait_for` path.

- **`test_code_task_codex_after_first_claude_not_last` routing mock.** The test's `_selective_fail` mock only failed `anthropic/*` models, but the dynamic routing table for `(BALANCED, CODE)` starts with `ollama/qwen3.5:latest` before Claude. The Ollama model succeeded via the litellm mock, so the router returned before reaching Codex. Fixed by failing ALL litellm models so only `run_codex` (the Codex CLI path) can succeed.

- **Ollama models gated behind reachability probe.** `build_dynamic_routing_table` previously always added `ollama` to the available-providers set regardless of actual Ollama availability. Routing chains could include Ollama models that immediately timed out on every request. Now guarded by `probe_ollama()` (1-second HTTP check with 60-second TTL cache); Ollama only enters the chain when the server is reachable.

### Packaging

- Description updated to emphasize token savings and session preservation for Claude Code/subscription users.
- PyPI `Homepage`/`Repository` URLs corrected from `ypollak2/chuzom` to `Chuzom/chuzom`.
- README: added "For Claude Code / Claude Pro / Max Subscribers" section explaining 3× session extension.

### Linting

- Fixed all 16 ruff errors: F821 (missing `Callable`/`Awaitable` imports in `codex_agent.py` and `gemini_cli_agent.py`), F841 (unused `PLOT_LEFT` in `session_summary.py`), F401/F841 in test files.

---

## v0.3.0 — 2026-06-11 — Enterprise enforcement wired + honest packaging

> Closes the audit's anchor finding (INV-010): the enterprise control plane is now **wired into and enforced on the routing path** under `CHUZOM_DEPLOYMENT_PROFILE=enterprise`, and the packaging/README are reconciled to reality. The developer router stays stable; the enterprise control plane is labelled **beta** with a per-feature status table in the README.

### Enterprise control plane (now enforced under the enterprise profile)

- **INV-010 closed.** RBAC (`check_route_prompt` / `check_provider` / `check_model`) and the audit chain are consulted on every routed turn. The enterprise profile flips RBAC→strict, audit→mandatory, redaction→on, forecast→strict (G-001/G-003/G-012/G-016). End-to-end enforcement proof added.
- **Phase 3b — per-identity allow-lists.** The authenticated SSO/OIDC identity now carries `permissions` + per-identity `allowed_providers` / `allowed_models` from the `IdentityStore`, so a restricted token enforces through the wired gates. Empty lists normalise to `None` (unrestricted) — an empty allow-list can never silently deny-all.
- **Loop-5 / G-039.** `CHUZOM_DEPLOYMENT_PROFILE` deployment-profile detection back-ported into the auto-route hook; the self-reference bypass is refused under the enterprise profile.
- **G-029 agent ledger.** `SessionStore.recent()` / `cancel()` (cascade) / `record_tool_call()` + `last_activity_at`; admin agent status + cancel endpoints.

### Security

- **G-004 — RBAC allow-list prefix-spoof closed.** A forged `provider/forged-model` candidate could match a bare allow-list entry (the provider prefix was stripped before comparison). `check_model` now matches the full id exactly; the `provider/model` and bare forms never cross-match.

### Packaging & docs (P0-6)

- `chuzom --version` reports the **installed distribution's version** (installed wheels previously reported a stale hardcoded `10.1.2`).
- `chuzom install --host claude-code` / `--host claude-desktop` now resolve; generated MCP configs invoke the canonical `chuzom` stdio entry instead of the deprecated `uvx claude-code-chuzom` package.
- README rewritten concise + honest (806 → ~140 lines) with a real "How it works" section and a per-feature beta status table; the overclaimed SOC 2 / GDPR / OTEL badges were dropped.

### Known gaps (on the roadmap; labelled beta in the README)

- SCIM mounting + role/group mapping; team-budget enforcement; multi-instance (Postgres) HA; control-plane→routing wiring for provider-disable / policy-versioning; audit-chain verify CLI/endpoint.

## v0.2.0 — 2026-06-08 — Audit Tracks 1 & 2 + lineage API rewrite

> **Security advisory + claims reconciliation + honest test signal + lineage API rewrite.** This release closes the developer-focused subset of the 2026-06 internal audit (`Docs/audit/FINDINGS.md`): **2 Critical** and **6 High** findings across security defaults (SEC-001/002/003), session isolation (INV-007 + ROU-001), truth-in-claims (INV-001/002), and test-suite integrity (TST-001). It also lands the **v0.2.x `LineageStore` API rewrite** that was implicit in TST-001's follow-up. Multi-tenancy / identity-layer items (INV-010, INV-011, ROU-002, PRI-001, OBS-001, TST-003) are deferred to Phase 2 pending the multi-tenancy product decision.
>
> The two Critical findings (SEC-001, SEC-002) were exploitable with default settings. Operators running prior versions on a reachable network should review the mitigations below.

### Security

- **SEC-001 — Removed `chuzom-sse` console script (BREAKING).** Prior versions installed a `chuzom-sse` binary that, when invoked, bound `0.0.0.0:$PORT` and exposed the full 60-tool MCP surface — including filesystem tools, wallet, and routing controls — with **zero authentication**. The entry point has been removed from `pyproject.toml`. The `chuzom.server.main_sse` function is retained in source for future re-introduction behind proper authentication + identity (post-INV-010); attempting to re-add the entry point without an auth wrapper is now guarded by a regression test (`tests/test_no_chuzom_sse_entry_point.py`).
  - **Mitigation if you were running `chuzom-sse`:** stop the process, review any logs you have for unauthorised tool invocations during the exposure window, rotate credentials accessible from the host, and switch to the stdio transport (`chuzom`) until a hardened SSE wrapper ships.
- **SEC-002 — `llm_fs_*` tools are now opt-in and sandboxed (BREAKING).** Prior versions registered four filesystem tools (`llm_fs_find`, `llm_fs_rename`, `llm_fs_edit_many`, `llm_fs_analyze_context`) by default. `llm_fs_edit_many` accepted an arbitrary glob and read up to 32 KB per match into the model prompt; `llm_fs_edit_many(glob_pattern="~/.ssh/**")` was a one-call exfiltration vector. Two independent gates now apply:
  1. **Opt-in env.** Tools are registered only when `CHUZOM_FS_TOOLS=on` (or `1`/`true`/`yes`) is set. Without the opt-in, `mcp.list_tools()` exposes zero `llm_fs_*` entries.
  2. **`project_root` sandbox.** `llm_fs_edit_many` and `llm_fs_analyze_context` now require a `project_root` parameter. The root is resolved with `Path.resolve()` (closing the symlink-escape hole); paths that resolve outside it are rejected before any file read or route call. `project_root='/'` is refused outright.
- **SEC-003 — `agoragentic_*` MCP tools are now opt-in (BREAKING).** Prior versions registered four marketplace tools (`agoragentic_task`, `agoragentic_browse`, `agoragentic_wallet`, `agoragentic_status`) by default, even when `CHUZOM_SLIM=routing` was set. **`agoragentic_task` performs USDC settlement on the Base L2 blockchain** — it can spend real money via the credentials stored at `~/.chuzom/agoragentic.json`. An LLM agent enumerating tools, an MCP client probing the tool list, or a hallucinated tool call could trigger an unintended on-chain transaction. The four tools are now gated behind `CHUZOM_AGORAGENTIC=on` (or `1`/`true`/`yes`). Without the opt-in, `mcp.list_tools()` exposes zero `agoragentic_*` entries.
- **INV-007 / ROU-001 — Per-session classification side channel (BREAKING).** The auto-route hook previously wrote a shared `~/.chuzom/last_classification.json` that every MCP server on the machine read from. Two failure modes: (1) two Claude Code sessions raced on the same file (whoever fired last set the verdict for both); (2) any same-user process could forge a classification within the 120 s freshness window. The hook now writes `~/.chuzom/last_classification_<session_id>.json` and the MCP reader pins to `CLAUDE_SESSION_ID` from the env that Claude Code injects when it spawns the MCP server. A belt-and-braces inner-payload check rejects shards whose inner `session_id` doesn't match the env. The legacy shared file is no longer written or read; consumers that still look for it gracefully return `None` and fall back to the length heuristic.

### Truth-in-claims

- **INV-001 — Pre-existing self-audit rescoped, not retracted.** `AUDIT_FINDINGS.txt` and `CHUZOM_AUDIT_REPORT.md` (both dated 2026-06-07, narrow lineage-subsystem reviews) previously stamped the project as "✅ APPROVED FOR IMMEDIATE PRODUCTION DEPLOYMENT" with 5★ ratings across the board. The 2026-06-08 comprehensive audit identified 3 Critical, 11 High, 11 Medium, 3 Low findings and scored enterprise-readiness at 1.65 / 5 — the prior claims were a scoping error, not a measurement of the whole project. Both files now carry a top-of-document scope notice, every overclaiming line is contextualised to "lineage subsystem only", and the documents point at `Docs/audit/` as the authoritative whole-project assessment. The lineage subsystem verdict (production-ready as a subsystem) is preserved.
- **INV-002 — README hero reconciled with `pyproject.toml` Alpha status.** The README first paragraph previously read "The enterprise-ready LLM router for developer organizations." while `pyproject.toml` classified the project `Development Status :: 3 - Alpha`. The hero now describes the project as "Local-first LLM router for developer workstations" and adds a maturity line stating that the developer-tool layer is the production path today (alpha per `pyproject.toml`) and the enterprise control plane (RBAC, tamper-evident audit chain, per-user / per-team budgets, OpenTelemetry export) is scaffolded but not yet wired into the routing path (`INV-010`). The reader of the first 30 lines of README and the first 20 lines of `pyproject.toml` now arrives at the same maturity conclusion.

### Testing

- **TST-001 — Un-skipped 9 silently-excluded test suites.** `tests/conftest.py:collect_ignore` had dropped 206 tests at collection time, including integrity, performance, observability, session-summary rendering, framework scenarios, and lineage roundtrips. The original justification (lineage symbols missing) was stale — PR #10 restored the exports but the exclusion list was never cleaned up. The README's "766 tests passing" badge ran against a suite that hid these. `collect_ignore` is now empty (every test file is collected); the residual failures all share one root cause (`LineageStore(db_path=...)` signature drift, fixed below in the lineage rewrite) and were individually marked via `_KNOWN_BROKEN_TESTS` with reasons that show up in `pytest -v`. New meta-test `tests/test_no_silent_collect_ignore.py` guards against future silent-exclusion regressions.

### Lineage API rewrite

- **`LineageStore` — dual-keyword constructor + planned `LineageRecord` write/query surface.** PR #16 (TST-001) exposed ~30 tests across 8 files that referenced a `LineageStore` API never implemented. That API now exists, additively:
  - **Constructor** (`__init__`) accepts both `router_dir` (directory, production shape — every `src/` caller hits this) and keyword-only `db_path` (specific SQLite file, test shape). Passing both raises `ValueError`. Production callers are unchanged — none used either keyword pre-rewrite.
  - **New `lineage` SQLite table** parallel to the existing `routing_decisions` table; mirrors `LineageRecord.to_row()` (22 columns including agent_id / session_id / step_index / parent_session_id / framework). Forward-compatible migration: if a pre-v0.0.2 DB is opened with a lineage table that lacks the agent-session columns, `_init_db` `ALTER`s the table to add them.
  - **New methods**: `record(LineageRecord)` writes to JSONL + the new table; `inversions(kind=None)` filters by `Inversion` enum; `summary()` aggregates total / up / down / none + inversion_rate; `by_session(session_id, agent_id=None)` returns rows ordered by step_index; `by_framework(slug)` returns rows matching the framework column; `close()` is a no-op symmetry shim.
  - **Result**: 14 `_KNOWN_BROKEN_TESTS` entries removed from `conftest.py`; the previously-skipped suites now contribute **~350 newly-visible passing tests** to coverage. Total: `tests/test_lineage.py` + `tests/qa/` + `tests/scenarios/` go from 116 → **470 passing** with 0 failures.

### Breaking changes

- The `chuzom-sse` console script no longer exists. Use the stdio transport (`chuzom`) until an authenticated SSE wrapper ships.
- `llm_fs_edit_many` now requires `project_root: str` as a positional argument (was previously sandbox-less).
- `llm_fs_analyze_context` renamed its first argument from `path` (default `"."`) to `project_root` (required). The previous default that quietly analysed the process cwd is gone.
- `llm_fs_*` tools are NOT registered unless `CHUZOM_FS_TOOLS=on` is set.
- `agoragentic_*` tools are NOT registered unless `CHUZOM_AGORAGENTIC=on` is set.
- The hook → MCP classification bridge moved from `~/.chuzom/last_classification.json` to per-session shards `~/.chuzom/last_classification_<session_id>.json`. Consumers that still target the legacy filename will see no data (and the router will fall back to its length heuristic, which is the correct conservative default).

### Added

- `tests/test_no_chuzom_sse_entry_point.py` — 3 regression tests guarding SEC-001.
- `tests/test_fs_path_validation.py` — 26 tests covering the SEC-002 env gate and sandbox helpers (`_resolve_root`, `_assert_under_root`, `_filter_files_under_root`), including symlink-escape and absolute-path-outside-root cases.
- `tests/test_agoragentic_opt_in.py` — 18 regression tests covering the SEC-003 env-gate truth table.
- `tests/test_classification_side_channel_isolation.py` — 12 tests covering session isolation, adversarial forgery (ROU-001), inner-payload mismatch, staleness, and malformed-input resilience.
- `tests/test_no_silent_collect_ignore.py` — 2 meta-tests asserting `collect_ignore` stays empty and every `_KNOWN_BROKEN_TESTS` entry carries a reason.
- `chuzom.tools.fs.FsSandboxError` — raised when a path escapes the configured `project_root`.
- `chuzom.lineage.LineageStore.{record, inversions, summary, by_session, by_framework, close}` — planned-API methods for writing and querying `LineageRecord` instances.
- `lineage` SQLite table — parallel to `routing_decisions`; mirrors `LineageRecord.to_row()` with forward-compatible migration of pre-v0.0.2 schemas.
- Security notice docstrings on `chuzom.server.main_sse`, `chuzom.tools.fs.register`, and `chuzom.tools.agoragentic.register` explaining the threat model and the conditions under which the prior behaviour may be reintroduced.

### Notes for operators

- Anyone who was relying on the default-on filesystem tools must add `CHUZOM_FS_TOOLS=on` to their environment AND pass `project_root` on every call.
- Anyone who was intentionally using the Agoragentic marketplace must add `CHUZOM_AGORAGENTIC=on` to the environment that launches the MCP server. The credentials file at `~/.chuzom/agoragentic.json` is unchanged.
- **If you discover unauthorised on-chain activity from `~/.chuzom/agoragentic.json`'s `agent_id` predating this release:** rotate the API key, revoke the agent, and review settlements on the Base L2 explorer. The pre-fix default was exploitable.
- Symlink escapes are now closed because path validation runs after `Path.resolve()`, not against the raw user-supplied string.
- The full audit context — including findings' file:line evidence and the rejected alternatives — lives in `Docs/audit/HIGH_PRIORITY_WORK_PLAN.md` and `Docs/audit/FINDINGS.md`.

### Phase 2 (parked pending multi-tenancy product decision)

- `INV-010` (identity → routing → audit chain wiring), `INV-011` + `TST-003` (per-identity budgets + concurrency tests), `ROU-002` (per-tenant routing tables), `PRI-001` (redaction in routing path), `OBS-001` (tenant/user/agent fields in logs). All blocked on `Q-P-2` in `Docs/audit/OPEN_QUESTIONS.md`.

---

## v0.1.1 — Stop misrouting display-intent prompts to llm_code

> **Patch release.** Targets the most common "Chuzom appears stuck" experience: trivial follow-ups like `show me the report` issued after code-heavy turns were being classified `code/moderate` via `code-context-inherit`, then forced through `mcp__chuzom__llm_code` — an external LLM that can't read local files. The tool would spin for 2-4 minutes before the user cancelled. No actual hang; just a misroute taking the slow path that couldn't help anyway. Full analysis in [`STUCK_PATTERNS_ANALYSIS.md`](./STUCK_PATTERNS_ANALYSIS.md).

### Added
- **Display-intent override** (`auto-route.py`) — `_DISPLAY_INTENT_RE` matches short prompts (≤100 chars) starting with `show`/`display`/`view`/`read`/`cat`/`print`/`list`/`open`/`see` followed by a display target (`the/my/this/<file>.md/report/file/output/log/diff/...`). Such prompts always route to `llm_query` regardless of inherited context, tagged `intent-override-display` for telemetry. Does **not** save to `last_route` so subsequent genuine code follow-ups still inherit the prior code context correctly.
- **`STUCK_PATTERNS_ANALYSIS.md`** — comprehensive 4-mode taxonomy of perceived "stuck" events across Claude Code CLI, VS Code/JetBrains extensions, Cursor/Windsurf, and Claude.ai web. Includes evidence trail from `auto-route-debug.log` + the d4cd6a72 session transcript, defense-gap matrix, prioritised fix list, and an instrumentation patch proposal for catching the next one.
- **`tests/test_display_intent_override.py`** — 41 cases covering positive matches, negative matches against real code-generation prompts (`show me a function that…`), length-cap behaviour, and source-integration smoke check that asserts the override branch remains wired.

### Changed
- **Continuation bypass narrowed to strict acks** (`auto-route.py`) — the early UserPromptSubmit bypass at `chuzom-auto-route.py:1988` now triggers only on strict `_CONTINUATION_RE` matches (single-word `yes`/`ok`/`go ahead`/etc.), not the broader `_is_short_followup` union. Multi-word directives like `please go ahead and do the change` after a code task now fall through to the classification block instead of silently exiting with no output. Behaviour change: prompts starting with `please`/`now`/`let's` no longer bypass — they're routed normally.
- **Classification branch order** (`auto-route.py`) — `_is_short_code_followup` is now checked **before** `_is_continuation` so short follow-ups after code tasks get the specific `code-context-inherit` telemetry tag instead of the generic `context-inherit`. Routing destination is functionally identical; observability is sharper.
- **`LineageStore` exported from `chuzom.lineage`** — adds `LineageStore` to `chuzom/lineage/__init__.py`'s `__all__` so `chuzom.tools.agents` (and the 5 QA-suite test modules) can import it without `ImportError`. Class existed in `lineage_store.py`; export was missing.
- **Live-hook tests find the renamed file** (`tests/test_auto_route_fix_verb.py`) — `_find_live_hook()` helper checks `~/.claude/hooks/chuzom-auto-route.py` first, falls back to legacy `llm-router-auto-route.py`. Resolves post-rebrand test drift where v0.0.2 fix-pattern assertions still pointed at the pre-rebrand binary path.

### Fixed
- **Silent hook exit on multi-word follow-ups** — `test_short_followup_after_code_inherits_code` was failing because the broad bypass swallowed prompts like `please go ahead and do the change now`. Now correctly emits the `code-context-inherit` routing directive.
- **Perceived 2-4 minute hangs on display-intent prompts** — the misroute path is closed at the classifier. `show me the report` after a code-heavy session now routes to `llm_query` (cheap, fast) instead of `llm_code` (slow external LLM that can't help).

### Internal
- 41 new regression tests in `test_display_intent_override.py`; 198/198 passing across `test_auto_route_*` + `test_display_intent_override` + `tests/lineage/` suites.

---

## v0.1.0 — Stability promise + first benchmark numbers + brand sweep

> **First stable-shape release.** The 0.0.x phase shipped fast and broke things on the way; 0.1.0 commits to:
> - SQL schema migrations land via `_safe_migrate` (idempotent ALTER TABLE) — no destructive resets.
> - Public CLI entry points (`chuzom`, `chuzom-install-hooks`, `chuzom-onboard`, `chuzom-quickstart`, `chuzom-sse`) and MCP tool names (`llm_*`, `chuzom_agent_*`) are frozen. Removals will go through a deprecation cycle in 0.2.x.
> - Enforcement mode names (`off`, `soft`, `smart`, `hard`, `strict`) are stable.
> - SQLite database file paths (`~/.chuzom/{usage,lineage,sessions,quotas,audit}.db`) are stable.

### Added
- **First end-to-end benchmark numbers** — ran `python -m bench --easy-only` against the smoke corpus (5 prompts × 4 routers). On objective easy prompts, Chuzom matches AlwaysCheap (q=2.60, $0.00 spend) — proves the heuristic-first cascade routes correctly when no escalation is warranted. AlwaysPremium errored on OpenAI rate limit, so cost-vs-quality Pareto vs GPT-4o isn't measurable yet; see `bench/results/20260606-150229.{json,md}` for the raw data.
- **`scripts/verify_chuzom_hooks.sh`** — end-to-end verifier that pipes representative payloads into the installed hooks (`~/.claude/hooks/chuzom-*.py`) and asserts the production code paths contain the live brand + enforcement logic. 11 checks; run after every reinstall.
- **`scripts/backfill_sidecars.py`** — replays `~/.chuzom/last_route_*.json` sidecars (written by `auto-route.py` when a directive fires) into `routing_decisions`. Idempotent via stable `correlation_id` (`sidecar:<session>:<saved_at>`). Sidecars carry intent only, so rows land as `success=0, reason_code='sidecar_backfill'`.
- **`token_budget.count_tokens(text, model=None)`** — accurate per-model token counting via tiktoken when available; falls back to `chars/4` when tiktoken is missing, the model is unknown, or encoding load fails. Used by cost-attribution paths (`tools/codex.py`, `tools/gemini_cli.py`); hot-path budget checks keep `estimate_tokens()` for speed.
- **`CHUZOM_ENFORCE=strict`** — new enforcement mode that disables every escape valve: the read-only Bash exception (smart mode allows `git log`/`ls`), the loop auto-pivot (3× same tool in 2 min → unblock), and the count auto-pivot (4 violations/turn → unblock). Use when bypass discipline matters more than uninterrupted flow.
- **Outcome-stamped enforcement log** — every VIOLATION line in `~/.chuzom/enforcement.log` now carries `outcome={BLOCKED, BLOCKED(strict), ALLOWED(soft), ALLOWED(readonly_bash)}` so the log is self-explanatory without source reads.
- **Schema bootstrap in `tools/admin.py:llm_usage`** — fresh / 0-byte `usage.db` now renders the empty-state UI instead of erroring with `no such table: usage`. Matches the resilience already in `dashboard_data.py`.

### Changed
- **Full brand sweep**: 37 source files (`.py` + `rules/*.md`) swept from `LLM Router` → `Chuzom` / `LLM ROUTER` → `CHUZOM`. Stop summary header now renders `⚡ CHUZOM`; dashboards, digests, install messages, web TUI, and routing rules are all consistent. Routing rules file regenerated as `chuzom-rules-version: 5`.
- **Cyber-grid Stop summary layout** — long classifier names (`code-context-inherit` at 20 chars, `content-generation-fast-path` at 28 chars) were rendered with `f"{name:<16}"` which pads but doesn't truncate, so labels bled into the SAVINGS column on the right. Adds method-name aliases (`build-fast`, `ctx-inherit`, `content-gen`, `heuristic·w`) plus a 16-char hard truncation guard so future classifier names can't reintroduce the overflow.

### Fixed
- **`outcome=BLOCKED` actually means blocked.** Pre-0.1.0, VIOLATION lines in `enforcement.log` left the disposition (blocked vs auto-pivot-allowed vs soft-mode-allowed) implicit — readers had to know the source to disambiguate. Now every exit path stamps its own outcome.

### Known gaps (will be addressed in 0.1.x)
- Easy-only benchmark can't differentiate routers (all classify as `simple` → all route to local). Moderate-corpus run with judge-grading is needed to show the classifier's value. Deferred until empty-response detection lands.
- Empty-response from local model (`ollama/qwen3.5`) on 3 of 5 easy prompts does NOT trigger cascade — the router silently returns the empty string instead of escalating. Tracked.
- AlwaysPremium baseline requires a working `OPENAI_API_KEY`; smoke run hit rate-limit. Cost-savings vs GPT-4o not yet measurable. Workaround: use `litellm`-routed Sonnet via Claude subscription as the premium baseline.
- `__version__` in `src/chuzom/__init__.py` is set to `10.1.2` (internal numbering); `pyproject.toml` is the public version source. Sync drift to be resolved.

### Internal
- 15 new regression tests covering: schema bootstrap, sidecar backfill (7 tests), strict enforcement (4 tests), cyber-grid layout (2 tests), token counting (6 tests). Full suite green at v0.1.0 cut.

---

## v0.0.2 — Agent layer + framework adapters + benchmark harness

### Added
- **`chuzom/agents/` module** — agent-aware routing without owning the agent loop.
    - `AgentProfile` dataclass — tier preference, signal boosts, preferred chain, budget envelope.
    - `AgentRegistry` — YAML-loaded (`config/agents.yaml`); 3 default profiles ship: `code-reviewer`, `trend-researcher`, `tdd-guide`.
    - `AgentSession` + `SessionStore` — SQLite-backed at `~/.chuzom/sessions.db`. State machine: ACTIVE → COMPLETED / ERRORED / BUDGET_EXCEEDED. Nested sessions via `parent_session_id` with full descendant `rollup`.
    - `BudgetEnvelope` + `BudgetExceeded` — immutable envelope, pre-emptive `would_exceed`, raise-or-pass `raise_if_would_exceed`.
- **`chuzom/tools/agents.py`** — 6 MCP tools:
    - `chuzom_agent_list` / `chuzom_agent_start_session` / `chuzom_agent_check_budget` / `chuzom_agent_route` / `chuzom_agent_complete_session` / `chuzom_agent_lineage`.
    - Budget enforcement at the route boundary — sessions refuse calls that would breach.
- **`chuzom/frameworks/` module** — adapter shape for agent frameworks.
    - `FrameworkAdapter` protocol (3 methods: `wrap_model`, `detect_agent_id`, `is_available`).
    - **Agno** — concrete, re-exports `RouteredModel` + `RouteredTeam` from `chuzom.integrations.agno`.
    - **Hermes** — skeleton; v0.0.3 lands the concrete tool-use protocol.
    - **LangGraph / CrewAI / OpenAI Agents SDK / Claude Agent SDK / Pydantic AI** — adapter stubs.
- **Lineage schema extension** — 5 new optional columns: `agent_id`, `session_id`, `step_index`, `parent_session_id`, `framework`. Idempotent migration handles pre-v0.0.2 databases via `ALTER TABLE ADD COLUMN` with duplicate-column guard. New indexes on `session_id` and `agent_id`.
- **Decision engine boosts** — `DecisionEngine.choose(scores, boosts={"signal": multiplier})`. Applied as score multipliers; thresholds untouched; scores clamped to [0,1]. Evidence annotated so lineage shows the boost was active.
- **`bench/` benchmark harness** — router-agnostic head-to-head comparison.
    - `Router` protocol — any router that returns `RouterResult` competes.
    - Built-in routers: `ChuzomRouter`, `FixedModelRouter` (cheap/premium endpoints), `StaticChainRouter` (ablation).
    - Hybrid judge: deterministic substring grading for objective prompts, LLM-as-judge for subjective.
    - Pareto frontier — only routers worth picking from at any quality budget.
    - Smoke corpus (5 easy + 5 moderate).
- **Local installability** — `pip install -e .` now works cleanly. CLI binary `chuzom`, `chuzom doctor`, full subcommand surface verified.

### Changed
- `chuzom/cache/` package now re-exports legacy `get_cache` / `ClassificationCache` from `cache/classification.py` (moved from `chuzom/cache.py`) alongside the new `SemanticCache` skeleton.
- `LineageRecord` gained 5 nullable fields. Existing call sites unchanged; new fields default to `None`.
- `make_record()` accepts optional `agent_id`, `session_id`, `step_index`, `parent_session_id`, `framework` keyword args.

### Tests
- **112 passing** (51 new for v0.0.2: 35 agent tests, 11 decision-boost tests, 5 framework smoke tests via tools).
- Coverage: budget envelope (consume / would_exceed / raise patterns), session lifecycle (create / record_step / complete / error / nested rollup), registry (YAML loader, duplicate-id rejection, default-template parse), MCP tool surface (refuse on breach, clamp to hard_max, unknown-agent error shapes), decision boosts (clamp to [0,1], priority preserved, evidence annotated).

### Deferred to v0.0.3+
- Hermes adapter concrete implementation (pending tool-use format decision).
- LangGraph / CrewAI / OpenAI Agents SDK / Claude Agent SDK / Pydantic AI concrete adapters.
- Embedding signal (`sentence-transformers/all-MiniLM-L6-v2`).
- Semantic response cache (`sqlite-vec` backend).
- `chuzom_agent_route` wiring to `chuzom.router.route_and_call` (currently returns `would_route: true` + step metadata; caller dispatches).
- Empirical `quality_gap` + `handoff_penalty` lookup tables deriving from lineage outcomes.

---

## v0.0.1 — Genesis (private fork from llm-router)

### Added
- Forked llm-router → chuzom. Package renamed, CLI binary renamed, all internal references updated.
- New module skeletons: `chuzom/signals/`, `chuzom/decisions/`, `chuzom/cache/`, `chuzom/hosts/`, `chuzom/lineage.py`.
- Config template at `config/signals.yaml` defining the v0 signal/decision DSL.
- Architecture design at `Docs/ARCHITECTURE.md` (local-only, gitignored).

### Carried over from llm-router
- Multi-provider routing chain (Ollama → Codex → cheap API → premium).
- MCP server + tool surface (`llm_query`, `llm_research`, `llm_analyze`, `llm_code`, `llm_generate`, `llm_image`, `llm_orchestrate`).
- Hooks system (auto-route, enforce-route, session-end, usage-refresh).
- Cost tracking + circuit breaker per provider.
- Caveman mode for token-efficient output.

### Deferred to v0.2+
- Full implementation of signal/decision engine (v0 ships scaffolding only).
- Semantic response cache backed by sqlite-vec.
- Empirical lookup tables (quality_gap, handoff_penalty).
- Reask, fact-check, reasoning-effort signals.
