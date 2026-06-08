<p align="center">
  <img src="assets/chuzom-logo.png" alt="Chuzom — meeting of rivers" width="640">
</p>

<h1 align="center">Chuzom</h1>

<p align="center">
  <em>Meeting of rivers, routing intelligence.</em>
</p>

<p align="center">
  <strong>The enterprise-ready LLM router for developer organizations.</strong><br/>
  Route every prompt to the cheapest capable model. Log every decision in a tamper-evident audit chain. Enforce per-user and per-team budgets. Ship telemetry to OpenTelemetry. Stays local; no proxy.
</p>

<p align="center">
  <a href="https://pypi.org/project/chuzom-router/"><img src="https://img.shields.io/badge/pypi-chuzom--router-4F46E5?style=flat-square" alt="PyPI"></a>
  <a href="https://github.com/ypollak2/chuzom"><img src="https://img.shields.io/badge/tests-766_passing-10B981?style=flat-square" alt="Tests"></a>
  <a href="https://github.com/ypollak2/chuzom"><img src="https://img.shields.io/badge/python-3.10+-3572A5?style=flat-square" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-10B981?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/SOC%202-mappable-8B5CF6?style=flat-square" alt="SOC 2">
  <img src="https://img.shields.io/badge/GDPR-mappable-8B5CF6?style=flat-square" alt="GDPR">
  <img src="https://img.shields.io/badge/OTEL-traces%20%2B%20metrics%20%2B%20logs-F59E0B?style=flat-square" alt="OTel">
</p>

<p align="center">
  <strong>Install in 30 seconds</strong>
</p>

<p align="center">

```bash
pip install chuzom-router
chuzom install --host claude-code   # or cursor / codex-cli / gemini-cli
```

</p>

<p align="center">
  <sub>Works with Claude Code · Cursor · Codex CLI · Gemini CLI · Claude Desktop · Factory IDE · Trae · 7 more</sub><br/>
  <sub><strong>Local-first.</strong> No hosted proxy. No account required. Optional org control plane.</sub>
</p>

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

- **Cost reduction** of 35–80% on routine work via tier-based routing
- **Tamper-evident audit log** with SHA-256 hash chain — every routing decision, quota breach, policy change captured
- **Per-user + per-team quotas** with pre-emptive refusal (no spend on rejected calls)
- **PII / secret detection** that forces local-only routing when prompts contain credentials
- **OpenTelemetry export** — spans + metrics + logs to Honeycomb, Datadog, Grafana, Jaeger
- **Multi-CLI host support** for Claude Code, Cursor, Codex CLI, Gemini CLI, Claude Desktop, and 9 more
- **Agent framework adapters** — Agno concrete; Hermes + LangGraph + CrewAI + OpenAI Agents SDK + Claude Agent SDK + Pydantic AI shaped for v0.0.3
- **Routing inversion detection** — flags when complex prompts go cheap (underserved) or simple prompts go premium (overspend)
- **Rich live dashboard** with status banner, tier distribution, latency histogram, agent rollups, watch mode
- **Per-route visibility** — every routed reply begins with `🎯 chuzom → <model> · <task>/<complexity> · <latency>` so you can see where each prompt landed without leaving the chat
- **Self-debug-safe** — chuzom recognises prompts that target chuzom itself (debug, route, hook, install, etc.) and bypasses enforcement so you never get locked out of the tools needed to repair chuzom
- **766 tests** including scenario reports that render as readable stories

---

## What makes Chuzom different

