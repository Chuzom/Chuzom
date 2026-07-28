# Configuration Reference

All variables can be set in the shell or in `~/.chuzom/.env` (loaded automatically by
the hooks).

## CLI reference

```bash
chuzom install [--host claude-code|cursor|codex|gemini-cli|all]
                                     # Wire into your IDE(s)

chuzom doctor                        # Verify hooks, MCP server, provider keys, health

chuzom summary [--watch]             # Cost dashboard (live or one-time snapshot)

chuzom --version                     # Show installed version
```

## Common one-liners

```bash
# Use a specific Ollama model
export CHUZOM_OLLAMA_MODEL=qwen2.5-coder:7b

# Claude Pro/Max subscription (enables quota tracking)
export CHUZOM_CLAUDE_SUBSCRIPTION=true

# Change routing policy
export CHUZOM_ROUTING_POLICY=local-first   # or: cost, quality, balanced, dynamic

# Enforcement mode (see the ladder below)
export CHUZOM_ENFORCE=smart
```

## Enforcement Modes

Chuzom's enforcement hook (`enforce-route.py`) fires before every tool call when a
routing directive is active. It controls whether Claude can bypass routing and answer
directly. Set via env var or `~/.chuzom/routing.yaml` (env takes precedence).

| Mode | Behavior | Best for |
|---|---|---|
| `smart` (**default**) | Hard-blocks direct answers for Q&A tasks (query/research/generate/analyze) until routed. Allows file tools for code tasks. Auto-downgrades after repeated violations to prevent stuck sessions | The default — enforce routing out of the box |
| `soft` | Logs routing misses but **never blocks** any tool call. Route hints appear in context; the model can follow them voluntarily. Saves nothing unless the model volunteers | Advisory-only routing |
| `hard` | Blocks Bash/Edit/Write for **all** task types until an `llm_*` tool is called. Maximum quota enforcement | Power users who want maximum enforcement |
| `strict` | Like `hard` with all escape valves disabled (no auto-pivot, no read-only Bash exception). Sessions can deadlock | Compliance environments |
| `advise` | Routes prompts to cheap models, but the enforcement hook **never blocks any tool**. Zero friction | Testing / evaluation |
| `off` | Enforcement completely disabled. Routing directives still appear in context | Debugging routing |

**Auto-pivot** (prevents stuck sessions in `smart` / `hard`):
- **Per-turn trap** — 2 blocks of the *same tool* within a single user turn trigger an
  immediate auto-pivot for that turn.
- **Session counter** — each blocked tool call increments a session-wide counter; at 3
  violations you get an escalation warning, and at 4 enforcement auto-downgrades to
  `soft` for the rest of the session.

Both escape valves are disabled under `strict`. An investigation-loop detector (same
tool blocked 3+ times in 2 minutes) also releases the lock in non-strict modes.

**Escape valve:** prefix any prompt with `claude:` to bypass routing entirely for that
turn:

```
claude: explain this function to me
```

## Advanced configuration

### Direct execution mode (`CHUZOM_DIRECT_EXECUTION`)

By default (`true`), the `UserPromptSubmit` hook executes simple prompts directly from
the hook process. What happens next depends on `CHUZOM_RENDER_MODE` (default `auto`):

- **Self-contained prompts** (no reference to your files, code, or earlier turns) are
  rendered in `block` mode — the turn is answered entirely from the hook, Claude is
  never invoked, and zero subscription tokens are consumed.
- **Context-dependent prompts** are rendered in `echo` mode — the hook's result is
  passed to Claude as an unverified draft, and Claude still runs the turn. Only
  `CHUZOM_RENDER_MODE=block` or `CHUZOM_ZERO_CLAUDE=1` prevents a Claude turn entirely.

If direct execution fails (Ollama unreachable, all providers fail), the hook falls
through and injects a `⚡ MANDATORY ROUTE:` directive instead, so an MCP tool handles it.

```bash
export CHUZOM_DIRECT_EXECUTION=true    # default — answer from hook (self-contained only)
export CHUZOM_DIRECT_EXECUTION=false   # MCP-tool mode — Claude calls the MCP tool
```

### Session-context accumulator (`CHUZOM_SESSION_CONTEXT`)

Routed models answer stateless by default — a cheap drafted answer can't see the
session's files, decisions, or prior turns. Chuzom accumulates session events into a
durable per-session store at `~/.chuzom/session_context_<sid>.jsonl` and injects a
token-budgeted context block into every provider path.

