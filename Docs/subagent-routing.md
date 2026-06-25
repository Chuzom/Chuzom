# Subagent Routing — applying Chuzom inside the Agent tool

Status: design + initial implementation (`hooks/agent-route.py`)
Author: routing-architecture pass, 2026-06

---

## Problem

Chuzom routes the **main session** by intercepting `UserPromptSubmit` (classify → inject
`⚡ MANDATORY ROUTE` → write `pending_route`), then gating tools at `PreToolUse` until an
`llm_*` call satisfies the route. It can also *directly execute* a main-session prompt on a
cheap model (`direct_executor`) and return the answer via `{"decision":"block"}`, so Claude
never spends subscription tokens.

**Subagents got none of this.** When Claude spawns an `Agent`, the only lever was
`PreToolUse[Agent]` (`agent-route.py`), which either:
- **approved** the spawn → the subagent ran its *entire* internal loop on the full inherited
  Claude model (Opus/Sonnet), unrouted; or
- **blocked** it → told the parent to make a single-shot `llm_*` call (losing tools/iteration).

There was no "route the subagent's work onto the cheapest capable model **and** log the
savings." This document specifies that path.

## Goal

1. **Route subagent work across every provider tier** (Ollama → Gemini → OpenAI/Codex → Claude)
   selected by **task type × complexity × quota pressure** — reusing the existing
   `chain_builder` + `direct_executor` engines.
2. **Log savings for every routed subagent** into the same SAVINGS pipeline the main session
   uses (`savings_log.jsonl` → `savings_stats`, plus `usage`/`routing_decisions`), tagged with a
   distinct `host` so subagent savings are attributable.
3. **Never trap.** Anything too big or that genuinely needs the Claude harness falls back to a
   real spawn. Fail-open on every error.

---

## The engines that already exist (no new runtime needed)

| Concern | Module | Reused as-is |
|---|---|---|
| Pick provider/model chain by complexity+pressure | `hooks/chain_builder.py` `build_chain` | ✅ |
| Single-shot text exec (Q&A) | `hooks/direct_executor.py` `execute_chain` | ✅ |
| Tool-using loop (file ops) on Ollama | `hooks/agent_loop.py` via `direct_executor.execute_agent` | ✅ |
| External agent CLIs | `gemini_cli_agent.run_gemini_cli`, `codex_agent.run_codex` | ⏳ phase 2 |
| Savings → JSONL | `hooks/savings_logger.py` `log_direct_savings` | ✅ (new `host` tag) |
| Savings → usage/routing_decisions | `hooks/savings_logger.py` `log_direct_to_db` | ✅ |
| Session/budget/lineage governance | `agents/`, `tools/agents.py` | ⏳ phase 2 |

The subagent path is **symmetric with the main-session DIRECT path** in `auto-route.py`. The one
thing that makes it possible: `PreToolUse[Agent]` receives `tool_input.prompt`, so it can
classify, execute, and return the result as the block `reason` — exactly how `auto-route`
returns direct answers.

---

## Architecture

```
 Parent spawns Agent(prompt, subagent_type)
        │
        ▼
┌──────────────────────── PreToolUse[Agent]  hooks/agent-route.py ─────────────────────────┐
│                                                                                          │
│  Explore / allowlisted / retrieval-only ─────────────────────────► APPROVE (spawn)       │
│  depth ≥ MAX ─────────────────────────────────────────────────────► BLOCK (circuit break)│
│                                                                                          │
│  classify(prompt) → (task_type, complexity)                                              │
│                                                                                          │
│  ┌─ DISPATCH LADDER (CHUZOM_SUBAGENT_DIRECT=on) ───────────────────────────────────────┐ │
│  │  complexity simple|moderate:                                                         │ │
│  │     zone,pct   = chain_builder.get_current_pressure()                                │ │
│  │     chain      = chain_builder.build_chain(complexity, zone, task_type)              │ │
│  │                  → [ollama/… , gemini/… , openai|codex/…]  (every model kind)        │ │
│  │     needs_tools? execute_agent(prompt, chain)   else execute_chain(prompt, chain)    │ │
│  │        success + quality_ok →                                                        │ │
│  │            stderr banner  🎯 subagent routed → provider/model · task/complexity      │ │
│  │            log_direct_savings(host="claude_code_subagent")   ── SAVINGS ──┐          │ │
│  │            log_direct_to_db(...)                                          │          │ │
│  │            return {"decision":"block","reason": <result>}  ◄─ parent gets routed out │ │
│  │        else ▼ fall through                                                │          │ │
│  │  complexity complex  OR  direct failed:                                   │          │ │
│  │     APPROVE spawn  (optionally Option-A: pin cheapest viable Claude tier) │          │ │
│  └──────────────────────────────────────────────────────────────────────────┘          │ │
└──────────────────────────────────────────────────────────────────────────────────────────┘
        │                                                          │
        ▼ block+result                                            ▼ SAVINGS pipeline
   Parent uses routed output                       savings_log.jsonl ──(session-end import)──►
   in place of the subagent                        savings_stats / usage / routing_decisions ──► dashboard
```

### Why execute-in-hook (and its limit)

A `PreToolUse` hook runs synchronously and blocks Claude Code for its duration — the same
tradeoff `auto-route` already accepts for main-session prompts. So the **dispatch ladder only
DIRECT-executes simple/moderate tasks**; `complex` tasks (and any direct failure) fall back to a
real spawn, keeping the hook snappy and never trapping large work. Hook timeout is bounded by
`execute_chain` (15s) / `execute_agent` (60s) caps plus a complexity gate.

