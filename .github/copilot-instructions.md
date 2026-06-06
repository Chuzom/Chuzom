<!-- llm-router-rules-version: 1 -->
# LLM Router — VS Code / GitHub Copilot Routing Rules

> These rules apply when using llm-router MCP tools inside VS Code with GitHub Copilot.
> VS Code loads MCP servers from .vscode/mcp.json (workspace) or the user mcp.json.
> Use `llm_auto` for routing + cross-session savings tracking.

---

## How to Route

VS Code loads MCP servers on startup. Once llm-router is registered, call tools by name:

```
Rule: for research/generate/code/analyze tasks → call llm_auto(prompt=<the task>)
```

Add to `.github/copilot-instructions.md` for workspace-level routing guidance:

```
When a task requires live web search, call the llm_research MCP tool.
For code generation or complex analysis, call llm_code or llm_analyze.
For auto-routing with savings tracking, call llm_auto.
```

---

## Task Type → Tool Mapping

| Task | Tool | Notes |
|---|---|---|
| Simple factual question | `llm_query` | Gemini Flash / Groq |
| Research / current events | `llm_research` | Perplexity (web-grounded) |
| Writing / content | `llm_generate` | Gemini Flash / Haiku |
| Deep analysis | `llm_analyze` | GPT-4o / Gemini Pro |
| Code generation | `llm_code` | Ollama → Codex → o3 |
| Unknown / auto-detect | `llm_auto` | Classifies + routes |

---

## Savings Visibility

Run `llm_savings` in Copilot Chat to see cross-session totals.

---

## Token-Efficient Responses

Skip preamble. Lead with result. Fragments fine when meaning is clear.
No trailing summaries. ≥3 items → bullets. Never restate the user's request.


# chuzom Routing Rules for VS Code

This section configures chuzom for optimal cost-aware LLM routing.

## Smart Routing Strategy

- **Research & web queries**: Route via `llm_research` for web-grounded answers
- **Code generation**: Route via `llm_code` for implementation tasks
- **Content creation**: Route via `llm_generate` for writing and documentation
- **Deep analysis**: Route via `llm_analyze` for complex problem-solving
- **Quick questions**: Route via `llm_query` for simple lookups

## Usage in VS Code

Press **Ctrl+L** to access the chuzom prompt. The MCP server automatically:
- Classifies task complexity (simple/moderate/complex)
- Routes to optimal LLM provider (local Ollama → cloud APIs → Claude)
- Tracks spending and applies budget pressure
- Caches classification results for consistency

## Tips

- Start with `llm_auto` for automatic intelligent routing
- Use `llm_research` for current events and web-based information
- Use `llm_code` with complexity hints for better model selection
