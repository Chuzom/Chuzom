# Chuzom — Route eligible prompts to local/free models before spending Claude quota.

[![PyPI version](https://img.shields.io/pypi/v/chuzom-router?style=flat-square&color=4F46E5)](https://pypi.org/project/chuzom-router/)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/chuzom-router?period=total&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=ORANGE&left_text=downloads)](https://pepy.tech/projects/chuzom-router)
[![Python](https://img.shields.io/pypi/pyversions/chuzom-router?style=flat-square&color=3572A5)](https://pypi.org/project/chuzom-router/)
[![CI](https://img.shields.io/github/actions/workflow/status/Chuzom/Chuzom/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Chuzom/Chuzom/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-10B981?style=flat-square)](https://github.com/Chuzom/Chuzom/blob/main/LICENSE)

<p align="center">
  <img src="https://raw.githubusercontent.com/Chuzom/Chuzom/main/assets/hero-confluence.webp" alt="A marmot at a river confluence — rushing rapids on one side, deep calm water on the other — where fast and slow streams meet and each finds its path" width="92%"/>
</p>

<p align="center">
  <em>A <strong>Chuzom</strong> is a <strong>confluence</strong> — the place where rivers meet.<br/>
  Fast rapids and deep water, converging, each stream finding its natural path.</em><br/>
  <strong>⭐ Star the repo if Chuzom saves your quota.</strong>
</p>

**Chuzom** is a smart LLM router for AI coding tools. On Claude Code a hook sees every prompt,
sends the eligible ones to a free local or subscription model, and spends Claude quota only on
work that truly needs it — so a day's quota stretches across a week of sessions.
Context-dependent prompts (which a stateless local model can't answer) and provider outages fall
back to Claude by design. Drop-in, zero workflow change, with **cost and quality independently
benchmarked** — see [Measured results](#-measured-results-audited). That benchmark covers routing
economics and answer quality; it is not a security or privacy audit.

```bash
pip install chuzom-router && chuzom install --host claude-code
```

## Contents

**Why** — [The Problem](#the-problem) · [The Solution](#the-solution) · [Why People Install This](#why-people-install-this) · [📊 Measured Results (audited)](#-measured-results-audited)<br>
**Use** — [Get Started](#get-started-60-seconds) · [How It Works](#how-it-works) · [Supported IDEs](#supported-ides) · [Routing at a Glance](#routing-at-a-glance) · [Configuration](#configuration)<br>
**More** — [Agentic Router](#agentic-router) · [`/council`](#-companion-skill-council) · [Session Dashboard](#session-summary-dashboard) · [More docs](#more-docs) · [FAQ](#faq) · [Contributing](#contributing) · [License](#license)

---

## The Problem

You're on **Claude Pro ($20/mo), Max ($100/mo), or Max ($200/mo)** — a flat subscription, not
pay-per-token. But Claude Code routes **every request** through your quota: file reads, quick
questions, routine edits, and complex reasoning all burn the same limited budget. Claude throttles
after roughly 40–50 messages in a 5-hour rolling window — **your session hits the wall in under
two hours, and you wait.**

| Prompt | Quota burned | Actually needs Claude? |
|---|---|---|
| *"What does this function return?"* | ✗ Yes | No |
| *"List files matching \*.test.ts"* | ✗ Yes | No |
| *"Write a test for this function"* | ✗ Yes | Probably not |
| *"Re-architect this auth system"* | ✓ Yes | **Yes** |

Simple questions and complex reasoning cost the same quota. That's the inefficiency Chuzom fixes.

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

| Tool | Cost | Best for |
|---|---|---|
| **Ollama** (local) | Free | Simple questions, syntax lookups, file ops |
| **Codex CLI** | Free (via GitHub Copilot) | Code generation, refactors, test writing |
| **Gemini CLI** | Free (via Google account) | Moderate reasoning, explanations, summaries |
| **Claude** | Your subscription quota | Complex reasoning, long context, architecture |

---

## Why People Install This

AI coding tools send too many prompts to premium models by default — you waste paid tokens on
simple questions, burn quota faster than necessary, and stop working when one provider is
rate-limited. Chuzom sits between your coding tool and your model providers: it classifies each
prompt, tries the cheapest capable model first, and falls back automatically when needed. **You
keep the same workflow. The router changes the model choice underneath.**

| ⏱️ Fewer quota walls | ✅ Quality preserved | 🛡️ Quota protected | ⚙️ Quick setup |
|---|---|---|---|
| Most prompts go to free/local models — you hit limits far less often | Premium models only when the task needs it — measured, not assumed | Auto-downgrade near limits, so no hard rate-limit wall | `pip install` + `chuzom install`; add Ollama to unlock free routing |

<p align="center">
  <img src="https://raw.githubusercontent.com/Chuzom/Chuzom/main/assets/flow-animated.webp" alt="Animated: a marmot resting on a lily pad in calm, gently rippling water at golden hour — the unhurried flow of a session that never hits the wall" width="92%"/>
</p>

<p align="center"><em>Fewer walls. Longer flow. The same workflow — just calmer underneath.</em></p>

---

## 📊 Measured Results (audited)

Since v1.0.0, the savings claim has been backed by a **real, reproducible control-group
benchmark** — not an estimate — after a formal correctness reset that ended in an independently
**audited verdict**. Chuzom vs. always-GPT-4o over a moderate+hard corpus, under *strict full
metering* (every escalation is a real, priced API call — no free-tier confound):

| Metric | Result |
|---|---|
| **Net cash savings** | **+$0.027** per run (Chuzom ≈ $0.0036 vs GPT-4o ≈ $0.030) |
| **Quality delta** | **−0.21** on a 0–5 judge scale — **within** the 0.5 non-inferiority margin |
| **Exhaustions** (dropped answers) | **0** |
| **Robustness** | held across **4 independent runs** (−0.18 / −0.21 / −0.21 / +0.00) |
| **Verdict** | Two consecutive clean passes on a frozen commit, **at that commit** — see the note below |

All 20 release gates pass, including a positive-net-savings gate, a quality-non-inferiority gate,
and a mutation-testing bar. Full evidence: [Release Gates][gates] · [Benchmark log][bench] ·
[Audit runbook][runbook].

> **⚠️ The qualification does not hold at HEAD.** It was granted at a specific frozen commit, and
> the project's own restart-at-zero rule means it lapses the moment the tree moves. A later audit
> found open P0 defects — including savings figures overstated ~3× by a stale price table, and a
> savings surface structurally incapable of displaying a loss, which Gate 7 certified anyway. The
> audit badge has been removed until a re-qualification passes at the shipping SHA.
> Remediation is tracked in `.chuzom/zero-tolerance-audit/`.

> **On the "3×" / "80%" headline numbers.** Those are *illustrative estimates* for a heavy-Opus
> workload — real savings depend entirely on your prompt mix. The **measured** figures above are
> the honest, reproducible ones. Reproduce them yourself with `chuzom benchmark`.

### Estimated savings by workload

> **These are illustrative estimates — directional, not measured.** They apply the *audited* ratio (Chuzom
> spent **~12% of the always-premium cost at non-inferior quality** → ≈88% avoided) to typical
> volumes. On a **Claude Pro/Max subscription the value is quota runway**, **not cash** — the money
> column applies only if you'd otherwise pay per-token at GPT-4o rates.

| Workload | Typical volume | Claude quota preserved | Session runway | Est. cash (pay-per-token only) |
|---|---|---|---|---|
| **Individual developer** — mixed Q&A, edits, small refactors | ~100 prompts/day | ~60–70% | ~2–3× more sessions/day | ~$20–35 / month |
| **Agentic workloads** — `llm_act` tool loops, many execute/verify sub-steps | high (each task fans out) | ~80–90% | ~4–5× | ~$50–150 / month |
| **Heavy Claude Code user** — ~1,000 prompts/week | ~1,000 / week | ~76% | ~4× (1–2 → 6–8 / day) | ~$16–34 / week (~$70–150 / mo) |

**Why agentic saves the most:** a single `llm_act` task fans out into many execute/verify
sub-steps, and Chuzom routes **subagent spawns** too — most of that never touches Claude quota.

#### Heavy-user week, expanded

| Metric | Without Chuzom | With Chuzom |
|---|---|---|
| Prompts to Claude (quota) | ~1,000 / week | ~240 / week |
| Prompts to Ollama (local, free) | 0 | ~520 / week |
| Prompts to Codex / Gemini CLI (prepaid) | 0 | ~240 / week |
| Claude quota consumed | 100% | ~24% |
| Sessions before "usage limit" | 1–2 / day | 6–8 / day |

Directional estimate — not statistically significant. Reproduce the audited figures with `chuzom benchmark`.

---

## Get Started (60 seconds)

**1. Install and wire into your IDE**

```bash
pip install chuzom-router            # or: uv pip install chuzom-router
chuzom install --host claude-code    # or: cursor, codex, gemini-cli, windsurf, all
```

**2. Add API keys (optional)**

```bash
# Bring your own keys — stored in ~/.chuzom/.env, never committed
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=...
export PERPLEXITY_API_KEY=pplx-...        # for research routing

# Or: use Claude Code Pro/Max or Codex subscriptions (zero keys needed)
export CHUZOM_CLAUDE_SUBSCRIPTION=true
```

**3. Verify & watch savings**

```bash
chuzom doctor            # checks hooks, Ollama, API keys, provider health
chuzom summary --watch   # live savings dashboard
```

Done. Your IDE now routes intelligently. (Windows PATH tips → [Troubleshooting][trouble-win].)

---

## How It Works

Every prompt flows through the same pipeline — **classify** (task type · complexity · sensitivity),
**build a chain** (ranked candidates, cheapest capable first), then **dispatch and stream** with
automatic failover and a local decision log:

<p align="center">
  <img src="https://raw.githubusercontent.com/Chuzom/Chuzom/main/assets/architecture-hero.svg"
       alt="Chuzom routing architecture: MCP clients (Claude Code, Cursor, Codex CLI, Gemini CLI) send a prompt to the Chuzom router, which classifies task type, complexity and sensitivity, builds a cheapest-capable-first chain, then dispatches to free local Ollama, budget cloud, or premium tiers, falling back down the chain on failure"
       width="100%"/>
</p>

**Local-first, no Chuzom telemetry.** Chuzom runs on your workstation and phones home to no Chuzom
servers — every routing decision is logged locally. Note: if you configure cloud providers (e.g.
`OPENAI_API_KEY`, `GEMINI_API_KEY`), the classifier and the routing chain send prompt text to
*those* providers' APIs when they are selected. With only a local provider (Ollama) configured,
prompt text stays on your machine.

---

## Supported IDEs

Chuzom works with every major AI-assisted IDE via two modes — **push** (a hook routes
automatically, e.g. Claude Code) and **pull** (the model chooses to call Chuzom tools).

| Tool | Routing | Status |
|---|---|---|
| 🔵 Claude Code / Desktop | **Push** (automatic) | ✅ Production |
| 🟠 Codex CLI | **Push** (plugin) | ✅ Production |
| 🟣 Cursor | **Pull** + rule nudge | ✅ Production |
| 🔴 Gemini CLI | **Pull** (tool call) | ✅ Production |
| 🟤 GitHub Copilot (VS Code) | **Pull** (agent mode) | ✅ Beta |
| 🌊 Windsurf / Cascade | **Pull** (agent mode) | ✅ Beta |
| 🌙 Kimi Code | **Pull** (MCP tools) | ✅ Beta |

> Claude Code gives the most consistent routing (a hook fires every turn). Per-IDE setup, the
> push/pull deep dive, and the 11-door MCP tool surface → **[IDE Setup guide][ide]**.

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
`quota-exhaustion`, `dynamic`) tune the cost/quality tradeoff. Chuzom also routes **subagent
spawns**, auto-detects **13 local inference servers** ([details][local]), and never hardcodes
model names (Ollama dynamic discovery).

> Full chains, subagent routing, the REASONING profile, model pinning, and every policy →
> **[Routing guide][routing]**.

---

## Agentic Router

> Status: real but maturing. Design + phased plan in [`Docs/agentic-router.md`][agentic].

Beyond routing a single completion, Chuzom can delegate a whole task to the cheapest **capable,
tool-using agent** and verify the result — via the `llm_act` MCP tool (Milestone-Gated Escalating
Execution):

1. **Plan** — decompose into milestones, each with an *objective, executable* acceptance check
   (`cmd` / `lint` / `diff` / `canary`). "Done" means the check passed, not a self-report.
2. **Delegate** — each milestone runs on the cheapest capable tier (local agent → Codex → premium).
3. **Escalate without rework** — a failed check escalates to a stronger tier, carrying
   already-passed milestones forward as frozen context.
4. **Flow, not stall** — escalation is bounded.

> **⚠️ Partially true — read the specifics.** This section used to claim that irreversible steps
> run in an isolated git worktree, merged only after they verify. Two thirds of that is now real and
> one third is still not, so here is the exact state:
>
> - **Verification is real.** A milestone's acceptance check reads the repository (`git diff`, plus
>   newly created files) rather than the executing agent's own report of what it did. A `return True`
>   stub submitted as an acceptance check is rejected instead of accepted.
> - **Irreversible steps fail closed.** An irreversible milestone that was not isolated is *surfaced*
>   rather than frozen. It cannot silently complete on a bare acceptance pass.
> - **Isolation itself is still not wired.** Nothing creates a worktree, so irreversible milestones
>   are refused rather than sandboxed. The merge-only-if-verified half exists and is connected; the
>   run-it-somewhere-safe half is not.
>
> Continue to treat `llm_act` / `llm_delegate` as unsafe against untrusted repository contents — see
> [SECURITY.md](SECURITY.md). Tracked as WP-09 in `.chuzom/zero-tolerance-audit/`.

```bash
llm_act(task="…")   # → JSON: outcome, per-milestone status, events, savings
```

Prompts with a code-mutating verb **and** an objective-verification demand (e.g. *"fix the failing
test and make it pass"*) route to delegation automatically. Disable with `CHUZOM_DELEGATE=off`;
any `llm_*` call clears the route, so you're never trapped.

---

## 🧠 Companion Skill: `/council`

Where Chuzom picks the *cheapest* capable model, `/council` is the *quality-maximizing*
counterpart: it convenes a committee of the strongest available models for genuinely hard problems
and runs `propose → critique → synthesize` across model families (Claude Opus, Codex/GPT-5.x,
optional Gemini). The output includes a fused answer **and an explicit dissent section** — minority
views are preserved, not averaged away.

```bash
/council Should we migrate this service to event sourcing?
/council --tier=max Evaluate this architecture decision thoroughly.
```

Use it when the cost of being wrong is higher than the cost of asking twice. It never auto-fires —
the human always confirms before any multi-model run.

---

## Session Summary Dashboard

At the end of every session, Chuzom prints a full-color **Tokyo Night** dashboard: routing method
breakdown, per-window savings, live Claude quota bars, per-model costs, a 14-day activity chart,
and a per-tier routing summary (Free local / Free subscription / Paid API).

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

Long model calls also **stream live progress** (Codex JSONL events, Gemini lines, heartbeats) — no
silent 80-second waits. Full walkthrough → **[Session Dashboard guide][dash]**.

---

## Configuration

Everything works out of the box. Common one-liners:

```bash
export CHUZOM_CLAUDE_SUBSCRIPTION=true          # enable Claude quota tracking
export CHUZOM_ROUTING_POLICY=local-first        # or: cost, quality, balanced, dynamic
export CHUZOM_OLLAMA_MODEL=qwen2.5-coder:7b     # pin a local model
export CHUZOM_ENFORCE=smart                     # default — see the enforcement ladder
```

All settings can live in `~/.chuzom/.env` (loaded automatically). The full env-var matrix,
enforcement modes (`smart` / `soft` / `hard` / `strict` / `advise` / `off`), and advanced options →
**[Configuration reference][config]**.

---

## More docs

| Guide | What's in it |
|---|---|
| [IDE Setup][ide] | Per-IDE setup, push vs pull, the 11-door MCP tool surface |
| [Routing][routing] | Chains, subagent routing, REASONING profile, policies, model pinning |
| [Local Inference][local] | 13 auto-detected local LLM servers + port overrides |
| [Configuration][config] | Full env matrix, enforcement modes, advanced config, CLI |
| [Session Dashboard][dash] | Dashboard panels + live streaming progress |
| [OKF Integration][okf] | Self-building local knowledge bundle that compounds savings |
| [Agentic Router][agentic] | Milestone-Gated Escalating Execution design |
| [Troubleshooting][trouble] | Command-not-found, hooks, Ollama, Windows setup |
| [Correctness Reset][gates] | The audit: gates, benchmark, verdict |

---

## Benchmarks

The **audited** control-group figures are in [Measured Results](#-measured-results-audited) — the
numbers to trust. Chuzom also ships a smoke corpus of 77 prompts (`easy` × 20, `hard` × 16,
`moderate` × 17, plus objective-heavy `moderate2` × 12 and `hard2` × 12) for quick local checks;
the audited release benchmark uses the moderate + hard baseline (33 prompts). A production-scale
corpus has not been published yet.

```bash
chuzom benchmark   # run your own
```

---

## FAQ

**Do I need to bring API keys?** No — not if you use Claude Code Pro/Max or Codex subscriptions.
Optional for other providers.

**What data does Chuzom collect?** None, and Chuzom itself makes no cloud calls — no telemetry, no
servers of ours. Your prompts are a separate question: **whether they stay on your machine depends
on which providers you configure.** With only Ollama, they do. Configure `OPENAI_API_KEY`,
`GEMINI_API_KEY` or any other cloud provider and prompt text is sent to *that* provider whenever the
router selects it — which is the normal case, since routing to cheap cloud models is a core feature.
See [Local-first](#local-first-no-chuzom-telemetry).

**How much can I actually save?** It depends entirely on your prompt mix. The honest, reproducible
number is the audited **+$0.027/run net at −0.21 quality** control-group result above.

**Which models does it support?** 18 providers — OpenAI, Anthropic, Google, Ollama, DeepSeek,
Groq, Mistral, xAI and more — plus 13 auto-detected local servers.

**Does Chuzom work without Ollama?** Yes — Ollama is optional. Without it, prompts route to Codex
CLI, Gemini CLI, or API providers. Install Ollama for free local routing.

**Can I use it on Windows?** Yes. `pip install chuzom-router` then `chuzom install`. PATH and
PowerShell tips → [Troubleshooting][trouble-win].

**How do I stop it blocking a tool call?** Relax with `CHUZOM_ENFORCE=soft` (log only) or `off`.
For a single turn, prefix your prompt with `claude:`. See [enforcement modes][config-enforce].

More Q&A in the [Troubleshooting guide][trouble].

---

## Contributing

Full test suite runs on every push (Python 3.11–3.14). Contributions welcome!

- 🐛 [Report bugs](https://github.com/Chuzom/Chuzom/issues)
- 💡 [Start discussions](https://github.com/Chuzom/Chuzom/discussions)
- 🔧 [Read `CONTRIBUTING.md`][contributing]

Chuzom also ships as a [Codex plugin][codex-plugin] (category *Developer Tools*).

---

## License

MIT © [LLM Router Contributors](https://github.com/Chuzom/Chuzom/graphs/contributors)

<!-- Absolute URLs so links resolve on PyPI, not just GitHub. -->
[gates]:          https://github.com/Chuzom/Chuzom/blob/main/Docs/correctness-reset/03_RELEASE_GATES.md
[bench]:          https://github.com/Chuzom/Chuzom/blob/main/Docs/correctness-reset/10_CODEX_QUOTA_BENCHMARK.md
[runbook]:        https://github.com/Chuzom/Chuzom/blob/main/Docs/correctness-reset/11_AUDIT_RUNBOOK.md
[ide]:            https://github.com/Chuzom/Chuzom/blob/main/Docs/ide-setup.md
[routing]:        https://github.com/Chuzom/Chuzom/blob/main/Docs/routing.md
[local]:          https://github.com/Chuzom/Chuzom/blob/main/Docs/local-inference.md
[config]:         https://github.com/Chuzom/Chuzom/blob/main/Docs/configuration.md
[config-enforce]: https://github.com/Chuzom/Chuzom/blob/main/Docs/configuration.md#enforcement-modes
[dash]:           https://github.com/Chuzom/Chuzom/blob/main/Docs/session-dashboard.md
[okf]:            https://github.com/Chuzom/Chuzom/blob/main/Docs/okf.md
[agentic]:        https://github.com/Chuzom/Chuzom/blob/main/Docs/agentic-router.md
[trouble]:        https://github.com/Chuzom/Chuzom/blob/main/Docs/troubleshooting.md
[trouble-win]:    https://github.com/Chuzom/Chuzom/blob/main/Docs/troubleshooting.md#windows-specific-setup
[contributing]:   https://github.com/Chuzom/Chuzom/blob/main/CONTRIBUTING.md
[codex-plugin]:   https://github.com/Chuzom/Chuzom/blob/main/.codex-plugin/plugin.json
