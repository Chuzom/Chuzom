<p align="center">
  <img src="https://raw.githubusercontent.com/ypollak2/chuzom/main/assets/hero-light.svg" alt="Chuzom — meeting of rivers, routing intelligence" width="760">
</p>

<h1 align="center">Chuzom</h1>

<p align="center">
  <em>Meeting of rivers, routing intelligence.</em>
</p>

<p align="center">
  <strong>Local-first LLM router for developer workstations.</strong><br/>
  Route every prompt to the cheapest capable model. Log every decision to a local lineage store. Stays local; no proxy. Drop-in for Claude Code, Cursor, Codex CLI, Gemini CLI, and more.
</p>

<p align="center">
  <sub><strong>Maturity:</strong> developer-tool layer is the production path today (alpha per <a href="https://github.com/ypollak2/chuzom/blob/main/pyproject.toml">pyproject.toml</a>). The enterprise control plane — RBAC, tamper-evident audit chain, per-user / per-team budgets, OpenTelemetry export — is scaffolded but not yet wired into the routing path (<a href="https://github.com/ypollak2/chuzom/blob/main/Docs/audit/FINDINGS.md">INV-010</a>). See <a href="https://github.com/ypollak2/chuzom/blob/main/Docs/audit/ROADMAP.md">ROADMAP</a> for sequencing.</sub>
</p>

<p align="center">
  <a href="https://pypi.org/project/chuzom-router/"><img src="https://img.shields.io/badge/pypi-chuzom--router-4F46E5?style=flat-square" alt="PyPI"></a>
  <a href="https://github.com/ypollak2/chuzom/actions/workflows/ci.yml"><img src="https://github.com/ypollak2/chuzom/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/ypollak2/chuzom"><img src="https://img.shields.io/badge/python-3.10+-3572A5?style=flat-square" alt="Python"></a>
  <a href="https://github.com/ypollak2/chuzom/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-10B981?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/SOC%202-mappable-8B5CF6?style=flat-square" alt="SOC 2">
  <img src="https://img.shields.io/badge/GDPR-mappable-8B5CF6?style=flat-square" alt="GDPR">
  <img src="https://img.shields.io/badge/OTEL-traces%20%2B%20metrics%20%2B%20logs-F59E0B?style=flat-square" alt="OTel">
</p>

<p align="center"><strong>Install in 30 seconds</strong></p>

```bash
pip install chuzom-router
chuzom install --host claude-code   # or cursor / codex-cli / gemini-cli
```

<p align="center">
  <sub>Works with Claude Code · Cursor · Codex CLI · Gemini CLI · Claude Desktop · Factory IDE · Trae · 7 more</sub><br/>
  <sub><strong>Local-first.</strong> No hosted proxy. No account required. Optional org control plane.</sub>
</p>

<!--
DEMO GIF SLOT — highest-leverage asset for adoption. Once recorded, replace this
comment with:
  <p align="center">
    <img src="https://raw.githubusercontent.com/ypollak2/chuzom/main/docs/assets/demo.gif"
         alt="chuzom routing a prompt and showing live savings" width="760">
  </p>
The GIF should show, in ~10s: a prompt in Claude Code → the live
`🎯 chuzom → <model> · saved $` banner → `chuzom summary --watch` updating.
Record it with the script in docs/assets/RECORD_DEMO.md.
-->

---

<details>
<summary><b>📑 Table of Contents</b></summary>