|  | llm-router | **Chuzom** |
|---|:---:|:---:|
| Cost-aware multi-provider routing | ✅ | ✅ |
| Local-first, no proxy | ✅ | ✅ |
| **Signal/decision YAML DSL** | — | ✅ |
| **Agent-aware sessions with budget envelope** | — | ✅ |
| **Hash-chained audit log (SOC 2 / GDPR / HIPAA mappable)** | — | ✅ |
| **RBAC: 4 roles × 12 permissions** | — | ✅ |
| **Per-user + per-team quotas with pre-emptive refusal** | — | ✅ |
| **PII redaction before lineage write (12 patterns + custom)** | — | ✅ |
| **Vault / AWS Secrets Manager / GCP SM YAML indirections** | — | ✅ |
| **OpenTelemetry traces + metrics + logs (auto-emit per decision)** | — | ✅ |
| **Routing inversion detection (up + down)** | — | ✅ |
| **Scenario reports with narrative routing traces** | — | ✅ |
| **Per-host integration matrix** | 8 hosts | **14 hosts** |
| **Agent framework adapters** | — | **7 frameworks** |
| **Pareto-frontier model registry from artificialanalysis.ai** | — | ✅ |
| **Test count** | ~200 | **732** |

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

Swap `--compact` for the full painterly Chhuzom-confluence banner (78 lines of 24-bit ANSI art) by dropping the flag. `chuzom welcome` prints to stdout, so it works in any shell that supports function wrappers — `zsh`, `bash` (with `function claude() { ... }`), `fish`, etc.

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

Full integration matrix in [`Docs/HOST_INTEGRATION_REPORT.md`](Docs/HOST_INTEGRATION_REPORT.md) (118 structural tests, all green).

---

## Agent framework adapters

