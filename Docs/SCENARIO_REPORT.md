# Chuzom Scenario Report

Each scenario below is a *story*, not just a pass/fail.
The trace shows every actor that touched the request — the
host CLI, the classifier, each signal, the decision engine,
the selector, the model, the provider, the lineage and
session stores — so you can audit what actually happened.

## Executive summary

| Metric | Value |
|---|---|
| Total scenarios | 2 |
| Passed | **2** |
| Failed | **0** |
| Total trace events | 16 |
| Cumulative duration | 1 ms |

### Per-CLI coverage

| CLI | Scenarios |
|---|---|
| `—` | 2 |

### Per-framework coverage

| Framework | Scenarios |
|---|---|
| `—` | 2 |

---

## Scenarios

## x-01 · Cascading failure: 3 providers down, 4th catches the ball

**Status:** ✅ PASS · **Duration:** 0 ms

### Narrative
A regional network issue takes Ollama, Codex, and OpenAI offline. Chuzom's selector walks the chain, records a failure for each, increments circuit breakers, and ultimately reaches Anthropic Claude which succeeds. The lineage row captures the full chain_attempted so the user can see exactly how many fallbacks were needed.

**Expected:** 3 failures recorded, 1 success, breaker opens for 3 providers, lineage shows full chain

### What really happened
1. **🎯 [selector]** chain resolved
     · chain=[ollama/qwen3.5:latest, codex/gpt-5-codex, openai/gpt-4o, anthropic/claude-sonnet-4.6]
2. **🤖 [model]** ollama/qwen3.5:latest FAILED
     · model='ollama/qwen3.5:latest' · success=False · cost_usd=0 · latency_ms=30000 · error='ConnectionError: network unreachable'
3. **🌐 [provider]** ollama/qwen3.5:latest: failure recorded
4. **🤖 [model]** codex/gpt-5-codex FAILED
     · model='codex/gpt-5-codex' · success=False · cost_usd=0 · latency_ms=30000 · error='ConnectionError: network unreachable'
5. **🌐 [provider]** codex/gpt-5-codex: failure recorded
6. **🤖 [model]** openai/gpt-4o FAILED
     · model='openai/gpt-4o' · success=False · cost_usd=0 · latency_ms=30000 · error='ConnectionError: network unreachable'
7. **🌐 [provider]** openai/gpt-4o: failure recorded
8. **🤖 [model]** anthropic/claude-sonnet-4.6 succeeded
     · model='anthropic/claude-sonnet-4.6' · success=True · cost_usd=0.018 · latency_ms=2700
9. **🌐 [provider]** anthropic/claude-sonnet-4.6: success recorded; breaker closed
10. **📜 [lineage]** record persisted
     · chain_attempted=[ollama/qwen3.5:latest, codex/gpt-5-codex, openai/gpt-4o, anthropic/claude-sonnet-4.6] · model_chosen='anthropic/claude-sonnet-4.6' · outcome='success'
     › _chain_attempted len=4_
11. **🏁 [outcome]** scenario complete
     · success=True
     › _User got an answer after 3 fallbacks. Lineage chain_attempted shows the full path. 3 provider breakers now in cooldown._

**Actual outcome:** User got an answer after 3 fallbacks. Lineage chain_attempted shows the full path. 3 provider breakers now in cooldown.

---

## x-07 · Health tracker: stale failures cleared at session start

**Status:** ✅ PASS · **Duration:** 1 ms

### Narrative
Provider 'flaky-api' failed N times yesterday. Its circuit breaker opened. Without intervention, every new Claude Code session would skip it forever. Chuzom's reset_stale() — called at session start — clears breakers older than 30 minutes so providers get a fresh chance each session.

**Expected:** stale provider reset, is_healthy returns True after reset

### What really happened
1. **🌐 [provider]** flaky-api: failed 10 times, breaker open
2. **🌐 [provider]** flaky-api: 1 hour elapsed since last failure
3. **🌐 [provider]** flaky-api: reset_stale returned ['flaky-api']
4. **🌐 [provider]** flaky-api: is_healthy after reset: True
5. **🏁 [outcome]** scenario complete
     · success=True
     › _Stale breaker cleared. Provider is available for retry. This prevents permanently-stuck-unhealthy state from yesterday's outages._

**Actual outcome:** Stale breaker cleared. Provider is available for retry. This prevents permanently-stuck-unhealthy state from yesterday's outages.

---
