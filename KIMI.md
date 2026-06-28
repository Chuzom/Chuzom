# Kimi Code — Chuzom Routing Instructions

## Setup

Add the Chuzom MCP server to Kimi Code's MCP configuration:

```json
{
  "mcpServers": {
    "chuzom": {
      "command": "chuzom",
      "args": []
    }
  }
}
```

Then install Chuzom (if not already installed):

```bash
pip install chuzom-router
chuzom install   # registers hooks and MCP server
```

---

## Routing Instructions

Chuzom MCP tools route each task to the cheapest capable model
(Ollama local → Codex → Gemini Flash → GPT-4o → Perplexity).

Call the relevant tool BEFORE generating your own answer — relay the routed result to the user.

> **Pull routing:** Unlike Claude Code (which intercepts prompts via hooks automatically),
> Kimi Code uses pull routing: YOU must call the tool. The tool returns the response;
> relay it verbatim. Do not paraphrase or supplement unless critical context is missing.

## Task → Tool Mapping

| Task | Tool | Notes |
|---|---|---|
| Code generation, refactors, tests | `llm_code` | Ollama → Codex → o3 |
| Questions, explanations, how-to | `llm_query` | Ollama → Gemini Flash |
| Debug, review, analysis | `llm_analyze` | Ollama → GPT-4o |
| Research, current events, live docs | `llm_research` | Perplexity (web-grounded) |
| Prose, docs, email, content | `llm_generate` | Gemini Flash → Haiku |
| Deep reasoning, proofs, root cause | `llm_reason` | Extended-thinking model |

## Rules

1. Call the matching tool **before** generating your own response.
2. Return the tool's output **as-is** (don't paraphrase).
3. Only use native Kimi intelligence for file navigation, terminal commands,
   or when all Chuzom MCP servers are unavailable.
4. Never skip routing for non-trivial tasks — Chuzom saves 60–90% vs native model cost.