| Framework | Status | What you get |
|---|:---:|---|
| **[Agno](https://github.com/agno-agi/agno)** (primary) | **concrete** | `RouteredModel` + `RouteredTeam` — drop-in for `agno.models.base.Model`; full budget envelope; lineage tagged `framework="agno"` |
| **Hermes** | skeleton (v0.0.3) | Protocol-shape pinned; concrete impl deferred until tool-use format is confirmed |
| **LangGraph** | stub (v0.0.3+) | Adapter shape ready; Runnable wrapping next |
| **CrewAI** | stub (v0.0.3+) | LiteLLM-compatible completion shim path |
| **OpenAI Agents SDK** | stub (v0.0.3+) | AsyncOpenAI client wrap path |
| **Claude Agent SDK** | stub (v0.0.3+) | anthropic client wrap path |
| **Pydantic AI** | stub (v0.0.3+) | Model-protocol implementation path |

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

### 💵 Per-user + per-team quotas

```python
from chuzom.enterprise import QuotaPolicy, QuotaTracker

quotas = QuotaTracker()
quotas.set_policy("user", alice.id, QuotaPolicy(
    daily_cap_usd=20.0,
    monthly_cap_usd=300.0,
    soft_warning_pct=0.80,
    hard_block=True,
))

# Pre-emptive refusal — no money spent on rejected calls
breached, info = quotas.would_exceed("user", alice.id, prospective_cost_usd=0.50)
if breached:
    return {"error": "quota_exceeded", **info}
```

Daily + monthly caps, soft warning thresholds, hard refusal mode, UTC-aligned period buckets.

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

Full deployment guide: [`Docs/ENTERPRISE_DEPLOYMENT.md`](Docs/ENTERPRISE_DEPLOYMENT.md). Threat model: [`Docs/THREAT_MODEL.md`](Docs/THREAT_MODEL.md). Security posture: [`SECURITY.md`](SECURITY.md).

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
              │  • embedding_match     (v0.0.3)      │
              │  • reask               (v0.0.3)      │
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

Architecture deep-dive: [`Docs/ARCHITECTURE.md`](Docs/ARCHITECTURE.md).

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
chuzom welcome              # painterly Chhuzom-confluence banner
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
| `CHUZOM_DEV_SRC` | absolute path | Source directory used by `chuzom dev-refresh` when `--source` isn't passed. |
| `CHUZOM_CLAUDE_SUBSCRIPTION` | `true` / `1` / `yes` | Forces subscription-mode banner + OAuth pressure cascade even when not auto-detected. |
| `CHUZOM_*_PATH` | absolute path | Override the location of any state DB (`CHUZOM_LINEAGE_PATH`, `CHUZOM_AUDIT_PATH`, etc.). |

### State DBs

State lives in `~/.chuzom/` (override per-DB via `CHUZOM_*_PATH` env vars):

| File | Purpose |
|---|---|
| `lineage.db` | Every routing decision |
| `sessions.db` | Agent session lifecycle |
| `identity.db` | Users + teams + tokens |
| `audit.db` | Immutable hash-chained audit |
| `quotas.db` | Per-identity consumption + policies |
| `cache.db` | Semantic response cache (v0.0.2 stub) |
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

| Tier | Count | Coverage |
|---|---|---|
| Unit (lineage / signals / agents / decisions / bench) | 112 | foundation |
| Integration (12 hosts) | 118 | host structural |
| QA — 5 pillars + Agno deep | 166 | functional / non-functional / perf / integrity / usability |
| QA — MCP handshake (live subprocess) | 10 | protocol layer end-to-end |
| QA — network failure simulation | 22 | circuit breaker state machine |
| QA — multi-host coexistence | 13 | Chuzom + llm-router parallel |
| QA — framework contracts (6 stubs) | 88 | per-framework × 14 contract dims |
| QA — session summary | 16 | dashboard data + render |
| QA — plugin packaging | 18 | marketplace + MCP-config plugins |
| QA — observability (OTLP) | 16 | spans + metrics + logs |
| QA — model registry | 17 | YAML + Pareto + filtering |
| QA — org policy (secure YAML) | 21 | plaintext rejection + resolution |
| QA — **enterprise (identity + RBAC + audit + redaction + quotas)** | **53** | per-module + parametrized |
| Scenario reports | 24 | CLI + framework + cross-cutting |
| Auto-route classifier regression | 52 | inherited + fix-verb expansion |

**732 total tests passing**, 0 failed, 129 intentional skips. 26 second wall time.

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
| [`SECURITY.md`](SECURITY.md) | Responsible disclosure, posture, SOC 2 / GDPR / HIPAA / PCI mapping |
| [`Docs/ARCHITECTURE.md`](Docs/ARCHITECTURE.md) | Three-ring architecture, data flows, package layout |
| [`Docs/ENTERPRISE_DEPLOYMENT.md`](Docs/ENTERPRISE_DEPLOYMENT.md) | Deployment topology, IdP integration, audit shipping, runbooks |
| [`Docs/THREAT_MODEL.md`](Docs/THREAT_MODEL.md) | STRIDE per asset, attack scenario walkthroughs, residual risks |
| [`Docs/QA_TEST_STRATEGY.md`](Docs/QA_TEST_STRATEGY.md) | Five pillars, quality gates with explicit thresholds, risk register |
| [`Docs/QA_TEST_REPORT.md`](Docs/QA_TEST_REPORT.md) | Per-pillar + per-host scorecards (auto-generated) |
| [`Docs/SCENARIO_REPORT.md`](Docs/SCENARIO_REPORT.md) | Per-scenario narrative routing journeys |
| [`Docs/HOST_INTEGRATION_REPORT.md`](Docs/HOST_INTEGRATION_REPORT.md) | 14-host integration matrix + verification status |
| [`CHANGELOG.md`](CHANGELOG.md) | Release notes |

---

## Status

**v0.0.2** — feature-complete for the dogfood ring. 732 tests passing. SECURITY.md, threat model, and enterprise deployment guide all shipped. Plugin packaging verified for Claude Code, Cursor, Codex CLI, Gemini CLI.

**v0.0.3** roadmap (next):
- Concrete adapters for Hermes / LangGraph / CrewAI / OpenAI Agents SDK / Claude Agent SDK / Pydantic AI
- OIDC / SAML adapter (federated identity)
- Central proxy mode with mTLS (for orgs that require VPC egress isolation)
- GDPR right-to-erasure CLI tool (`chuzom erase-user <email>`)
- Empirical `quality_gap` lookup tables derived from lineage outcomes
- Embedding signal + semantic response cache (sqlite-vec backend)
- Per-team model allow/deny lists
- Automatic identity-event audit emission

---

## License

MIT.

Chuzom was forked from [llm-router](https://github.com/ypollak2/llm-router) and rebuilt around the signal/decision DSL and enterprise controls. llm-router remains the lightweight personal cost-saver; Chuzom is the version you put in front of an organization.