- [Why orgs deploy Chuzom](#why-orgs-deploy-chuzom)
- [What you get](#what-you-get)
- [What makes Chuzom different](#what-makes-chuzom-different)
- [Quick start](#quick-start)
- [Live dashboard](#live-dashboard)
- [Routing examples](#routing-examples)
- [Works with](#works-with)
- [Agent framework adapters](#agent-framework-adapters)
- [Enterprise features](#enterprise-features)
- [How routing works](#how-routing-works)
- [OpenTelemetry observability](#opentelemetry-observability)
- [Org-grade policies with secure secrets](#org-grade-policies-with-secure-secrets)
- [Scenario-based test reports](#scenario-based-test-reports)
- [Model registry](#model-registry)
- [CLI](#cli)
- [Configuration](#configuration)
- [Tests + quality](#tests--quality)
- [Documentation](#documentation)
- [License](#license)

</details>

---

## Why orgs deploy Chuzom

Every engineering org has the same four problems with LLM access:

1. **Cost** — most prompts don't need GPT-4o or Sonnet. They go there anyway because the developer's tool picks one model and sticks with it.
2. **Audit** — when compliance asks *"what model answered which question for whom and when?"* the answer is *"check the OpenAI dashboard"*.
3. **Safety** — developers paste API keys, customer data, and source code into prompts that hit third-party APIs.
4. **Governance** — there's no per-team cap, no model allow/deny, no way to enforce policy across heterogeneous tools.

Chuzom sits between developer tools and LLM providers as an MCP server. Every prompt gets classified, routed to the cheapest capable model, logged with full attribution, and (in org mode) checked against the user's quota + the team's policy.

The developer's workflow doesn't change. The model choice, the audit trail, and the spend control happen underneath.

---

## What you get

- **Cost reduction** of 35–80% on routine work via tier-based routing — reproducible head-to-head vs always-cheap / always-premium on a fixed corpus with cost-vs-quality scoring (`python -m bench`, see [bench/](https://github.com/ypollak2/chuzom/tree/main/bench))
- **Tamper-evident audit log** with SHA-256 hash chain — every routing decision, quota breach, policy change captured
- **Distributed-safe per-identity budgets** — atomic check-then-charge (single-instance SQLite + multi-instance Postgres backends share one `BudgetBackend` Protocol); pre-emptive refusal so no money is spent on calls the cap would reject
- **Forecast / predictive budget tier** — refuses reservations BEFORE the hard cap is hit when the rolling burn rate projects exhaustion inside the horizon (opt-in via `CHUZOM_BUDGET_FORECAST_MODE`)
- **Agent-aware routing policy** — per-session `AgentRoutingPolicy` biases candidate ordering by preferred provider, classification-keyed model preferences, and a per-turn cost cap distinct from the session budget. Inherits through the parent-session chain so a sub-agent picks up its spawner's constraints unless it overrides them
- **PII / secret detection** that forces local-only routing when prompts contain credentials
- **OpenTelemetry export** — spans + metrics + logs to Honeycomb, Datadog, Grafana, Jaeger
- **Multi-CLI host support** for Claude Code, Cursor, Codex CLI, Gemini CLI, Claude Desktop, and 9 more
- **Agent framework adapters** — Agno concrete; Hermes + LangGraph + CrewAI + OpenAI Agents SDK + Claude Agent SDK + Pydantic AI shaped for v0.3.0
- **Routing inversion detection** — flags when complex prompts go cheap (underserved) or simple prompts go premium (overspend)
- **Rich live dashboard** with status banner, tier distribution, latency histogram, agent rollups, watch mode
- **Per-route visibility with budget context** — every routed reply begins with `🎯 chuzom → <model> · <task>/<complexity> · <latency>`. Subscription routes append `wk left N% · 5h left M%`; API routes append `30d on <provider>: $X.XX`; when the cumulative counterfactual is meaningful you also see `saved Xpp wk / Ypp 5h` (rolled into a full breakdown via the new `llm_quota_saved` tool)
- **Self-debug-safe** — chuzom recognises prompts that target chuzom itself (debug, route, hook, install, etc.) and bypasses enforcement so you never get locked out of the tools needed to repair chuzom
- **~3667 tests** including scenario reports that render as readable stories

---

## What makes Chuzom different

Chuzom isn't a hosted gateway — it's a **local-first router that lives on the
developer's workstation**, so the honest comparison is against the tools a team
actually reaches for. Legend: ✅ yes · 🟡 partial / opt-in · — no.

### Developer experience — Chuzom's wedge

| Capability | LiteLLM Proxy | Portkey | OpenRouter | **Chuzom** |
|---|:---:|:---:|:---:|:---:|
| Runs locally, no proxy hop / no hosted account | 🟡 | — | — | ✅ |
| Cost-aware multi-provider routing | ✅ | ✅ | 🟡 | ✅ |
| Signal / decision **YAML DSL** for routing | — | — | — | ✅ |
| **Subscription-aware** routing (Claude Pro/Max, Codex sub) | — | — | — | ✅ |
| Live **in-editor savings banner** (`🎯 chuzom → model · saved $`) | — | — | — | ✅ |
| PII / secret detection → forces local-only routing | 🟡 | ✅ | — | ✅ |
| Semantic / result caching | ✅ | ✅ | — | ✅ |
| Scenario reports with narrative routing traces | — | — | — | ✅ |
| Multi-CLI host support (14 hosts) | — | — | — | ✅ |

### Enterprise control plane — where Chuzom is now competitive

| Capability | LiteLLM Proxy | Portkey | OpenRouter | **Chuzom** |
|---|:---:|:---:|:---:|:---:|
| Per-user / per-team budgets + spend tracking | ✅ | ✅ | 🟡 | ✅ |
| Per-identity **quota enforcement** on the routing path | ✅ | ✅ | 🟡 | ✅ |
| RBAC (roles × permissions) | ✅ | ✅ | — | 🟡 ¹ |
| Audit log | ✅ | ✅ | — | 🟡 ¹ |
| **Tamper-evident hash-chained** audit | — | — | — | ✅ |
| **SSO / OIDC / SCIM** | ✅ | ✅ | 🟡 | ✅ ² |
| Admin API / control plane | ✅ | ✅ | ✅ | 🟡 ³ |
| Container / Helm / systemd deployment | ✅ | ✅ | ✅ ⁴ | ✅ |
| Self-hostable / air-gapped (Ollama-only) | ✅ | 🟡 | — | ✅ |
| Open-source core | ✅ | 🟡 | — | ✅ (MIT) |

¹ Implemented and tested; **enforced by default under `CHUZOM_PROFILE=enterprise`**
   (developer profile stays permissive).
² OIDC JWT validation (JWKS / RS256) + just-in-time provisioning + SCIM 2.0
   user provisioning. SAML via an OIDC bridge.
³ FastAPI control plane (user / token / policy / audit endpoints); a few
   endpoints are still being hardened.
⁴ OpenRouter is hosted — "deployment" is N/A; marked ✅ for "available as a service."

> Every ✅ in the top block is a genuine win none of the three hosted gateways
> offer. The bottom block is where Chuzom has closed most of the gap — SSO,
> quotas, audit, and a deployable stack all shipped.

---

## Quick start

### 1 · Install

```bash
pip install chuzom-router
chuzom install --host claude-code
```

Or wire it into another host:

```bash
chuzom install --host cursor       # writes ~/.cursor/mcp.json
chuzom install --host gemini-cli   # writes ~/.gemini/mcp_servers.json
chuzom install --host codex        # writes Codex CLI plugin config
chuzom install --host all          # all of the above
```

### 2 · Add providers (optional)

```bash
export OPENAI_API_KEY="sk-..."             # GPT-4o, o3
export GEMINI_API_KEY="AIza..."            # Gemini Flash / Pro
export ANTHROPIC_API_KEY="sk-ant-..."      # Haiku / Sonnet / Opus
export OLLAMA_BASE_URL="http://localhost:11434"  # Local models (free)
```

Works with **zero API keys** when you run Claude Code Pro/Max (uses the subscription) or Codex CLI subscription. Add an API key per provider you want unlocked.

### 3 · Verify

```bash
chuzom doctor
```

You'll see hooks installed, MCP server reachable, providers detected, and any setup issues called out with a fix command.

### 4 · Watch the dashboard live

```bash
chuzom summary --watch
```

### 5 · See the Chuzom banner on every `claude` launch (optional)

Claude Code's `SessionStart` hooks cannot surface output to your terminal — they only inject context into the model. To get a visible startup banner, wrap `claude` in your shell rc so the banner prints **before** Claude Code takes over the TUI:

```zsh
# ~/.zshrc
claude() {
    command chuzom welcome --compact 2>/dev/null
    command claude "$@"
}
```

Swap `--compact` for the full painterly Chuzom-confluence banner (78 lines of 24-bit ANSI art) by dropping the flag. `chuzom welcome` prints to stdout, so it works in any shell that supports function wrappers — `zsh`, `bash` (with `function claude() { ... }`), `fish`, etc.

---

## Live dashboard

```
╭────────────────── ◆ Session Summary ──────────────────╮
│  🟢 CHUZOM · session observability dashboard          │
│                                                        │
│  Session savings $0.0774 (39% vs always-premium)       │
│  Spent $0.1193 · baseline $0.1967                      │
│  25 routing decisions · 2098 ms avg                    │
╰────────────────────────────────────────────────────────╯
╭──────────── ◆ Tier distribution ───────────────────────╮
│  local    │ 10 │  $0.00  │ ████████████████████  │
│  cheap    │  6 │ 0.330¢  │ ████████████          │
│  mid      │  5 │ $0.1110 │ ██████████            │
│  premium  │  3 │  $0.00  │ ██████                │
╰────────────────────────────────────────────────────────╯
╭──── ◆ Routing health (inversions) ─────────────────────╮
│  ↑ 0 UP-inversions    ↓ 0 DOWN-inversions               │
│  Inversion rate: 0.0% (target < 5%)                     │
╰────────────────────────────────────────────────────────╯
╭──── ◆ Safety ──────────────────────────────────────────╮
│  ✓ 2 PII / secret leak(s) caught — forced local        │
╰────────────────────────────────────────────────────────╯
╭──── ◆ Latency distribution ────────────────────────────╮
│  p50: 1100 ms    p95: 4500 ms    p99: 4800 ms          │
│   600 ms │ █████████ │ 7                                │
│  1200 ms │ ████████  │ 6                                │
│  1800 ms │ █████     │ 4                                │
╰────────────────────────────────────────────────────────╯
```

Status glyph: 🟢 healthy / 🟡 watch / 🔴 alert based on inversion rate + failure rate. Run with `--watch` for live updates every 5 seconds.

---

## Routing examples

| Prompt | Signal that fires | Tier chosen | Cost |
|---|---|---|---|
| `"What is a foreign key?"` | (none fires) → default chain | Ollama (local) | $0 |
| `"Refactor this function for early returns"` | `code_keywords` | Ollama → Codex | $0 |
| `"Latest OpenAI o3 benchmarks?"` | `research_keywords` | Perplexity | $0.002 |
| `"Here's my OPENAI_API_KEY=sk-proj-..."` | **`pii_secret` (priority 10)** | **Forced Ollama (local)** | $0 |
| `"Refactor auth.py"` + `code-reviewer` agent profile | `code_keywords` ×1.5 boost | Sonnet | $0.018 |
| `"How does our internal X work"` from a developer who burned 95% of monthly quota | `quota_check` → soft warn | GPT-4o-mini | $0.0006 |

The signal layer is YAML-configurable; the routing decisions are auditable; every call goes through the same pipeline regardless of which host the developer was using.

---

## Works with

| Host | Integration | Live routing | Verified by |
|---|---|:---:|---|
| **Claude Code** | MCP server + hooks + rules + plugin | ✅ | 10 MCP handshake + 5 integration |
| **Claude Desktop** | MCP server via `claude_desktop_config.json` | ✅ | MCP handshake |
| **Cursor** | MCP server + rules | ✅ | 12 adapter + 10 handshake + 4 coexistence |
| **Codex CLI** | Plugin marketplace + rules | ✅ | plugin manifest + handshake |
| **Codex / VS Code** | Rules file | rules-driven | rules validation |
| **Gemini CLI** | MCP server + rules (v1.3+) | ✅ | 4 adapter + 10 handshake + 2 coexistence |
| **Gemini** (other) | Rules file | rules-driven | rules validation |
| **GitHub Copilot** | Rules file | rules-driven | rules validation |
| **Copilot CLI** | Rules file | rules-driven | rules validation |
| **Factory IDE** | Plugin manifest | ✅ | plugin validation |
| **Trae IDE** | Rules + root `.rules` | rules-driven | rules validation |
| **PI** | Rules file | rules-driven | rules validation |

Install paths:

```bash
chuzom install --host claude-code
chuzom install --host claude-desktop
chuzom install --host cursor
chuzom install --host codex
chuzom install --host gemini-cli
chuzom install --host all
```

Full integration matrix in [`Docs/HOST_INTEGRATION_REPORT.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/HOST_INTEGRATION_REPORT.md) (118 structural tests, all green).

---

## Agent framework adapters

| Framework | Status | What you get |
|---|:---:|---|
| **[Agno](https://github.com/agno-agi/agno)** (primary) | **concrete** | `RouteredModel` + `RouteredTeam` — drop-in for `agno.models.base.Model`; full budget envelope; lineage tagged `framework="agno"` |
| **Hermes** | skeleton (v0.3.0) | Protocol-shape pinned; concrete impl deferred until tool-use format is confirmed |
| **LangGraph** | stub (v0.3.0+) | Adapter shape ready; Runnable wrapping next |
| **CrewAI** | stub (v0.3.0+) | LiteLLM-compatible completion shim path |
| **OpenAI Agents SDK** | stub (v0.3.0+) | AsyncOpenAI client wrap path |
| **Claude Agent SDK** | stub (v0.3.0+) | anthropic client wrap path |
| **Pydantic AI** | stub (v0.3.0+) | Model-protocol implementation path |

Chuzom doesn't replace your agent runtime. It sits inside it, picks the right model per agent step, enforces the session's budget, and tags every routing decision with the framework + agent_id for cost rollups.

```python
from agno.agent import Agent
from chuzom.frameworks.agno import RouteredModel

agent = Agent(
    model=RouteredModel(task_type="code"),
    instructions="You are a code reviewer.",
)
agent.print_response("Review src/auth.py for security issues")
```

That's the whole integration — every model call inside the agent goes through Chuzom's signal layer, lineage gets tagged with `framework="agno"` and the session's `agent_id`, and the agent's budget envelope refuses calls that would breach the cap.

---

## Enterprise features

Six controls that an organization can adopt incrementally — each module is independent.

### 🔐 Identity + API tokens

- Three-level hierarchy: Org → Team → User
- API tokens with `tsr_` prefix (grep-able if leaked) and **256 bits of entropy**
- **SHA-256 hashed at rest** — stolen DB = stolen hashes, not credentials
- Individual + bulk revocation; auto-revoke on user deactivation
- Optional TTL; `external_id` column for OIDC/SAML federation
- Persisted at `~/.chuzom/identity.db`

### 👥 Role-based access control

Four roles × twelve permissions:

| Role | Routes | Views own | Views team | Views all | Manages users | Manages policy |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Admin** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Manager** | ✅ | ✅ | ✅ | — | — | — |
| **Employee** | ✅ | ✅ | — | — | — | — |
| **Service account** | ✅ | — | — | — | — | — |

`require_permission(identity, Permission.MANAGE_USERS)` raises `PermissionDenied` with structured context. Fail-closed by default.

### 📜 Immutable audit log

Every event carries a SHA-256 hash of `(prev_hash + canonical_payload)`. Tampering with any row breaks the chain — `verify_chain()` reports the first divergent row.

```python
from chuzom.enterprise import AuditLog
log = AuditLog()
log.append(AuditEvent(
    type="routing.decision",
    actor_id=identity.user.id,
    actor_email=identity.user.email,
    org_id=identity.user.org_id,
    resource=f"lineage:{record.id}",
    action="created",
    detail={"cost_usd": 0.018, "model": "openai/gpt-4o"},
))

# Daily: verify nothing was modified out-of-band
log.verify_chain()

# Ship to your SIEM
log.export_cef(limit=10000)   # ArcSight CEF (Splunk/Datadog/Sentinel)
log.export_json(limit=10000)  # generic JSON
log.export_csv(limit=10000)   # spreadsheet
```

### 🛡️ PII / secret redaction

```python
from chuzom.enterprise import redact_prompt, RedactionPolicy

result = redact_prompt(
    "Email alice@acme.com or use sk-proj-abc... no really",
)
# result.text       → "Email [REDACTED:email] or use [REDACTED:openai_key]..."
# result.counts     → {"email": 1, "openai_key": 1}
# result.any_redactions → True
```

12 default patterns: OpenAI / Anthropic / Gemini / GitHub / AWS / Slack API keys, JWTs, private-key blocks, emails, US phones, US SSNs, Luhn-validated credit cards. Custom patterns plug in via `RedactionPolicy.with_patterns()`.

Applied **before** the lineage write so the durable record never contains the raw secret.

### 💵 Per-identity budgets with atomic check-then-charge

`BudgetBackend` is a duck-typed Protocol with three production-grade implementations:

| Backend | Use case | Coordination |
|---|---|---|
| `BudgetEnvelopeManager` (in-process) | Tests, ephemeral runs | `asyncio.Lock` |
| `SqliteBudgetBackend` (default) | Single-instance deployments | SQLite `BEGIN IMMEDIATE` (cross-process file lock) |
| `PostgresBudgetBackend` | Multi-instance Phase 3b | `UPDATE … WHERE consumed + pending + cost <= cap` (row-level lock) |

```python
from chuzom.budget_backend import get_budget_backend
from chuzom.budget_key import BudgetKey, SCOPE_TURN

backend = get_budget_backend()                     # CHUZOM_BUDGET_BACKEND env decides
key = BudgetKey(tenant_id="t1", org_id="o1", user_id="alice",
                agent_id=None, scope=SCOPE_TURN)

backend.register(key, cap_usd=5.00, soft_cap_usd=4.00)

# Pre-emptive refusal — no money spent on calls the cap would reject.
if not await backend.try_reserve(key, cost_usd=0.20):
    return {"error": "quota_exceeded"}

# On provider success:
await backend.commit(key, cost_usd=actual_cost)
```

**G-002 acceptance pinned by tests** — 100 concurrent reservations against a $5 cap → exactly 50 succeed (per-process for SQLite; across 4 processes for Postgres via Testcontainers).

### ⏱️ Forecast tier (T2-L2) — refuse before the cap

Opt-in via `CHUZOM_BUDGET_FORECAST_MODE` (off / warn / strict). When enabled, every `try_reserve` consults the rolling burn rate from committed spend events; if the projected time-to-breach falls inside `CHUZOM_BUDGET_FORECAST_HORIZON_SECONDS` (default 300), strict mode raises `ForecastedBudgetBreach` before the call ever reaches a provider:

```
ForecastedBudgetBreach: Forecasted budget breach in 90s
at burn rate $0.0033/s (horizon 300s).
```

Off-mode and warn-mode preserve the existing call path; strict mode wraps the runaway-agent guards already in T3-M3 (`max_iterations`, `max_recursion_depth`).

### 📊 Observability — OpenTelemetry-native

One env var and every routing decision becomes a span + metric + log in your observability backend:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
export OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=KEY
pip install "chuzom-router[tracing]"
```

That's it. Chuzom auto-emits per routing decision:

- **Spans**: `chuzom.route` with full attribution (host, task_type, complexity, model_chosen, tier, cost, latency, agent_id, session_id, framework)
- **Span events**: `inversion_detected`, `pii_detected`
- **Metrics**: `chuzom.routing.decisions{tier,task_type,host}`, `chuzom.routing.inversions{direction}`, `chuzom.safety.pii_catches`, histograms for cost and latency
- **Logs**: WARN on inversions, INFO on PII catches, ERROR on budget breaches

Compatible with **Honeycomb, Grafana Cloud, Datadog, Jaeger, AWS X-Ray, GCP Cloud Trace** — anything that speaks OTLP.

Full deployment guide: [`Docs/ENTERPRISE_DEPLOYMENT.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/ENTERPRISE_DEPLOYMENT.md). Threat model: [`Docs/THREAT_MODEL.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/THREAT_MODEL.md). Security posture: [`SECURITY.md`](https://github.com/ypollak2/chuzom/blob/main/SECURITY.md).

---

## How routing works

```
                    ┌──────────────────────┐
   user prompt ─►   │  Host CLI (MCP call) │  ─► mcp__chuzom__llm_*
                    └────────────┬─────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │  Signal layer                        │
              │  • pii_secret          (priority 10) │
              │  • code_keywords       (priority 50) │
              │  • research_keywords   (priority 40) │
              │  • embedding_match     (v0.3.0)      │
              │  • reask               (v0.3.0)      │
              └──────────────────┬──────────────────┘
                                 │  bag of SignalScore
              ┌──────────────────▼──────────────────┐
              │  Decision engine                     │
              │  AND / OR / NOT / SINGLE over        │
              │  signals → chain alias               │
              └──────────────────┬──────────────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │  Selector + circuit breaker          │
              │  Free-first chain walk; failover     │
              └──────────────────┬──────────────────┘
                                 │
                 ┌───────────────┼────────────────┐
                 ▼               ▼                ▼
              Ollama       Codex (sub)       OpenAI / Anthropic / Gemini
                 │               │                │
                 └───────────────┼────────────────┘
                                 │
            ┌────────────────────▼──────────────────────┐
            │  Lineage + audit + OTLP (parallel writes) │
            │  • lineage.db        — every decision      │
            │  • audit.db          — hash-chained        │
            │  • OTLP              — span + metric + log │
            └─────────────────────────────────────────┘
```

Layers are independent: signals are pure functions, the decision engine is a pure function, the selector wraps providers + circuit breaker. Each layer's contract is pinned by tests so refactors stay safe.

**Self-reference bypass.** When a prompt mentions chuzom itself alongside debug- or development-context words (e.g., *"chuzom is stuck"*, *"debug the chuzom hook"*, *"chuzom route indicator"*), the auto-route hook short-circuits before any routing or enforcement fires — no banner, no `pending_route_*.json` written, no blocked tools. This prevents the circular failure mode where users can't repair chuzom because chuzom is blocking the tools they need. The bypass is logged as `SELF_REFERENCE_BYPASS` in `~/.chuzom/auto-route-debug.log` so the audit trail stays complete.

Architecture deep-dive: [`Docs/ARCHITECTURE.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/ARCHITECTURE.md).

---

## OpenTelemetry observability

Chuzom was designed with observability as a first-class concern. The OTLP exporter is auto-wired into `LineageStore.record()` so when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, **every routing decision** becomes a span — no application code changes required.

What you can build on top:

- **Per-team cost dashboards** filtered on `chuzom.framework="agno"` or `chuzom.agent_id="code-reviewer"`
- **Inversion rate alerts** when up-inversions exceed 5% over rolling 1000 decisions
- **PII catch heatmaps** by hour of day to identify training opportunities
- **Latency p95 vs cost scatter plots** to identify expensive-slow models
- **Per-user spend leaderboards** for finance reporting

---

## Org-grade policies with secure secrets

Routing policy ships as YAML. **Secrets never appear inline** — five built-in reference schemes:

```yaml
# config/policies/prod.yaml
name: prod-routing
providers:
  openai:
    api_key: "${vault:secret/llm-providers#openai_key}"
  anthropic:
    api_key: "${aws-sm:arn:aws:secretsmanager:us-east-1:1234:secret:anthropic}"
  gemini:
    api_key: "${gcp-sm:projects/X/secrets/gemini/versions/latest}"
  custom:
    api_key: "${env:CUSTOM_API_KEY}"
    legacy_key: "${file:/var/secrets/legacy.txt}"
routing:
  enforce: smart
  default_chain: code_chain
tier_budgets:
  cheap: 100.00
  mid: 50.00
  premium: 10.00
```

**Plaintext-secret detection** at YAML load time — `OrgPolicy.load()` rejects files containing OpenAI / Anthropic / Gemini / GitHub / AWS / Slack / JWT / private-key-block patterns with a clear remediation. Secrets do not live in version-controlled YAML, ever.

```python
from chuzom.org_policy import OrgPolicy
policy = OrgPolicy.load("config/policies/prod.yaml")  # plaintext check runs

# At request time, secrets resolve via your configured backend
api_key = policy.resolve("providers.openai.api_key")  # → hits Vault now
```

Custom schemes plug in via `SecretResolver.register_scheme()`.

---

## Scenario-based test reports

Chuzom ships a scenario harness that produces a markdown *story* per routing journey — every actor that touched the request (host, hook, classifier, signal, decision engine, selector, model, lineage, session, budget) renders as a numbered bullet.

```
## cli-02 · Claude Code: secret in prompt forces local-only routing

1. 🧑 [user] submitted prompt with embedded key (chars=100)
2. 🪝 [hook] auto-route saw code-shaped prompt (task_type=code)
3. 📡 [signal] pii_secret FIRED (score=1, evidence='matched pattern: openai_key')
4. 📡 [signal] code_keywords did not fire (score=0)
5. ⚖️ [decision] force_local_on_pii chose action='local_only_chain'
6. 🎯 [selector] chain resolved (chain=[ollama/qwen3.5:latest])
7. 🤖 [model] ollama/qwen3.5:latest succeeded (cost=$0, 1800ms)
8. 📜 [lineage] record persisted (tier=local, inversion=none)
       › secret matched in prompt; routed local
9. 🏁 [outcome] PII detected → forced local routing
```

24 scenarios across 4 CLIs + 7 frameworks + 8 failure modes. Generated automatically at `Docs/SCENARIO_REPORT.md` when the scenario suite runs.

```bash
pytest tests/scenarios/
# Report: Docs/SCENARIO_REPORT.md (24 scenarios, 24 passed)
```

---

## Model registry

Chuzom ships a **model registry** sourced from [artificialanalysis.ai/leaderboards/models](https://artificialanalysis.ai/leaderboards/models) with quality scores, prices, latency p50, capabilities, and context windows for every routable model:

```python
from chuzom.model_registry import ModelRegistry

reg = ModelRegistry.load_default()
# Find cheaper models with equivalent quality
cheaper = reg.cheaper_with_equal_quality(
    reg.get("openai/gpt-4o"), quality_tolerance=0.05,
)
# Pareto frontier — only the models worth picking from
front = reg.pareto_frontier()
```

Ships with 13 models pre-loaded; refresh from artificialanalysis.ai via `scripts/refresh-model-registry.py`. Custom registry via `config/models.yaml`.

---

## CLI

```bash
# Setup + verify
chuzom install              # install hooks + rules + MCP config
chuzom install --host all   # install for every supported host
chuzom doctor               # health check + remediation hints
chuzom welcome              # painterly Chuzom-confluence banner
chuzom welcome --compact    # one-line variant for ~/.zshrc wrappers

# Session intelligence
chuzom summary              # last 24h dashboard
chuzom summary --watch      # live-updating every 5s
chuzom summary --markdown   # share-able output

# Inspection
chuzom last [--count N]     # recent routing decisions
chuzom replay               # full session transcript
chuzom savings-report       # token + cost breakdown
chuzom retrospect           # IAF-style session debrief

# MCP tools (called by your host CLI / agent runtime, not by the user directly)
llm_quota_saved             # cumulative subscription-% counterfactual (weekly + 5h)
llm_check_usage             # cached Claude subscription snapshot
llm_refresh_claude_usage    # OAuth refresh (macOS Keychain)

# Development workflow
chuzom dev-refresh          # reinstall pkg + sync hooks + restart MCP servers
chuzom dev-refresh --dry-run        # show the plan, don't execute
chuzom dev-refresh --skip-mcp-kill  # keep current sessions alive

# Governance
chuzom budget set <provider> <amount>
chuzom set-enforce <mode>   # smart | soft | hard | off
chuzom policy --check       # validate signal/decision config

# Team / org
chuzom team report [period]
chuzom team push [period]   # ship to Slack/Discord/webhook
```

---

## Configuration

### Runtime toggles (env vars)

| Variable | Values | Effect |
|---|---|---|
| `CHUZOM_ENFORCE` | `smart` (default) · `soft` · `hard` · `off` | Routing enforcement mode. `smart` hard-blocks Q&A and soft-allows code edits; `soft` logs but never blocks; `hard` blocks until an `llm_*` tool is called; `off` disables enforcement entirely. Same modes the `chuzom set-enforce` CLI writes. |
| `CHUZOM_ROUTE_BANNER` | `on` (default) · `off` / `0` / `false` / `no` | Suppress the stderr `🎯 routed → …` line emitted on every DIRECT-success route. The user-visible reply-prefix indicator stays unaffected. |
| `CHUZOM_ZERO_CLAUDE` | `1` / `true` / `on` | Strict zero-Claude routing — every prompt must execute via an external route or be blocked. Useful for cost-sensitive deployments. |
| `CHUZOM_AGENT_POLICY_MODE` | `off` · `warn` (default) · `strict` | T3-XL1 agent-aware routing policy gate. `strict` refuses non-preferred candidates with `PermissionDenied`; `warn` logs and proceeds; `off` short-circuits the policy layer entirely. |
| `CHUZOM_BUDGET_BACKEND` | `sqlite` (default) · `memory` · `postgres` | Selects the budget backend implementation. `sqlite` (single-instance persistent) is the default; `postgres` opts in to the multi-instance Phase 3b backend (requires the `postgres` extra + `CHUZOM_BUDGET_POSTGRES_DSN`); invalid values fail-open to `sqlite`. |
| `CHUZOM_BUDGET_POSTGRES_DSN` | libpq DSN | Postgres connection string when `CHUZOM_BUDGET_BACKEND=postgres`. Missing DSN → fail-open to SQLite. |
| `CHUZOM_BUDGET_FORECAST_MODE` | `off` (default) · `warn` · `strict` | T2-L2 forecast tier gate. `strict` raises `ForecastedBudgetBreach` when burn-rate trajectory projects exhaustion inside the horizon; `warn` logs and proceeds. |
| `CHUZOM_BUDGET_FORECAST_WINDOW_SECONDS` | seconds (default `60`) | Rolling window for the burn-rate calculation. |
| `CHUZOM_BUDGET_FORECAST_HORIZON_SECONDS` | seconds (default `300`) | Projected time-to-breach below this threshold triggers a forecast refusal under strict mode. |
| `CHUZOM_WEEKLY_QUOTA_USD_OPUS_EQUIV` | USD (default `50`) | Calibration constant for the quota-saved metric: dollars of Opus-equivalent spend that equal 100% of one week of Claude subscription quota. Override per plan tier. |
| `CHUZOM_DEV_SRC` | absolute path | Source directory used by `chuzom dev-refresh` when `--source` isn't passed. |
| `CHUZOM_CLAUDE_SUBSCRIPTION` | `true` / `1` / `yes` | Forces subscription-mode banner + OAuth pressure cascade even when not auto-detected. |
| `CHUZOM_OIDC_ISSUER` | IdP issuer URL | Enables OIDC federation. When set, a `CHUZOM_TOKEN` that is not a chuzom `tsr_` token is validated as an IdP-issued JWT (RS256 / JWKS) and the user is just-in-time provisioned. Requires the `sso` extra (`pip install 'chuzom-router[sso]'`). |
| `CHUZOM_OIDC_AUDIENCE` | string | Required `aud` claim value when OIDC is enabled. |
| `CHUZOM_OIDC_JWKS_URI` | URL | JWKS endpoint. Defaults to `{issuer}/.well-known/jwks.json`. |
| `CHUZOM_OIDC_EMAIL_CLAIM` / `CHUZOM_OIDC_GROUPS_CLAIM` | claim name | Claims carrying email (default `email`) and groups (default `groups`). |
| `CHUZOM_OIDC_ROLE_MAP` | `group=role,…` | Maps IdP groups → chuzom roles, e.g. `chuzom-admins=admin,chuzom-users=employee`. Highest-privilege match wins; unmatched → `employee`. |
| `CHUZOM_OIDC_DEFAULT_ORG` / `CHUZOM_OIDC_DEFAULT_TEAM` | name | Org/team that JIT-provisioned federated users land in (default `default`). |
| `CHUZOM_SCIM_ENABLED` | `on` / `1` / `true` | Enables the SCIM 2.0 provisioning endpoint (`/scim/v2/Users`) for IdP-driven create / update / deprovision. Requires `CHUZOM_SCIM_TOKEN`. |
| `CHUZOM_SCIM_TOKEN` | bearer secret | The bearer token the IdP presents to the SCIM endpoint (compared in constant time). |
| `CHUZOM_*_PATH` | absolute path | Override the location of any state DB (`CHUZOM_LINEAGE_PATH`, `CHUZOM_AUDIT_PATH`, `CHUZOM_BUDGETS_DB_PATH`, etc.). |

### State DBs

State lives in `~/.chuzom/` (override per-DB via `CHUZOM_*_PATH` env vars):

| File | Purpose |
|---|---|
| `lineage.db` | Every routing decision |
| `sessions.db` | Agent session lifecycle (includes T3-XL1 `routing_policy_json` column) |
| `identity.db` | Users + teams + tokens |
| `audit.db` | Immutable hash-chained audit |
| `quotas.db` | Per-identity consumption + policies |
| `budgets.db` | T2-L1 `BudgetBackend` envelopes + T2-L2 spend events (SQLite backend) |
| `cache.db` | Semantic response cache (stub) |
| `usage.json` | Live Claude subscription snapshot |

Per-project config lives in `config/` (gitignored where appropriate):

| File | Purpose |
|---|---|
| `config/signals.yaml` | Signal + decision DSL |
| `config/agents.yaml` | Agent profiles |
| `config/models.yaml` | Model registry snapshot |
| `config/policies/*.yaml` | Org-grade policies with secret indirections |

Provider keys via env vars or `~/.chuzom/config.yaml` (mode-600 user-readable, for security-policy deployments where `.env` is blocked).

---

## Tests + quality

| Tier | Coverage |
|---|---|
| Unit (lineage / signals / agents / decisions / bench) | foundation |
| Integration (12 hosts) | host structural |
| QA — 5 pillars + Agno deep | functional / non-functional / perf / integrity / usability |
| QA — MCP handshake (live subprocess) | protocol layer end-to-end |
| QA — network failure simulation | circuit breaker state machine |
| QA — multi-host coexistence | Chuzom + llm-router parallel |
| QA — framework contracts (6 stubs) | per-framework × 14 contract dims |
| QA — session summary | dashboard data + render |
| QA — plugin packaging | marketplace + MCP-config plugins |
| QA — observability (OTLP) | spans + metrics + logs |
| QA — model registry | YAML + Pareto + filtering |
| QA — org policy (secure YAML) | plaintext rejection + resolution |
| QA — **enterprise (identity + RBAC + audit + redaction + quotas)** | per-module + parametrized |
| **T1** — tenant id + RBAC + per-provider permissions | per-identity scopes |
| **T2** — budget cluster (key + envelope + tiers + atomic backend + forecast + Postgres) | G-002 acceptance, multi-instance |
| **T3** — agent safety (cancel shield, deadlines, runaway guards, idempotency, cost cap, wall clock, routing policy) | G-008 acceptance |
| **T4** — privacy + governance (redaction routing, classification allow-list) | per-classification provider gates |
| Scenario reports | CLI + framework + cross-cutting |
| Auto-route classifier regression | inherited + fix-verb expansion |

Full suite runs in CI on every push — [![CI](https://github.com/ypollak2/chuzom/actions/workflows/ci.yml/badge.svg)](https://github.com/ypollak2/chuzom/actions/workflows/ci.yml) — across Python 3.11 + 3.13, excluding the in-progress `tests/lineage/` and one known timing-sensitive perf flake. ~2.5 minute wall time.

Run subsets:

```bash
pytest tests/qa/             # all QA pillars (~100 ms each)
pytest tests/scenarios/      # narrative reports (writes Docs/SCENARIO_REPORT.md)
pytest tests/integration/    # host structural
```

---

## Documentation

| Doc | What it covers |
|---|---|
| [`SECURITY.md`](https://github.com/ypollak2/chuzom/blob/main/SECURITY.md) | Responsible disclosure, posture, SOC 2 / GDPR / HIPAA / PCI mapping |
| [`Docs/ARCHITECTURE.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/ARCHITECTURE.md) | Three-ring architecture, data flows, package layout |
| [`Docs/ENTERPRISE_DEPLOYMENT.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/ENTERPRISE_DEPLOYMENT.md) | Deployment topology, IdP integration, audit shipping, runbooks |
| [`Docs/THREAT_MODEL.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/THREAT_MODEL.md) | STRIDE per asset, attack scenario walkthroughs, residual risks |
| [`Docs/QA_TEST_STRATEGY.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/QA_TEST_STRATEGY.md) | Five pillars, quality gates with explicit thresholds, risk register |
| [`Docs/QA_TEST_REPORT.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/QA_TEST_REPORT.md) | Per-pillar + per-host scorecards (auto-generated) |
| [`Docs/SCENARIO_REPORT.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/SCENARIO_REPORT.md) | Per-scenario narrative routing journeys |
| [`Docs/HOST_INTEGRATION_REPORT.md`](https://github.com/ypollak2/chuzom/blob/main/Docs/HOST_INTEGRATION_REPORT.md) | 14-host integration matrix + verification status |
| [`CHANGELOG.md`](https://github.com/ypollak2/chuzom/blob/main/CHANGELOG.md) | Release notes |

---

## Status

**v0.2.0** — beyond the dogfood ring, into the audit-driven hardening phase. Full test suite green in CI on every push (see the CI badge above). SECURITY.md, threat model, and enterprise deployment guide all shipped. Plugin packaging verified for Claude Code, Cursor, Codex CLI, Gemini CLI.

### Recently shipped

- **T3-XL1** — agent-aware routing policy (`AgentRoutingPolicy`), per-session candidate reordering, per-turn cost cap distinct from session budget, parent-chain inheritance via `SessionStore.effective_policy`. Gated by `CHUZOM_AGENT_POLICY_MODE` = off / warn / strict.
- **T2-L1** — distributed-safe budget backend; `BudgetBackend` Protocol + `SqliteBudgetBackend` with `BEGIN IMMEDIATE` atomicity. **G-002** TST-003 acceptance: 100 concurrent reservations → exactly N succeed.
- **T2-L2** — forecast / predictive budget tier. Burn-rate driven `ForecastedBudgetBreach` under strict mode. Spend events persisted alongside envelope state in the same transaction.
- **T2-XL1** — multi-instance coordination via `PostgresBudgetBackend`. Single-`UPDATE` atomic check-then-charge SQL. Multi-process G-002 acceptance pinned with Testcontainers + `multiprocessing.spawn`.
- **T4-M2** — per-classification provider allow-list (e.g. CODE must stay on-prem). Earlier in roadmap; landed.
- **T-CODEX-3** — real Codex / Gemini-CLI stderr surfaces in the router's `chain_errors` summary instead of the opaque `(response omitted)`.
- **Per-route savings indicator** — routing notice now carries cumulative weekly + 5h counterfactual savings in subscription-percentage-point terms, plus per-provider context (subscription quota remaining for Claude routes, rolling 30-day spend for API routes). Full breakdown via the new `llm_quota_saved` MCP tool.

### Open backlog (next slice)

- **T-CODEX-2** — Codex research-task injection with knowledge-cutoff disclaimer (free fallback when Perplexity rate-limits)
- **T3-L1** — multi-agent supervisor lineage rollups across the parent/child session chain
- **T4-L1** — full ZDR (zero-data-retention) plumbing for routes that demand it
- **T4-XL1** — Customer-Managed-Key (CMK) integration
- **T-QS-2** — observed-calibration path for the quota-saved metric (derive the `$/pp` ratio from each user's own claude_usage history instead of a configured constant)
- Concrete adapters for Hermes / LangGraph / CrewAI / OpenAI Agents SDK / Claude Agent SDK / Pydantic AI
- OIDC / SAML adapter (federated identity)
- Central proxy mode with mTLS (for orgs that require VPC egress isolation)
- GDPR right-to-erasure CLI tool (`chuzom erase-user <email>`)
- Empirical `quality_gap` lookup tables derived from lineage outcomes
- Embedding signal + semantic response cache (sqlite-vec backend)
- Automatic identity-event audit emission

---

## License

MIT.

Chuzom was forked from [llm-router](https://github.com/ypollak2/llm-router) and rebuilt around the signal/decision DSL and enterprise controls. llm-router remains the lightweight personal cost-saver; Chuzom is the version you put in front of an organization.
