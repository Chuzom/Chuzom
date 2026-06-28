---
description: Route tasks through Chuzom to save tokens and cost
trigger: always_on
---

# Chuzom routing — use MCP tools before answering directly

Chuzom MCP tools route each task to the cheapest model that can handle it.
Calling them before generating your own answer saves 60–90% of token cost.

> **Important — pull routing:** Unlike Claude Code (which intercepts prompts
> automatically via hooks), Windsurf uses pull routing: YOU must call the tool.
> The tool returns the response; relay it to the user instead of generating
> your own answer.

## When to call which tool

| User request type | Tool to call first |
|---|---|
| Write / refactor / fix code | `llm_code(prompt=..., complexity="moderate")` |
| Quick question / definition / how-to | `llm_query(prompt=..., complexity="simple")` |
| Debug / analyze / review code | `llm_analyze(prompt=...)` |
| Research / current events / docs | `llm_research(prompt=...)` |
| Write prose / docs / email | `llm_generate(prompt=...)` |
| Deep reasoning / proofs / root cause | `llm_reason(prompt=...)` |

## Rules

1. Call the matching tool **before** generating your own response.
2. Return the tool's output to the user **as-is** (don't paraphrase).
3. Only use native Windsurf intelligence for file navigation, terminal commands,
   or when all Chuzom MCP servers are unavailable.
4. If `llm_code` or similar is unavailable, proceed normally and note it.
