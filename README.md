<p align="center">
  <img src="https://raw.githubusercontent.com/Chuzom/chuzom/main/assets/chuzom-logo.png" alt="Chuzom — river-confluence emblem, routing intelligence" width="640">
</p>

<h1 align="center">Chuzom</h1>

<p align="center"><em>Meeting of rivers, routing intelligence.</em></p>

<p align="center">
  <strong>Local-first LLM router for developer workstations.</strong><br/>
  Route every prompt to the cheapest model that can actually do the job — and log every decision locally.<br/>
  No proxy. No account. Drop-in for Claude Code, Cursor, Codex CLI, Gemini CLI, and more.
</p>

<p align="center">
  <a href="https://pypi.org/project/chuzom-router/"><img src="https://img.shields.io/badge/pypi-chuzom--router-4F46E5?style=flat-square" alt="PyPI"></a>
  <a href="https://github.com/Chuzom/chuzom/actions/workflows/ci.yml"><img src="https://github.com/Chuzom/chuzom/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Chuzom/chuzom/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-10B981?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10+-3572A5?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/developer_router-stable-10B981?style=flat-square" alt="Developer router: stable">
  <img src="https://img.shields.io/badge/enterprise_control_plane-beta-F59E0B?style=flat-square" alt="Enterprise: beta">
</p>

<p align="center">
  <sub><strong>Maturity (honest):</strong> the <strong>developer router is stable</strong> — that's the production path. The <strong>enterprise control plane is beta</strong>: RBAC, SSO/OIDC, and a tamper-evident audit chain are wired and enforced under <code>CHUZOM_DEPLOYMENT_PROFILE=enterprise</code>; SCIM, team-budget enforcement, and multi-instance HA are in progress. See <a href="#enterprise-control-plane-beta">Enterprise</a> for the per-feature status.</sub>
</p>

---

## Install (30 seconds)

```bash
pip install chuzom-router
chuzom install --host claude-code     # or: cursor · codex · gemini-cli · claude-desktop · all
```

```bash
chuzom doctor          # verify hooks, MCP server, providers
chuzom summary --watch # live cost-savings dashboard
```