```bash
export CHUZOM_SESSION_CONTEXT=all     # default — context sent to every provider
export CHUZOM_SESSION_CONTEXT=local   # strip before external openai/gemini targets
export CHUZOM_SESSION_CONTEXT=off     # routed calls stay stateless
```

**Fail-open:** any store or config failure falls back to routing without context.
Session stores are deleted at session end and pruned after 7 days.

### Subscription mode (`CHUZOM_CLAUDE_SUBSCRIPTION`)

When you have **Claude Pro or Max** (a subscription, not API keys):

```bash
export CHUZOM_CLAUDE_SUBSCRIPTION=true
```

This enables OAuth-based quota tracking (reads live usage from Claude Code's Keychain
token), pressure-aware routing (routes more aggressively when your 5-hour or weekly
quota is high), and the "Free subscription" tier in the session summary. Without it,
Chuzom treats Claude as a paid-API provider and tracks cost in dollars.

### Classifier behavior (`CHUZOM_CLASSIFY_LOCAL_ONLY`)

By default, Chuzom classifies prompts using local methods only (heuristic + Ollama), so
your prompts never leave your machine for classification.

```bash
export CHUZOM_CLASSIFY_LOCAL_ONLY=true    # default — heuristic + Ollama only
export CHUZOM_CLASSIFY_LOCAL_ONLY=false   # allow API classifiers when Ollama is absent
```

If unset, Chuzom auto-detects: if Ollama is unreachable but API keys are present, it
enables API classifiers automatically so routing accuracy doesn't silently degrade.

## Full environment variable reference

| Env var | Default | Description |
|---|---|---|
| `CHUZOM_OLLAMA_MODEL` | auto-discovered | Override the primary Ollama model |
| `OLLAMA_BUDGET_MODELS` | auto-discovered | Comma-separated budget model list |
| `OLLAMA_MODELS` | auto-discovered | Comma-separated full model list |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `CHUZOM_OLLAMA_TIMEOUT` | `4` | Per-call Ollama timeout in seconds |
| `CHUZOM_AGENTIC_MODEL` | _(unset)_ | Preferred model for agentic tasks (analyze/generate/query/research) |
| `CHUZOM_CODEX_MODELS` | `gpt-5.5,gpt-5.4` | Codex model fallback chain |
| `CHUZOM_CODEX_TIMEOUT` | `300` | Codex CLI timeout in seconds |
| `CHUZOM_CLAUDE_SUBSCRIPTION` | `false` | Enable subscription quota tracking mode |
| `CHUZOM_DIRECT_EXECUTION` | `true` | Answer prompts directly from hook; Claude skipped only when the render mode resolves to `block` |
| `CHUZOM_ENFORCE` | `smart` | Enforcement mode: `smart`, `soft`, `hard`, `strict`, `advise`, `off` |
| `CHUZOM_ROUTING_POLICY` | `balanced` | Routing policy: `balanced`, `local-first`, `cost`, `quality`, `quota-exhaustion`, `dynamic` |
| `CHUZOM_DYNAMIC_LEADERBOARD_ORDERING` | `off` | Apply leaderboard chain ordering to the dynamic routing table (opt-in) |
| `CHUZOM_CLASSIFY_LOCAL_ONLY` | auto | Restrict classification to local models only (privacy) |
| `CHUZOM_ROUTE_BANNER` | `on` | Show `🎯 Chuzom routed →` banner in terminal (`off` to hide) |
| `CHUZOM_ZERO_CLAUDE` | `false` | Zero-Claude mode: block native Claude turns; external route or block |
| `CHUZOM_SESSION_CONTEXT` | `all` | Session-context accumulator: `all`, `local`, `off` |
| `CHUZOM_SLIM` | `consolidated` | MCP tool surface: `consolidated` (11 doors) or `off` (legacy tools) |
| `CHUZOM_DELEGATE` | `on` | Enable the operational/execution → `llm_act` redirect |
| `PERPLEXITY_API_KEY` | _(unset)_ | API key for research routing via Perplexity |
| `GEMINI_API_KEY` | _(unset)_ | API key for Gemini Flash / Pro |
| `OPENAI_API_KEY` | _(unset)_ | API key for GPT-4o / o3 |
| `ANTHROPIC_API_KEY` | _(unset)_ | API key for direct Claude API (not subscription) |
