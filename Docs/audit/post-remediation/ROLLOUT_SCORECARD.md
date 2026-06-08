# Rollout Scorecard

**Scale.** 0 = absent · 1 = experimental · 2 = basic · 3 = production-capable with important gaps · 4 = strong enterprise · 5 = mature and independently validated.

**Baseline.** The 2026-06-08 pre-remediation scorecard was **1.65 / 5** weighted. This post-remediation scorecard tracks movement.

---

## Per-domain scores

| Domain | Pre | Post | Δ | Justification |
|---|---|---|---|---|
| Developer onboarding | 3 | 3 | — | Wizard + 14 host integrations work. No central rollout still. |
| Developer compatibility | 3 | 3 | — | LiteLLM-based; PRO-001/PRO-002 unaddressed. |
| Developer productivity protection | 1 | 1 | — | No controlled quality comparison exists. |
| Central administration | 1 | 1 | — | Per-instance config only; no admin API/UI. |
| Policy enforcement | 1 | 1 | — | RBAC unwired (G-001). |
| Identity and attribution | 1 | 2 | +1 | TurnIdentity + audit row + log contextvars wired (Tier 1+2). No tenant. |
| Cost accuracy | 2 | 2 | — | Per-call cost rows accurate within chuzom; not reconciled with invoices. |
| Savings verification | 2 | 2 | — | Per-call counterfactual exists; no fleet-level proof. |
| Budget enforcement | 2 | 2 | — | Global only; per-identity absent. |
| Reliability | 3 | 3 | — | Retry-After + fallback chain unchanged. |
| Security | 1 | 3 | +2 | SEC-001/002/003 + INV-007 + ROU-001 closed. |
| Privacy | 1 | 1 | — | PRI-001/002/003 unchanged. |
| Observability | 2 | 3 | +1 | request_id/user_id/org_id/agent_id in log contextvars. tenant_id absent. |
| Auditability | 1 | 3 | +2 | One row per turn, hash-chain, verify_chain stress-tested. No operator-facing verify endpoint; no distributed-safe story. |
| Provider resilience | 3 | 3 | — | Unchanged. |
| Distributed consistency | 0 | 0 | — | No work done. |
| Agent identity | 1 | 2 | +1 | agent_id field added; no agent registry. |
| Agent lineage | 1 | 1 | — | Parent-child not propagated. |
| Agent budget control | 1 | 1 | — | No parent-child propagation; no hierarchical budgets. |
| Agent runaway protection | 1 | 1 | — | No iteration / wall-clock / cancel guards. |
| Agent routing quality | 1 | 1 | — | Same router as developer; no agent-aware policy. |
| Agent operational control | 1 | 1 | — | No kill switch; no pause. |
| Deployment | 2 | 2 | — | No container/Helm/K8s. |
| Maintainability | 2 | 2 | — | router.py monolith persists. |
| Supportability | 1 | 1 | — | No runbook, no on-call playbook. |

---

## Weighted readiness scores

The same block weighting as the 2026-06-08 scorecard is used for comparability.

| Block | Domains | Avg pre | Avg post | Weight |
|---|---|---|---|---|
| Security & trust | Security, Privacy, Distributed consistency, Identity & attribution, Auditability, (Compliance) | 0.83 | 1.83 | 30% |
| Routing & cost | Routing reliability, Compatibility, Cost accuracy, Savings verification | 2.33 | 2.50 | 15% |
| Reliability & scale | Reliability, Distributed consistency, Observability | 2.33 | 2.00 | 15% |
| Test & maintain | Maintainability, (Test maturity) | 2.00 | 2.00 | 10% |
| User-facing | Onboarding, Compatibility, Productivity protection, Central administration | 2.00 | 2.00 | 15% |
| Agent + deploy | Agent identity/lineage/budget/runaway/routing/ops + Deployment | 1.50 | 1.43 | 15% |

**Weighted post-remediation score: 2.05 / 5** (up from 1.65).

**Maturity stage:** **Basic.** Above prototype. Below production-capable. The +0.4 movement is real and concentrated in Security + Auditability + Identity attribution.

---

## Per-rollout readiness verdicts

### Developer rollout readiness

| Question | Score (0-5) | Comment |
|---|---|---|
| Onboarding scales to fleet | 1 | Per-dev keys; no central push. |
| Compatibility preserved | 3 | LiteLLM normalisation-loss unmeasured. |
| Productivity preserved | 1 | Not measured. |
| Bypass-resistant | 1 | Trivial bypass. |
| Cost provable to Finance | 1 | No invoice reconciliation. |

**Composite: 1.4 / 5.** Pilot OK; broad rollout not OK; mandatory rollout not OK.

### Central governance readiness

| Question | Score |
|---|---|
| Central policy as object | 0 |
| Runtime enforcement | 1 |
| SSO/SCIM/OIDC | 0 |
| Distributed audit | 0 |
| Emergency controls | 1 |

**Composite: 0.4 / 5.** Configuration layer only.

### Agentic-platform readiness

| Question | Score |
|---|---|
| Hierarchical identity | 2 |
| Hierarchical budget | 1 |
| Runaway protection | 1 |
| Cancellation | 0 |
| Operational control | 1 |
| Load-tested | 0 |

**Composite: 0.83 / 5.** Experimentation only.

### Financial confidence

| Question | Score |
|---|---|
| Per-call accounting | 3 |
| Counterfactual baseline | 2 |
| Provider invoice reconciliation | 0 |
| Net-of-hidden-cost | 0 |
| Independent verification | 0 |

**Composite: 1.0 / 5.** Plausible but unverified.

---

## Movement summary

The remediation cycle materially improved **Security**, **Auditability**, and **Identity attribution** — exactly the three domains where the original audit anchored the lowest scores. No movement on **Central administration**, **Distributed consistency**, **Agent budget / runaway / operational control**, **Deployment**, **Supportability** — the domains that determine enterprise readiness for shared infrastructure or autonomous workloads.

Overall + 0.4 on a 5-point weighted scale is honest, not transformational. The product is now a **defensible developer-tool with credible per-turn audit hygiene**, not yet an enterprise-deployable control plane.