Bring the API keys for the providers you want (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_BASE_URL` for free local models). Works with **zero keys** on a Claude Code Pro/Max or Codex subscription.

---

## What you get

- **35–80 % cost reduction** on routine work via tier-based routing — measured head-to-head vs always-cheap / always-premium on a fixed corpus (`python -m bench`).
- **Cheapest-capable routing** — each prompt is classified (task + complexity) and sent to the first model in a free-first chain that can handle it, with **circuit-breaker failover** when a provider is down.
- **Local lineage + a hash-chained audit log** of every decision — stays on your machine, no telemetry.
- **A single per-route line** on every reply: `🎯 chuzom → <model> · <task>/<complexity> · <latency> · saved $X`.
- **Drop-in for your existing tools** — installs as an MCP server + hooks; your workflow doesn't change.
- **PII / secret detection** that forces local-only routing when a prompt contains credentials.

---

## How it works

A prompt flows through five independent layers — each a pure, test-pinned contract — on its way to a model:

```
  prompt  ─►  1. CLASSIFY        task type + complexity (signals: pii/secret, code, research, …)
            ─►  2. RESOLVE         deployment profile (developer | enterprise) + identity
            ─►  3. BUILD CHAIN     ordered candidates, cheapest-capable first
                                   (+ subscription-local / quota-balance reordering)
            ─►  4. ENFORCE         (enterprise) RBAC allow-lists · PII redaction · budget reserve
            ─►  5. DISPATCH        walk the chain with circuit-breaker failover + cancel shield
  reply  ◄──  AUDIT + LINEAGE     hash-chained audit row + local lineage; savings banner returned
```

In **developer** mode (the default) steps 2 and 4 are near no-ops: identity is your local user and there's nothing to enforce — you just get cheap, resilient routing. Under `CHUZOM_DEPLOYMENT_PROFILE=enterprise`, step 4 turns on: RBAC denies disallowed models *before* dispatch, redaction defaults on, and the audit row is mandatory.

> **Self-reference bypass.** If a prompt is about Chuzom itself in a debug context (*"chuzom is stuck"*), the hook short-circuits before routing — so a broken router can never block the tools you need to fix it. The bypass is logged for the audit trail (and *refused* under the enterprise profile).

Deep dive: [`Docs/ARCHITECTURE.md`](https://github.com/Chuzom/chuzom/blob/main/Docs/ARCHITECTURE.md).

---

## What makes Chuzom different

Chuzom isn't a hosted gateway — it's a **local-first router on your workstation**, so the honest comparison is against the tools you already reach for.

| | Chuzom | Hosted gateway (LiteLLM proxy / OpenRouter) | Your IDE's built-in picker |
|---|:---:|:---:|:---:|
| Runs locally, no proxy/account | ✅ | — | ✅ |
| Cheapest-capable per-prompt routing | ✅ | 🟡 | — |
| Local audit/lineage of every decision | ✅ | 🟡 (their server) | — |
| Drop-in across many dev tools | ✅ | 🟡 | — |
| Org governance (RBAC/SSO/budgets) | 🟡 beta | ✅ | — |

---

## Enterprise control plane (beta)

Activated by `CHUZOM_DEPLOYMENT_PROFILE=enterprise`. Honest, per-feature status (from a recent internal audit):

| Capability | Status |
|---|---|
| **RBAC** on the routing path — denies disallowed providers/models before dispatch; fails closed | ✅ wired & enforced |
| **SSO / OIDC** JWT federation (RS256-pinned, JIT user provisioning) | ✅ wired |
| **Tamper-evident audit chain** (SHA-256 prev-hash, un-disableable under enterprise) | ✅ wired · verify-CLI on roadmap |
| **Identity + API tokens** (SHA-256 hashed at rest, issue/revoke/expire) | ✅ |
| **Per-identity budgets** (atomic check-then-charge, single node) | ✅ |
| **SCIM 2.0 provisioning** | 🟡 built, mounting + role-mapping in progress |
| **Team-budget enforcement** | 🟡 set via admin API; enforcement on roadmap |
| **Multi-instance HA** (Postgres-coordinated budgets) | 🟡 experimental |
| **Control-plane → routing** (provider disable, policy versioning) | 🟡 wiring in progress |

> We mark these honestly on purpose: everything ✅ survives a buyer's technical due-diligence today; everything 🟡 is on the public roadmap. We'd rather under-promise.

---

## Open-core

| | License | What |
|---|---|---|
| **`chuzom-router`** (this repo) | **MIT** | Everything that helps *you* spend less on your own keys — routing, local budgets, local audit, your dashboard. **Free, forever.** |
| **Chuzom Enterprise** *(coming)* | Commercial | Everything that governs *other people's* access & spend — RBAC, SSO/SCIM, team budgets, mandatory audit, multi-instance HA. |

**The line:** *single-user value is free; control-over-others is paid.*

---

## CLI

```
chuzom install [--host <name>|all]   wire into a host (Claude Code, Cursor, Codex, …)
chuzom doctor                        diagnose hooks / MCP / providers
chuzom summary [--watch]             cost-savings dashboard
chuzom serve [--admin]               run as an HTTP/SSE service (container / systemd)
chuzom --version
```

## Tests & contributing

### Running tests

This package is **public open-source** with an **enterprise control plane** as optional backlog (SCIM/OIDC, RBAC, Postgres multi-instance, etc.). The test suite is split accordingly:

- **Public tests** (`tests/`): Developer router features (routing, quotas, redaction)
- **Enterprise tests** (`tests/enterprise/`): RBAC, audit chain, admin API, SCIM/OIDC

The default `pytest` runs only the **public** test suite:

```bash
pytest                    # Run public tests (fast)
pytest tests/enterprise   # Run enterprise tests (requires Docker for Postgres)
pytest tests/             # Run all tests
```

For CI on public distributions, only `tests/` is run. Enterprise CI runs the full suite.

Full test suite runs in CI on every push across Python 3.11 + 3.13. Contributions welcome — see [`CONTRIBUTING.md`](https://github.com/Chuzom/chuzom/blob/main/CONTRIBUTING.md).

## License

[MIT](https://github.com/Chuzom/chuzom/blob/main/LICENSE) © the Chuzom contributors.
