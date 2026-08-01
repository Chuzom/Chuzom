# Plan: Route everything through Chuzom — observability & enforcement

Goal: use Chuzom's routing far more — every LLM query (Claude Code main turns,
subagents, AND external agents) routed to the right model and visible in the ledger.

## LLM surfaces

| Surface | Mechanism | Status |
|---|---|---|
| A. Claude Code main turns | `UserPromptSubmit → auto-route` (DIRECT exec) | ✅ routes |
| B. Claude Code subagents | `PreToolUse → agent-route` + `enforce-route` | ✅ routes |
| C. External agents (Stockagent, cron, Agno) | **Chuzom gateway** (was: direct litellm) | ✅ **fixed (1a/1b)** |

Surface C was the whole gap and where the token volume is.

## Part 1 — Route 100% of LLM operations
- **1a. OpenAI-compatible gateway** — `src/chuzom/gateway.py`, `chuzom gateway` CLI.
  Wraps `build_chain`+`execute_chain`, meters into `usage.db`+`savings_log`. Any client
  routes via `OPENAI_BASE_URL=http://127.0.0.1:17900/v1`. **DONE — live-tested + meters.**
- **1b. Stockagent through the gateway** — `stockagent/llm.py` routes via gateway with
  direct-provider fallback. **DONE — live-tested, lands in ledger.**
- **1c. Thin Python SDK** (`from chuzom import route`) — TODO.
- **1d. Chat-routing aggressiveness** — route through the right model all the time,
  without the enforce hook blocking itself. TODO (loosen `needs_claude_tools` / soft enforce).
- **Persistence** — run the gateway as a launchd service so external agents always route. TODO.

## Part 2 — Routing observability suite + report  (TODO)
`tests/routing_observability/` fires scenarios (simple Q&A · research · code · file-op ·
subagent · gateway call · high-pressure) and records: routed? · model · tokens in/out ·
latency (incl. model-swap penalty) · saved$. Generates `var/routing_report.md` from
usage.db + model_tracking.jsonl + session_spend.json + enforcement.log + auto-route-debug.log.

## Part 3 — Per-change CI: test + report  (TODO)
`make verify`: unit + routing-integration tests + regression report (perf/tokens/routing
matrix + diff vs last run); gates release (extends version-sync + clean-room checks).

## Part 4 — Enforce Chuzom for all agents  (TODO)
- Subagents: already enforced (agent-route); add a test that new types are intercepted.
- External agents: gateway = only sanctioned path; `chuzom-client` wrapper + `OPENAI_BASE_URL`
  in shared env + CI lint that fails on direct `litellm`/`openai`/`google.generativeai` calls.
- Cron: same gateway env var.

## Decisions (locked)
- Transport: **HTTP `/v1` gateway** (universal).
- Aggressiveness: **route through the right model all the time, without blocking** (1d).
