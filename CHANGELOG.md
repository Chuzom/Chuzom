# Changelog

## v0.0.2 — Agent layer + framework adapters + benchmark harness

### Added
- **`tessera/agents/` module** — agent-aware routing without owning the agent loop.
    - `AgentProfile` dataclass — tier preference, signal boosts, preferred chain, budget envelope.
    - `AgentRegistry` — YAML-loaded (`config/agents.yaml`); 3 default profiles ship: `code-reviewer`, `trend-researcher`, `tdd-guide`.
    - `AgentSession` + `SessionStore` — SQLite-backed at `~/.tessera/sessions.db`. State machine: ACTIVE → COMPLETED / ERRORED / BUDGET_EXCEEDED. Nested sessions via `parent_session_id` with full descendant `rollup`.
    - `BudgetEnvelope` + `BudgetExceeded` — immutable envelope, pre-emptive `would_exceed`, raise-or-pass `raise_if_would_exceed`.
- **`tessera/tools/agents.py`** — 6 MCP tools:
    - `tessera_agent_list` / `tessera_agent_start_session` / `tessera_agent_check_budget` / `tessera_agent_route` / `tessera_agent_complete_session` / `tessera_agent_lineage`.
    - Budget enforcement at the route boundary — sessions refuse calls that would breach.
- **`tessera/frameworks/` module** — adapter shape for agent frameworks.
    - `FrameworkAdapter` protocol (3 methods: `wrap_model`, `detect_agent_id`, `is_available`).
    - **Agno** — concrete, re-exports `RouteredModel` + `RouteredTeam` from `tessera.integrations.agno`.
    - **Hermes** — skeleton; v0.0.3 lands the concrete tool-use protocol.
    - **LangGraph / CrewAI / OpenAI Agents SDK / Claude Agent SDK / Pydantic AI** — adapter stubs.
- **Lineage schema extension** — 5 new optional columns: `agent_id`, `session_id`, `step_index`, `parent_session_id`, `framework`. Idempotent migration handles pre-v0.0.2 databases via `ALTER TABLE ADD COLUMN` with duplicate-column guard. New indexes on `session_id` and `agent_id`.
- **Decision engine boosts** — `DecisionEngine.choose(scores, boosts={"signal": multiplier})`. Applied as score multipliers; thresholds untouched; scores clamped to [0,1]. Evidence annotated so lineage shows the boost was active.
- **`bench/` benchmark harness** — router-agnostic head-to-head comparison.
    - `Router` protocol — any router that returns `RouterResult` competes.
    - Built-in routers: `TesseraRouter`, `FixedModelRouter` (cheap/premium endpoints), `StaticChainRouter` (ablation).
    - Hybrid judge: deterministic substring grading for objective prompts, LLM-as-judge for subjective.
    - Pareto frontier — only routers worth picking from at any quality budget.
    - Smoke corpus (5 easy + 5 moderate).
- **Local installability** — `pip install -e .` now works cleanly. CLI binary `tessera`, `tessera doctor`, full subcommand surface verified.

### Changed
- `tessera/cache/` package now re-exports legacy `get_cache` / `ClassificationCache` from `cache/classification.py` (moved from `tessera/cache.py`) alongside the new `SemanticCache` skeleton.
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
- `tessera_agent_route` wiring to `tessera.router.route_and_call` (currently returns `would_route: true` + step metadata; caller dispatches).
- Empirical `quality_gap` + `handoff_penalty` lookup tables deriving from lineage outcomes.

---

## v0.0.1 — Genesis (private fork from llm-router)

### Added
- Forked llm-router → tessera. Package renamed, CLI binary renamed, all internal references updated.
- New module skeletons: `tessera/signals/`, `tessera/decisions/`, `tessera/cache/`, `tessera/hosts/`, `tessera/lineage.py`.
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
