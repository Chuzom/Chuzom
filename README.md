<p align="center">
  <img src="https://raw.githubusercontent.com/Chuzom/chuzom/main/assets/chuzom-logo.png" alt="Chuzom — Local LLM routing for developers" width="320">
</p>

<h1 align="center">Chuzom</h1>

<p align="center">
  <strong>Automatic, local LLM routing — save 35–80% on API costs.</strong><br/>
  Sends each prompt to the cheapest model that can actually do the job.<br/>
  Works with Claude Code, Cursor, Codex CLI, Gemini CLI, and more. No proxy. No account.
</p>

<p align="center">
  <a href="https://pypi.org/project/chuzom-router/"><img src="https://img.shields.io/badge/pypi-chuzom--router-4F46E5?style=flat-square" alt="PyPI"></a>
  <a href="https://github.com/Chuzom/chuzom/actions"><img src="https://github.com/Chuzom/chuzom/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Chuzom/chuzom/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-10B981?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10+-3572A5?style=flat-square" alt="Python">
</p>

---

## Supported IDEs

Chuzom integrates with your favorite dev tools:

| IDE | Support | Command |
|---|---|---|
| **Claude Code** (Claude Desktop) | ✅ | `chuzom install --host claude-code` |
| **Cursor** | ✅ | `chuzom install --host cursor` |
| **Codex CLI** | ✅ | `chuzom install --host codex` |
| **Gemini CLI** | ✅ | `chuzom install --host gemini-cli` |
| **All supported** | ✅ | `chuzom install --host all` |

---

## Install (30 seconds)

```bash
pip install chuzom-router
chuzom install --host claude-code    # choose your IDE
chuzom summary --watch               # watch your savings live
```

Bring API keys for providers you want (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or local Ollama via `OLLAMA_BASE_URL`).

**Works with zero API keys** if you have Claude Code Pro/Max or Codex subscription — uses local credentials.

---

## How it works

Every prompt you send flows through a smart routing pipeline:

```
YOUR PROMPT
    ↓
    ├─ 1. Classify (What type of task? How complex?)
    │
    ├─ 2. Build a model chain (Cheapest → best, ordered)
    │    • Simple questions  → Gemini Flash or Claude Haiku ($0.001/task)
    │    • Code/math         → GPT-4o or Claude Sonnet ($0.01/task)
    │    • Hard reasoning    → o3 or Claude Opus ($0.10/task)
    │
    ├─ 3. Detect risks (PII/secrets? → use local models only)
    │
    ├─ 4. Send to first model that can handle it
    │
    └─ 5. Log the decision locally (no telemetry, no proxy)

RESULT + savings banner
    ↓
    🎯 chuzom → claude-3.5-sonnet · code/moderate · 342ms · saved $0.08
```

**That's it.** Your IDE works the same, but every decision saves money.

---

## Cost savings in practice

On a typical developer's workload (mix of explanations, code review, debugging):

- **Always use cheapest model:** $2–5/month (but fails on hard tasks)
- **Always use premium model:** $40–80/month (overkill for most work)
- **Chuzom (smart routing):** $8–15/month (saves 70–80% vs premium)

**Real example:** Asking Claude Opus to explain an error message costs $0.08. Chuzom routes to Haiku ($0.001) — **same answer, 80x cheaper.**

See [`python -m chuzom benchmark`](https://github.com/Chuzom/chuzom/blob/main/scripts/bench.py) for reproducible cost-vs-quality measurements.

---

## What you get

- ✅ **Drop-in for your IDE** — installs as an MCP server + hooks; workflow doesn't change
- ✅ **35–80% cost savings** — measured vs always-cheap and always-premium on a fixed corpus
- ✅ **Automatic model selection** — each prompt classified by task + complexity
- ✅ **Local decision logging** — every routing decision stays on your machine (no telemetry, no proxy)
- ✅ **Live savings dashboard** — `chuzom summary --watch` shows per-session spending
- ✅ **Circuit-breaker failover** — if a provider is down, automatically tries the next model
- ✅ **PII/secret detection** — prompts with credentials route to local models only
- ✅ **Per-reply banner** — see which model handled your prompt and how much you saved

---

## CLI

```bash
chuzom install [--host <name>|all]   # wire into a dev tool
chuzom doctor                         # verify hooks, MCP, provider keys
chuzom summary [--watch]              # cost dashboard (live or one-time)
chuzom --version
```

---

## Under the hood

Chuzom is a **local MCP server** that intercepts your IDE's model requests. It:

1. Analyzes the prompt (task type, complexity, sensitivity)
2. Builds an ordered chain of capable models (cheapest first)
3. Sends to the first model that can handle the task
4. Logs the decision locally + returns your answer + a savings banner

All routing happens on your workstation. No data leaves your machine. No proxy. No account required.

---

## Contributing

Full test suite runs in CI on every push (Python 3.10+). Contributions welcome — see [`CONTRIBUTING.md`](https://github.com/Chuzom/chuzom/blob/main/CONTRIBUTING.md).

---

## License

[MIT](https://github.com/Chuzom/chuzom/blob/main/LICENSE) © the Chuzom contributors.
