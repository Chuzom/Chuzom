# Project Instructions

## Chuzom routing — cost-aware LLM routing

Chuzom MCP tools route each task to the cheapest capable model (Ollama → Flash → GPT-4o → Claude).
Call the relevant tool BEFORE generating your own answer — relay the routed result to the user.

> **Pull routing note:** Unlike Claude Code (which intercepts prompts via hooks automatically),
> Kimi Code uses pull routing: YOU must call the tool. The tool returns the response.

| Task | Tool |
|---|---|
| Code generation, refactors, tests | `llm_code` |
| Questions, explanations, how-to | `llm_query` |
| Debug, review, analysis | `llm_analyze` |
| Research, current events, docs | `llm_research` |
| Prose, docs, email | `llm_generate` |
| Deep reasoning, proofs, root cause | `llm_reason` |

Never skip routing for non-trivial tasks. Chuzom routes to the cheapest capable model, saving 60–90%.
