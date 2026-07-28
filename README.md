# Chuzom — Extend Your Claude Quota. 3× Longer Sessions.

<!-- Package -->
[![PyPI version](https://img.shields.io/pypi/v/chuzom-router?style=flat-square&color=4F46E5)](https://pypi.org/project/chuzom-router/)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/chuzom-router?period=total&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=ORANGE&left_text=downloads)](https://pepy.tech/projects/chuzom-router)
[![Python](https://img.shields.io/pypi/pyversions/chuzom-router?style=flat-square&color=3572A5)](https://pypi.org/project/chuzom-router/)
[![License: MIT](https://img.shields.io/badge/license-MIT-10B981?style=flat-square)](https://github.com/Chuzom/Chuzom/blob/main/LICENSE)

<!-- Health -->
[![CI](https://img.shields.io/github/actions/workflow/status/Chuzom/Chuzom/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Chuzom/Chuzom/actions/workflows/ci.yml)
[![Last commit](https://img.shields.io/github/last-commit/Chuzom/Chuzom?style=flat-square&color=8B5CF6)](https://github.com/Chuzom/Chuzom/commits/main)
[![Commit activity](https://img.shields.io/github/commit-activity/m/Chuzom/Chuzom?style=flat-square&color=06B6D4)](https://github.com/Chuzom/Chuzom/pulse)
[![Open issues](https://img.shields.io/github/issues/Chuzom/Chuzom?style=flat-square&color=F59E0B)](https://github.com/Chuzom/Chuzom/issues)
[![Code size](https://img.shields.io/github/languages/code-size/Chuzom/Chuzom?style=flat-square&color=64748B)](https://github.com/Chuzom/Chuzom)

<!-- Community -->
[![GitHub Stars](https://img.shields.io/github/stars/Chuzom/Chuzom?style=flat-square&color=F59E0B)](https://github.com/Chuzom/Chuzom/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/Chuzom/Chuzom?style=flat-square&color=64748B)](https://github.com/Chuzom/Chuzom/network/members)
[![Contributors](https://img.shields.io/github/contributors/Chuzom/Chuzom?style=flat-square&color=EC4899)](https://github.com/Chuzom/Chuzom/graphs/contributors)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](./CONTRIBUTING.md)

<!-- Compatibility & flair -->
[![Claude Code](https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square)](https://claude.com/claude-code)
[![MCP](https://img.shields.io/badge/MCP-server-111827?style=flat-square)](https://modelcontextprotocol.io)
[![Code style: Ruff](https://img.shields.io/badge/code_style-ruff-261230?style=flat-square)](https://github.com/astral-sh/ruff)
[![Audited](https://img.shields.io/badge/audit-RELEASE_QUALIFIED-10B981?style=flat-square)](Docs/correctness-reset/03_RELEASE_GATES.md)

---

<p align="center">
  <img src="assets/hero-confluence.webp" alt="A marmot at a river confluence — rushing rapids on one side, deep calm water on the other — where fast and slow streams meet and each finds its path" width="92%"/>
</p>

<p align="center">
  <em>A <strong>Chuzom</strong> is a <strong>confluence</strong> — the place where rivers meet.<br/>
  Fast rapids and deep water, converging, each stream finding its natural path.<br/>
  That's the router: every prompt flows to the model that fits it, and your Claude quota is spent only where it counts.</em>
</p>

<p align="center">
  <strong>⭐ Star on GitHub if Chuzom saves your quota ⭐</strong><br/>
  <em>Help other developers discover automatic LLM routing</em>
</p>

---

**Chuzom** is a smart LLM router for AI coding tools. It reads each prompt, sends the
easy ones to free local or subscription models, and spends your Claude quota only on
the work that truly needs it — so a day's quota stretches across a full week of
sessions. Drop-in, zero workflow change, **and now independently audited** (see
[Measured results](#-measured-results-audited)).

```bash
pip install chuzom-router && chuzom install --host claude-code
```

## Contents

- [The Problem](#the-problem)
- [The Solution](#the-solution)
- [Why People Install This](#why-people-install-this)
- [📊 Measured Results (audited)](#-measured-results-audited)
- [Get Started (60 seconds)](#get-started-60-seconds)
- [How It Works](#how-it-works)
- [Supported IDEs](#supported-ides)
- [Routing at a Glance](#routing-at-a-glance)
- [Agentic Router](#agentic-router)
- [Companion Skill: `/council`](#-companion-skill-council)
- [Session Summary Dashboard](#session-summary-dashboard)
- [Configuration](#configuration)
- [More docs](#more-docs) · [FAQ](#faq) · [Contributing](#contributing) · [License](#license)

---

## The Problem

You're on **Claude Pro ($20/mo), Max ($100/mo), or Max ($200/mo)** — a flat
subscription, not pay-per-token.

But Claude Code routes **every request** through your quota: file reads, quick
questions, routine edits, and complex reasoning all burn the same limited budget. Claude
throttles after roughly 40–50 messages in a 5-hour rolling window.

**The result: your session hits the wall in under 2 hours, and you wait.**

| Prompt | Quota burned | Actually needs Claude? |
|---|---|---|
| *"What does this function return?"* | ✗ Yes | No |
| *"List files matching \*.test.ts"* | ✗ Yes | No |
| *"Write a test for this function"* | ✗ Yes | Probably not |
| *"Re-architect this auth system"* | ✓ Yes | **Yes** |

Simple questions and complex reasoning cost the same quota. That's the inefficiency
Chuzom fixes.

---

## The Solution

**Chuzom** routes each prompt to the cheapest capable model *before* spending Claude quota.

```
Your IDE (Claude Code, Cursor, etc)
    ↓
[Chuzom Smart Router]  ← analyzes complexity & task type
    ↓
├─ Simple tasks?   → Ollama (local, free) 🌳
├─ Moderate tasks? → Codex CLI / Gemini CLI (free via your subscriptions)
└─ Complex tasks?  → Claude (only when it truly needs it) 🔥
    ↓
Result + streaming progress + quota savings banner
    🎯 chuzom → gemini-2.5-flash · code/moderate · 342ms · saved Claude quota!
```

<p align="center">
  <sub><em>🌊 Simple prompts take the fast rapids (local, free). Deep reasoning takes the slow, deep water (Claude). The router reads the current and picks the channel — you never think about it.</em></sub>
</p>

| Tool | Cost | Best for |
|---|---|---|
| **Ollama** (local) | Free | Simple questions, syntax lookups, file ops |
| **Codex CLI** | Free (via GitHub Copilot) | Code generation, refactors, test writing |
| **Gemini CLI** | Free (via Google account) | Moderate reasoning, explanations, summaries |
| **Claude** | Your subscription quota | Complex reasoning, long context, architecture |

---

## Why People Install This

AI coding tools send too many prompts to premium models by default. That means you waste
paid tokens on simple questions, burn quota faster than necessary, and stop working when
one provider is rate-limited.

Chuzom sits between your coding tool and your model providers. It classifies each prompt,
tries the cheapest capable model first, and falls back automatically when needed. **You
keep the same workflow. The router changes the model choice underneath.**

<table align="center">
<tr>
<td align="center" width="25%">
  <h3>⏱️ 3–5× Longer Sessions</h3>
  <p>Route most prompts to free models — hit quota limits far less often</p>
</td>
<td align="center" width="25%">
  <h3>✅ Quality Preserved</h3>
  <p>Premium models only when the task truly needs it — measured, not assumed</p>
</td>
<td align="center" width="25%">
  <h3>🛡️ Quota Protected</h3>
  <p>Auto-downgrade near limits. No more rate-limit walls</p>
</td>
<td align="center" width="25%">
  <h3>⚙️ Zero Config</h3>
  <p>Works out of the box with a Claude Pro/Max subscription</p>
</td>
</tr>
</table>

<p align="center">
  <img src="assets/flow-animated.webp" alt="Animated: a marmot resting on a lily pad in calm, gently rippling water at golden hour — the unhurried flow of a session that never hits the wall" width="92%"/>
</p>

<p align="center">
  <em>Fewer walls. Longer flow. The same workflow — just calmer underneath.</em>
</p>

---

## 📊 Measured Results (audited)

Chuzom v1.0.0 is the first release where the savings claim is **backed by a real,
reproducible control-group benchmark**, not just estimated. The router went through a
formal correctness reset that ended in an independently **audited verdict**.

**Control-group benchmark** — Chuzom vs. always-GPT-4o over a moderate+hard prompt
corpus, under *strict full metering* (every escalation is a real, priced API call — no
free-tier confound):

| Metric | Result |
|---|---|
| **Net cash savings** | **+$0.027** per run (Chuzom ≈ $0.0036 vs GPT-4o ≈ $0.030) |
| **Quality delta** | **−0.21** on a 0–5 judge scale — **within** the 0.5 non-inferiority margin |
| **Exhaustions** (dropped answers) | **0** |
| **Robustness** | held across **4 independent runs** (−0.18 / −0.21 / −0.21 / +0.00) |
| **Verdict** | **RELEASE QUALIFIED** — two consecutive clean audit passes on a frozen commit |

All 20 release gates pass, including a positive-net-savings gate, a
quality-non-inferiority gate, and a mutation-testing bar. Full evidence:
[Release Gates](Docs/correctness-reset/03_RELEASE_GATES.md) ·
[Benchmark log](Docs/correctness-reset/10_CODEX_QUOTA_BENCHMARK.md) ·
[Audit runbook](Docs/correctness-reset/11_AUDIT_RUNBOOK.md).

> **On the "3×" / "80%" headline numbers.** Those are *illustrative estimates* for a
> heavy-Opus workload — real savings depend entirely on your prompt mix. The **measured**
> figures above are the honest, reproducible ones. Reproduce them yourself with
> `python -m chuzom benchmark`.

<details>
<summary><strong>Illustrative estimate — one week for a heavy Claude Code user</strong> (directional, not measured)</summary>

A typical heavy user sends ~800–1,200 prompts/week. Routing most of them to free models:

| Metric | Without Chuzom | With Chuzom |
|---|---|---|
| Prompts to Claude (quota) | ~1,000 / week | ~240 / week |
| Prompts to Ollama (local, free) | 0 | ~520 / week |
| Prompts to Codex / Gemini CLI (prepaid) | 0 | ~240 / week |
| Claude quota consumed | 100% | ~24% |
| Sessions before "usage limit" | 1–2 / day | 6–8 / day |

These are directional — not statistically significant. The audited control-group numbers
above are the ones to trust.
</details>

---

## Get Started (60 seconds)

**1. Install**

```bash
pip install chuzom-router          # or: uv pip install chuzom-router
```

**2. Wire into your IDE**

```bash
chuzom install --host claude-code  # or: cursor, codex, gemini-cli, windsurf, all
```

**3. Add API keys (optional)**

```bash
# Bring your own keys — stored in ~/.chuzom/.env, never committed
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=...
export PERPLEXITY_API_KEY=pplx-...        # for research routing

# Or: use Claude Code Pro/Max or Codex subscriptions (zero keys needed)
export CHUZOM_CLAUDE_SUBSCRIPTION=true
```

**4. Verify & watch savings**

```bash
chuzom doctor            # checks hooks, Ollama, API keys, provider health
chuzom summary --watch   # live savings dashboard
```

Done. Your IDE now routes intelligently. (Windows PATH tips → [Troubleshooting](Docs/troubleshooting.md#windows-specific-setup).)

---

## How It Works

Every prompt flows through a smart classification pipeline:

```
┌──────────────────────────────┐
│ Your prompt in Claude Code    │
└──────────────┬───────────────┘
               ↓
        1️⃣  CLASSIFY            task type · complexity · sensitivity (PII/secrets)
               ↓
        2️⃣  BUILD CHAIN         ranked candidates — cheapest capable first, with fallbacks
               ↓
        3️⃣  DISPATCH + STREAM   first qualified model · live progress · auto-failover · local log
               ↓
        ✅  Result              🎯 chuzom → <model> · <task> · <latency> · saved $<amount>
```

**Zero data leaves your machine.** Chuzom is an MCP server on your workstation — no
proxy, no cloud, no telemetry. Every routing decision is logged locally.

---

## Supported IDEs

Chuzom works with every major AI-assisted IDE via two modes — **push** (a hook routes
automatically, e.g. Claude Code) and **pull** (the model chooses to call Chuzom tools,
e.g. Cursor/Copilot/Windsurf).

| Tool | Routing | Status |
|---|---|---|
| 🔵 Claude Code / Desktop | **Push** (automatic) | ✅ Production |
| 🟠 Codex CLI | **Push** (plugin) | ✅ Production |
| 🟣 Cursor | **Pull** + rule nudge | ✅ Production |
| 🔴 Gemini CLI | **Pull** (tool call) | ✅ Production |
| 🟤 GitHub Copilot (VS Code) | **Pull** (agent mode) | ✅ Beta |
| 🌊 Windsurf / Cascade | **Pull** (agent mode) | ✅ Beta |
| 🌙 Kimi Code | **Pull** (MCP tools) | ✅ Beta |

> Claude Code gives the most consistent routing (a hook fires every turn). Per-IDE setup,
> the push/pull deep dive, and the 11-door MCP tool surface → **[IDE Setup guide](Docs/ide-setup.md)**.

---

## Routing at a Glance

Chuzom tries each tier in order, falling back on failure or timeout:

| Complexity | Profile | Tier 1 (cheapest) | → | Fallback |
|---|---|---|---|---|
| **simple** | BUDGET | Ollama (local/free) | Codex · Gemini Flash | Haiku |
| **moderate** | BALANCED | Ollama (local/free) | Codex · GPT-4o | Sonnet |
| **complex** | PREMIUM | Codex CLI | OpenAI o3 · Claude Opus | Gemini 2.5 Pro |
| **deep_reasoning** 🧠 | REASONING | Ollama qwen3 | DeepSeek-R1 · o3 | Claude Opus + thinking |

Six one-line **routing policies** (`balanced`, `local-first`, `cost`, `quality`,
`quota-exhaustion`, `dynamic`) tune the cost/quality tradeoff. Chuzom also routes
**subagent spawns**, auto-detects **13+ local inference servers**
([details](Docs/local-inference.md)), and never hardcodes model names (Ollama dynamic
discovery).

> Full chains, subagent routing, the REASONING profile, model pinning, and every policy →
> **[Routing guide](Docs/routing.md)**.

---

## Agentic Router

> Status: real but maturing. Design + phased plan in [`Docs/agentic-router.md`](Docs/agentic-router.md).

Beyond routing a single completion, Chuzom can delegate a whole task to the cheapest
**capable, tool-using agent** and verify the result — via the `llm_act` MCP tool
(Milestone-Gated Escalating Execution):

1. **Plan** — decompose the task into milestones, each with an *objective, executable*
   acceptance check (`cmd` / `lint` / `diff` / `canary`). "Done" means the check passed,
   not the model's self-report.
2. **Delegate** — each milestone runs on the cheapest capable tier (local agent → Codex → premium).
3. **Escalate without rework** — a failed check escalates to a stronger tier, carrying
   already-passed milestones forward as frozen context.
4. **Flow, not stall** — escalation is bounded; irreversible steps run in an isolated git
   worktree, merged only after they verify.

```bash
llm_act(task="…")   # → JSON: outcome, per-milestone status, events, savings
```

Prompts with a code-mutating verb **and** an objective-verification demand (e.g. *"fix
the failing test and make it pass"*) route to delegation automatically. Disable with
`CHUZOM_DELEGATE=off`; any `llm_*` call clears the route, so you're never trapped.

---

## 🧠 Companion Skill: `/council`

Where Chuzom picks the *cheapest* capable model, `/council` is the *quality-maximizing*
counterpart: it convenes a small committee of the strongest available models for
genuinely hard problems and runs `propose → critique → synthesize` across model families
(Claude Opus, Codex/GPT-5.x, optional Gemini). The output includes a fused answer **and an
explicit dissent section** — minority views are preserved, not averaged away.

```bash
/council Should we migrate this service to event sourcing?
/council --tier=max Evaluate this architecture decision thoroughly.
```

Use it when the cost of being wrong is higher than the cost of asking twice. It never
auto-fires — the human always confirms before any multi-model run.

---

## Session Summary Dashboard

At the end of every session, Chuzom prints a full-color **Tokyo Night** dashboard: the
routing method breakdown, per-window savings, live Claude quota bars, per-model costs, a
14-day activity chart, and a per-tier routing summary (Free local / Free subscription /
Paid API).

```
  🧮 Routing Summary — this session
  Tier              | Calls | Tokens |   Actual |  Baseline |    Saved
  ──────────────────────────────────────────────────────────────────
  Free local        |    16 |    240 | $ 0.0000 | $  0.0013 | $ 0.0013
  Free subscription |     5 |   3516 | $ 0.0000 | $  0.0190 | $ 0.0190
  Paid API          |    27 |  13421 | $ 0.1735 | $  0.0725 | $ 0.0000
  ──────────────────────────────────────────────────────────────────
  TOTAL             |    48 |  17177 | $ 0.1735 | $  0.0928 | $ 0.0203
```

Long model calls also **stream live progress** (Codex JSONL events, Gemini lines,
heartbeats) — no silent 80-second waits. Full dashboard walkthrough →
**[Session Dashboard guide](Docs/session-dashboard.md)**.

---

## Configuration

Everything works out of the box. Common one-liners:

```bash
export CHUZOM_CLAUDE_SUBSCRIPTION=true          # enable Claude quota tracking
export CHUZOM_ROUTING_POLICY=local-first        # or: cost, quality, balanced, dynamic
export CHUZOM_OLLAMA_MODEL=qwen2.5-coder:7b     # pin a local model
export CHUZOM_ENFORCE=smart                     # default — see the enforcement ladder
```

All settings can live in `~/.chuzom/.env` (loaded automatically). The full env-var
matrix, enforcement modes (`smart` / `soft` / `hard` / `strict` / `advise` / `off`), and
advanced options (direct execution, session context, subscription mode) →
**[Configuration reference](Docs/configuration.md)**.

---

## More docs

| Guide | What's in it |
|---|---|
| [IDE Setup](Docs/ide-setup.md) | Per-IDE setup, push vs pull, the 11-door MCP tool surface |
| [Routing](Docs/routing.md) | Chains, subagent routing, REASONING profile, policies, model pinning |
| [Local Inference](Docs/local-inference.md) | 13+ auto-detected local LLM servers + port overrides |
| [Configuration](Docs/configuration.md) | Full env matrix, enforcement modes, advanced config, CLI |
| [Session Dashboard](Docs/session-dashboard.md) | Dashboard panels + live streaming progress |
| [OKF Integration](Docs/okf.md) | Self-building local knowledge bundle that compounds savings |
| [Agentic Router](Docs/agentic-router.md) | Milestone-Gated Escalating Execution design |
| [Troubleshooting](Docs/troubleshooting.md) | Command-not-found, hooks, Ollama, Windows setup |
| [Correctness Reset](Docs/correctness-reset/03_RELEASE_GATES.md) | The audit: gates, benchmark, verdict |

---

## Benchmarks

The **audited** control-group figures are in [Measured Results](#-measured-results-audited)
(the numbers to trust). Chuzom also ships a built-in smoke corpus of 77 prompts
(`easy` × 20, `hard` × 16, `moderate` × 17, plus objective-heavy `moderate2` × 12 and
`hard2` × 12) for quick local checks — the audited release benchmark uses the
moderate + hard baseline (33 prompts); the extension sharpens the estimate. A
production-scale corpus (thousands of prompts) has not been published yet.

```bash
python -m chuzom benchmark   # run your own
```

---

## FAQ

**Do I need to bring API keys?** No — not if you use Claude Code Pro/Max or Codex
subscriptions. Optional for other providers.

**What data does Chuzom collect?** None. Everything stays on your machine — no telemetry,
no cloud calls.

**How much can I actually save?** It depends entirely on your prompt mix. The honest,
reproducible number is the audited **+$0.027/run net at −0.21 quality** control-group
result above. Heavy-Opus workloads see the largest gains; light users see less.

**Which models does it support?** 20+ providers: OpenAI, Anthropic, Google, Ollama, 13+
local servers, and more.

**Does Chuzom work without Ollama?** Yes — Ollama is optional. Without it, prompts route
to Codex CLI, Gemini CLI, or API providers. Install Ollama for free local routing.

**Can I use it on Windows?** Yes. `pip install chuzom-router` then `chuzom install`. PATH
and PowerShell tips → [Troubleshooting](Docs/troubleshooting.md#windows-specific-setup).

**How do I stop it blocking a tool call?** Relax with `CHUZOM_ENFORCE=soft` (log only) or
`off`. For a single turn, prefix your prompt with `claude:`. See
[enforcement modes](Docs/configuration.md#enforcement-modes).

More Q&A in the [Troubleshooting guide](Docs/troubleshooting.md).

---

## Contributing

Full test suite runs on every push (Python 3.10+). Contributions welcome!

- 🐛 [Report bugs](https://github.com/Chuzom/Chuzom/issues)
- 💡 [Start discussions](https://github.com/Chuzom/Chuzom/discussions)
- 🔧 [Read `CONTRIBUTING.md`](./CONTRIBUTING.md)

Chuzom also ships as a [Codex plugin](.codex-plugin/plugin.json) (category *Developer
Tools*).

---

## License

MIT © [The Chuzom Contributors](https://github.com/Chuzom/Chuzom/graphs/contributors)
