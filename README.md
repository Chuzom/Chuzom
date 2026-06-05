# Tessera

> Signals compose into routing decisions like mosaic tiles.

**Tessera** is a lightweight, signal-driven LLM router that runs as an MCP server inside Claude Code, Cursor, Codex (OpenAI IDE), Codex CLI, and Gemini CLI. It classifies every prompt, routes it to the cheapest capable model across providers (Ollama, OpenAI, Gemini, Anthropic subscription, Perplexity), caches semantically-similar prompts, and tracks the full lineage of every decision.

## What it does

| Capability | How |
|---|---|
| **Signal-driven classification** | YAML-configurable signals: keyword (bm25/ngram/fuzzy), embedding (MiniLM), PII detector, complexity heuristics |
| **Composable decisions** | AND / OR / NOT composition over signals → model pick |
| **Semantic response cache** | sqlite-vec + embedding similarity — reuse answers across semantically-equivalent prompts |
| **Routing lineage** | every decision stored: signals, complexity, chain attempted, model chosen, outcome, latency, cost |
| **Inversion detection** | flags when classified-complex prompts get routed to cheap models (or vice-versa) |
| **Multi-CLI** | one MCP server, host adapters for Claude Code, Cursor, Codex IDE, Codex CLI, Gemini CLI |
| **Cost-aware fallback** | free-first chain: Ollama → Codex (subscription) → cheap API → Claude/GPT premium |

## Install

```bash
pip install tessera-router
tessera install --host claude-code   # or cursor / codex / codex-cli / gemini-cli
```

## Status

Early alpha. v0 ships the rebranded foundation + new signal / decision scaffolding + semantic cache + lineage modules.

## License

MIT.
