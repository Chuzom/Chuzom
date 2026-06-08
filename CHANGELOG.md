# Changelog

## Unreleased — Security: agoragentic marketplace tools moved to opt-in

> **Security advisory.** This entry closes a High finding from the 2026-06 internal audit (`Docs/audit/FINDINGS.md` — F-SEC-003). The pre-fix behaviour exposed payment-signing capability to any MCP client by default.

### Security

- **SEC-003 — `agoragentic_*` MCP tools are now opt-in (BREAKING).** Prior versions registered four marketplace tools (`agoragentic_task`, `agoragentic_browse`, `agoragentic_wallet`, `agoragentic_status`) by default, even when `CHUZOM_SLIM=routing` was set. **`agoragentic_task` performs USDC settlement on the Base L2 blockchain** — it can spend real money via the credentials stored at `~/.chuzom/agoragentic.json`. An LLM agent enumerating tools, an MCP client probing the tool list, or a hallucinated tool call could trigger an unintended on-chain transaction. The four tools are now gated behind `CHUZOM_AGORAGENTIC=on` (or `1`/`true`/`yes`). Without the opt-in, `mcp.list_tools()` exposes zero `agoragentic_*` entries.

### Breaking changes

- `agoragentic_*` tools are NOT registered unless `CHUZOM_AGORAGENTIC=on` is set. MCP clients that previously discovered these tools at startup will see them disappear until they set the env var.

### Operator notes

- **If you were intentionally using the Agoragentic marketplace:** add `CHUZOM_AGORAGENTIC=on` to the environment that launches the MCP server. The credentials file at `~/.chuzom/agoragentic.json` is unchanged.
- **If you were not using it:** no action required. The four tools simply disappear from the MCP tool list.
- **If you discover unauthorised on-chain activity from `~/.chuzom/agoragentic.json`'s `agent_id` predating this release:** rotate the API key, revoke the agent, and review settlements on the Base L2 explorer. The pre-fix default was exploitable.

### Added

- `tests/test_agoragentic_opt_in.py` — 18 regression tests covering the env-gate truth table (affirmative values, falsy values, missing env, malformed values) and verifying both `register()` behaviour and the internal `_agoragentic_enabled` helper.

### Notes for the wider remediation roadmap

- This is the minimum-viable mitigation (work-plan Option B). A follow-up effort should **document** the Agoragentic integration in the README (work-plan Option A, scheduled month 2) and **decide** whether payment-signing belongs in the MCP tool surface at all, given that an LLM agent invoking the tool is the user-paying-money primitive.

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