---

## Savings accounting — "track every kind of savings"

Every routed subagent emits the **same record shape** as main-session DIRECT routing, with
`host="claude_code_subagent"`:

```json
{ "timestamp":"…","session_id":"…","task_type":"code","complexity":"moderate",
  "estimated_saved": 0.0123, "external_cost": 0.0,
  "model":"ollama/qwen3-coder:30b", "input_tokens":…, "output_tokens":…,
  "host":"claude_code_subagent" }
```

- `estimated_saved = baseline_cost(complexity) − external_cost`, where the baseline is the Claude
  tier the subagent *would* have burned (simple→Haiku, moderate→Sonnet, complex→Opus).
- `session-end.py` already flushes `savings_log.jsonl` → `savings_stats`; no extra wiring.
- The distinct `host` lets the dashboard separate three savings streams:
  `claude_code` (main DIRECT) · `claude_code_subagent` (this) · CC-subscription counterfactuals
  (`usage.db` via `cc-usage-track.py`).

So total tracked savings = main-session DIRECT + **subagent DIRECT** + subscription-tier
counterfactuals.

---

## Configuration

| Env var | Default | Effect |
|---|---|---|
| `CHUZOM_SUBAGENT_DIRECT` | `on` | Master switch for subagent DIRECT execution |
| `CHUZOM_SUBAGENT_DIRECT_MAX_COMPLEXITY` | `moderate` | Highest complexity to execute in-hook (`simple`/`moderate`/`complex`) |
| `CHUZOM_SUBAGENT_CLI_DELEGATION` | `on` | Master switch for the CLI-delegation tier (Codex / Gemini CLI) |
| `CHUZOM_SUBAGENT_CLI_TIMEOUT` | `120` | Max seconds for a delegated CLI run before falling back |
| `CHUZOM_CODEX_MODELS` | — | Override Codex model list (set to a model the account has) |
| `CHUZOM_SUBAGENT_GOVERNANCE` | `on` | Record each routed run as a governed `agents/` session |
| `CHUZOM_SUBAGENT_MODEL_PIN` | `on` | Pin lightweight spawned subagents (Explore/retrieval) to Haiku |
| `CHUZOM_AGENT_ROUTE_ALLOW` | — | Subagent types that bypass routing (real tool-work agents) |
| `CHUZOM_ROUTE_BANNER` | `on` | stderr `🎯 routed →` banner |

---

## Phasing

- **Phase 1 (done):** dispatch ladder + savings logging for simple/moderate subagents via
  `execute_chain` / `execute_agent` (Ollama for tools). Fall back to spawn otherwise.
- **Phase 2 (done):** `.env` self-loading in `agent-route.py` (so `OLLAMA_BUDGET_MODELS` + keys
  reach `build_chain` → DIRECT prefers **free local** models); CLI delegation
  (`_try_cli_delegation`) routing tool-heavy/complex subagents to `run_codex` / `run_gemini_cli`,
  bounded by `CHUZOM_SUBAGENT_CLI_TIMEOUT`, savings tagged `host="claude_code_subagent_cli"`.
- **Phase 3 (done):** every routed subagent run is recorded as a governed `agents/` session
  (`_govern_run` → `SessionStore.create/record_step/complete` in `~/.chuzom/sessions.db`):
  `agent_id="subagent:<type>"`, budget cap = Claude-equivalent baseline, consumed = actual
  external cost, `framework="chuzom-subagent-route"`. The cap−consumed gap is the saving,
  auditable at the governance layer. Gated by `CHUZOM_SUBAGENT_GOVERNANCE`. Fire-and-forget.
- **Phase 4 (done, conservative scope):** Option-A model-pin for lightweight *spawned* subagents.
  Explore + retrieval-only agents (which run on inherited Opus today) are pinned to **Haiku** via
  PreToolUse input rewriting — `{"hookSpecificOutput":{"permissionDecision":"allow",
  "updatedInput":{...,"model":"haiku"}}}`. The spawn keeps the full harness, just on a cheaper
  tier. If the host ignores `updatedInput`, the `allow` still holds (graceful). Gated by
  `CHUZOM_SUBAGENT_MODEL_PIN`. Pinning allowlisted tool-work agents (code-reviewer/Plan) by
  complexity is the deliberate next increment.

### Operational notes (this environment)
- `run_codex` needs a model the account actually has. Defaults `gpt-5.5`/`gpt-5.4` return 404 here
  — set `CHUZOM_CODEX_MODELS` to a valid model. The CLI tier falls back gracefully until then; a
  wrong model retries 5×, so keep `CHUZOM_SUBAGENT_CLI_TIMEOUT` bounded.
- Gemini CLI is not installed here (`is_gemini_cli_available()` False); Codex is preferred.

---

## Verification

1. **Unit:** feed a crafted `PreToolUse[Agent]` payload to the hook on stdin; assert it returns a
   `block` with routed output and appends one `claude_code_subagent` record to `savings_log.jsonl`.
2. **End-to-end:** spawn a real simple subagent; confirm the parent receives routed text and the
   savings record lands; run `import_savings_log()` and read `savings_stats` to confirm the figure
   reaches the dashboard.
```
