# Routing Chains, Profiles & Policies

The model tried depends on task complexity. Chuzom tries each tier in order, falling
back on failure or timeout.

## Routing chains

| Complexity | Profile | Tier 1 (cheapest) | Tier 2 | Tier 3 | Fallback |
|---|---|---|---|---|---|
| **simple** | BUDGET | Ollama (local/free) | Codex CLI | Gemini Flash | Haiku |
| **moderate** | BALANCED | Ollama (local/free) | Codex CLI | GPT-4o | Sonnet |
| **complex** | PREMIUM | Codex CLI | OpenAI o3 | Claude Opus | Gemini 2.5 Pro |
| **deep_reasoning** 🧠 | REASONING | Ollama qwen3 | DeepSeek-R1 | OpenAI o3 | Claude Opus + thinking |

## Subagent routing — savings inside the Agent tool

Chuzom routes **subagent spawns**, not just top-level prompts. When Claude Code's
`Agent` tool fires, the `agent-route` hook applies the same funnel before an expensive
subagent ever starts:

| Tier | What happens |
|---|---|
| **DIRECT** | simple/moderate subagents run on free-local (Ollama) or a cheap chain — the result is handed back, no Opus spawn |
| **CLI delegation** | tool-heavy / complex subagents delegate to **Codex / Gemini CLI** (external subscriptions, real toolchains) |
| **Model-pin** | lightweight Explore / retrieval spawns are pinned to **Haiku** instead of inherited Opus |
| **Governance** | every routed run is recorded as a budgeted session in `~/.chuzom/sessions.db` (cap vs consumed) |
| fall-through | anything that genuinely needs the full harness still spawns normally — never trapped |

Subagent savings are tracked under their own hosts (`claude_code_subagent`,
`claude_code_subagent_cli`), so they show up in your dashboard alongside main-session
routing. Full design: [subagent-routing.md](subagent-routing.md).

## The REASONING profile

When Chuzom detects a prompt that requires extended chain-of-thought reasoning —
formal proofs, first-principles derivations, multi-step deductive chains, or explicit
"think step-by-step" requests — it routes to the dedicated **REASONING profile**
instead of the generic PREMIUM chain.

What makes REASONING different:
- **DeepSeek-R1** (`deepseek-reasoner`) leads the chain — it costs **$0.0014/1K tokens**
  (28× cheaper than o3) and matches frontier reasoning quality on math and logic benchmarks
- **Extended thinking** is activated for every model that supports it: Gemini 2.5 Pro
  receives `thinkingConfig: {thinkingBudget: 8192}` and Claude Opus receives
  `thinking: {type: enabled, budget_tokens: 16000}`
- **OpenAI o3** handles problems R1 can't solve at R1's budget

**Trigger patterns** (auto-detected — no configuration needed):

```
Prove that...        →  🧠 deep_reasoning → DeepSeek-R1
Step by step...      →  🧠 deep_reasoning → DeepSeek-R1
Think through...     →  🧠 deep_reasoning → DeepSeek-R1
Walk me through...   →  🧠 deep_reasoning → DeepSeek-R1
Root cause analysis  →  🧠 deep_reasoning → DeepSeek-R1
```

Or call `llm_reason` directly from any MCP-compatible IDE:

```
llm_reason("Why does Dijkstra's algorithm fail with negative weights? Walk me through it.")
```

## Ollama dynamic discovery

Chuzom never uses hardcoded model names. It discovers your installed Ollama models in
this priority order:

1. `CHUZOM_OLLAMA_MODEL` env var (single model override)
2. `OLLAMA_BUDGET_MODELS` env var (comma-separated list)
3. `OLLAMA_MODELS` env var (comma-separated list)
4. `~/.chuzom/discovery.json` (auto-populated by `chuzom doctor`)
5. Safe default: `qwen3.5:latest`

```bash
# Use your own model
export CHUZOM_OLLAMA_MODEL=llama3.2:latest

# Or let chuzom discover what's running
chuzom doctor    # populates ~/.chuzom/discovery.json
```

## Agentic model pinning

Prefer a specific model for **agentic / tool-reasoning** tasks — `analyze`, `generate`,
`query`, and `research` — while keeping dedicated coders for `code`. When set, the
agentic model is pinned at the **absolute front** of the routing chain for those task
types, ahead of the generic Ollama injection and every other reorder:

```bash
# Env var (highest precedence)
export CHUZOM_AGENTIC_MODEL=ollama/hermes3:8b
```

```yaml
# Or in ~/.chuzom/routing.yaml (env > repo > user)
agentic_model: ollama/hermes3:8b
```

`code` tasks are intentionally excluded, so a coder pin (e.g.
`routing.code.model: ollama/qwen3-coder:30b`) still wins coding work.

---

## Routing policies

User-selectable routing policies tune the cost/quality/freedom tradeoff. Set once via
env var and forget:

```bash
export CHUZOM_ROUTING_POLICY=local-first   # in ~/.zshrc / ~/.bashrc
```

Or add it to your `.env`:

```
CHUZOM_ROUTING_POLICY=cost
```

### Available policies

| Policy | Symbol | What it does | Best for |
|---|---|---|---|
| `balanced` | ⚖️ | **Default.** Best cost/quality trade-off — cheap models first, Claude only when complexity demands it | Most users |
| `local-first` | 🏠 | Always try local Ollama models before any cloud provider, even for complex tasks | Offline / air-gapped work |
| `cost` | 💰 | Ruthlessly picks the cheapest capable model, using live per-token pricing | Budget-constrained teams |
| `quality` | 🏆 | Routes to the highest benchmark-score model for the task type ([artificialanalysis.ai](https://artificialanalysis.ai/leaderboards/models)) | Docs, complex analysis, code review |
| `quota-exhaustion` | 📊 | Avoids any provider whose quota is above 85% consumed | End-of-billing-cycle crunches |
| `dynamic` | 🔀 | Round-robins across providers within ±10% of each other in quota usage | Balancing load over long sessions |

### How policies work

Policies are applied **after** the full routing chain is built (after Ollama discovery,
Codex injection, Gemini CLI injection). Each policy sees the complete candidate list
and reorders it — it does not filter models out, so fallback always works.

```
Built chain:  [claude-sonnet-4, codex/gpt-5.5, gpt-4o, gemini-2.5-flash]
Policy cost:  [codex/gpt-5.5, gemini-2.5-flash, gpt-4o, claude-sonnet-4]
                ^free (prepaid)    ^cheaper API       ^mid       ^most expensive
```

### Quality scores (artificialanalysis.ai)

The `quality` policy uses benchmark scores per task type (`code`, `query`, `analyze`,
`generate`, `research`) cached in `data/benchmarks.json`. Scores are sourced from
[artificialanalysis.ai](https://artificialanalysis.ai/leaderboards/models) — a
third-party leaderboard that re-runs independent evaluations across providers.

### Leaderboard-driven chain ordering (opt-in)

The static routing chains are ordered *cheapest-capable-first* using live-leaderboard
quality scores. As of v1.0.0 the same ordering can be applied to the dynamic routing
table (used when provider discovery is active) via an opt-in flag:

```bash
export CHUZOM_DYNAMIC_LEADERBOARD_ORDERING=1   # default off
```

Default **off** preserves the audited routing behavior byte-for-byte; enabling it
aligns the dynamic path with the static path. BUDGET chains are never reordered — their
cheap-first order is the cost-saving behavior.
