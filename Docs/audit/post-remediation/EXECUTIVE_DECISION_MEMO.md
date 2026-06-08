# Executive Decision Memo

**To:** CTO, VP Engineering, CISO, Head of Platform, Head of AI, Finance leadership
**From:** Post-remediation enterprise acceptance audit
**Re:** chuzom — decision required for developer rollout, central governance, and agentic-platform use
**Date:** 2026-06-08

---

## Decision required

Three independent decisions, not one:

1. **Should we deploy chuzom to all developers and route every model call through it?**
2. **Should we adopt chuzom as the central control plane for model usage governance?**
3. **Should we host our enterprise agentic platform on chuzom?**

The audit answers each question separately and does not average them.

## Recommendation summary

| Decision | Recommendation |
|---|---|
| 1. Developer rollout | **Controlled pilot only.** Not for broad rollout. Not mandatory. |
| 2. Central governance | **No.** What exists is configuration plus a per-process audit log, not a control plane. |
| 3. Agentic platform | **No, for production.** Yes for **low-risk experimentation only.** |
| Cost-saving claims | **Plausible but unverified.** Reconcile with provider invoices before any Finance-visible claim. |

---

## Business opportunity

Chuzom plausibly reduces gross model-call cost by routing each request to the cheapest model that can handle it. Across the 14 host integrations it supports, this is achievable per-developer with low setup friction. If the same routing logic can be safely applied at organisation scale, the savings compound.

The opportunity is real. The question is whether the implementation as it stands today preserves the four properties enterprise adoption requires:

1. **Net savings**, not just cheaper-per-call.
2. **Developer productivity** — no measurable quality regression.
3. **Central control** — policy enforced by the platform, not by trusted clients.
4. **Safety at scale** — autonomous agents bounded by hard, in-product guards.

The current evidence supports #1 only directionally, #2 not at all, #3 not at all, and #4 not at all. Two of the four properties are not just unmeasured — they require new systems to exist before they can be measured.

## Current evidence (what the remediation cycle bought)

In the 2026-06 remediation cycle, 8 of the 14 Critical-and-High findings from the original audit were closed: the SSE-zero-auth issue, the filesystem-tool sandbox, the agoragentic-wallet opt-in, the per-session classification race, the truth-in-marketing reconciliation, and the silently-excluded test suites. A per-turn tamper-evident audit row is now written, attributed to a `user_id` (and optionally `agent_id`) resolved from environment variables; `verify_chain()` passes a 1000-decision stress test.

These movements are **real and verifiable in code** (see `REMEDIATION_VERIFICATION.md`). They moved the weighted readiness score from **1.65 → 2.05** on a 5-point scale — a meaningful step out of the experimental band, but well short of the production band.

What did **not** change:

- **No RBAC** is enforced at the routing chokepoint. The `Permission.ROUTE_PROMPT` check that the original audit called for does not exist on the path.
- **No per-identity budgets.** Budgets remain provider-scoped.
- **No multi-tenant axis.** `tenant_id` does not appear anywhere in identity, budgets, audit, or routing.
- **No central control plane.** Configuration is per-instance .env + per-user YAML.
- **No SSO / SCIM / OIDC.**
- **No provider-invoice reconciliation pipeline.** Finance cannot validate the savings claim against the source of truth.
- **No deployment artefacts** for shared infrastructure (no container, no Helm).
- **No cancellation / deadline propagation** in the routing path.
- **No runaway-agent guards** at the chuzom level beyond per-session $5 hard caps.

The six unaddressed findings (INV-011, ROU-002, PRI-001, OBS-001/tenant, TST-003) and the four post-remediation gaps (control plane, SSO, reconciliation, deployment artefacts) are all parked behind a product decision the team has explicitly deferred: the multi-tenancy model question (`Q-P-2`).

## Financial case

| Question | Answer (today) |
|---|---|
| Does chuzom report a per-call cost? | Yes, accurately, per chuzom's own metering. |
| Does it report a per-call counterfactual? | Yes, vs. the host model. |
| Does it report a fleet-level baseline (direct provider)? | No. |
| Can Finance reconcile chuzom's reported cost with the provider invoice? | No. |
| Is net savings — after retries, fallbacks, quality cost, rework, and chuzom operating cost — calculated? | No. |
| Does the savings number bound any of the seven net-value terms in our scoring model? | Two of seven. |

**Net.** Any savings figure attributed to chuzom today is **directional**. It cannot be presented to Finance as a verified financial outcome. The path to "verified" requires the experiment program described in `COST_SAVINGS_VALIDATION.md` §6.

## Technical risk

The technical risks fall into three buckets:

1. **Developer productivity regression** (medium-high probability, medium impact). Routing a request to a cheaper model can quietly degrade tool-call validity, prompt-cache hits, or reasoning quality. The remediation cycle did not measure this. A pilot can.

2. **Bypass at scale** (high probability, low–medium impact). Today a developer with their own provider key can route directly to the provider and the platform team will not know. Mandatory enforcement requires removing provider keys from developer environments and brokering them server-side — a system that does not exist.

3. **Cost-attribution gaps** (high probability, medium–high impact). Per-team, per-project, per-agent attribution is not present. Showback / chargeback to teams cannot be done from chuzom data alone.

## Security risk

The remediation cycle materially improved the security posture. The two Critical findings (`chuzom-sse` and unsandboxed filesystem tools) and the wallet-tools-default-on issue are closed and regression-tested. **No new Critical security finding was found in the post-remediation inspection.**

Remaining security risks are policy gaps, not bugs:

- The `chuzom://status` MCP resource returns provider configuration to any caller; no identity gating.
- The `CHUZOM_AUDIT_DISABLED=1` env disables auditing locally. Acceptable for testing, unacceptable in a regulated rollout.
- Provider-side data flow (no ZDR plumbing, no redaction-in-routing) means sensitive prompts can reach a provider that may retain them.

## Agentic risk

This is the most serious unresolved risk. Per `AGENTIC_PLATFORM_ASSESSMENT.md`:

- **No cancellation propagation.** Killing a parent agent does not abort the running provider call. Cost continues to accrue past cancellation.
- **No iteration / wall-clock / cost-per-task guards.** A poorly-written agent loop can spend its $5 session cap in seconds; nothing higher in the system catches the pattern in time.
- **No parent-child budget propagation.** Child agents spend independently of parent budgets. A workflow of $10 can burn $50 across children.
- **No distributed-safe audit log.** Multi-process write coordination is SQLite's file lock. Adequate for a few processes per host; inadequate for a fleet.
- **No load tests** for the routing path under 100+ concurrent calls.

Hosting hundreds-to-thousands of concurrent agents on chuzom as it stands today exposes the organisation to runaway-cost and side-effect-duplication risks that are not bounded by any in-product control. **The agent-platform readiness verdict is no.**

## Rollout recommendation

The audit recommends a **two-track posture**:

### Track A (concurrent): Controlled developer pilot

Run the 20-developer, two-team, 8-week pilot in `PILOT_PLAN.md`. Expected investment: 1 dedicated pilot engineer + 0.25 FTE of chuzom maintainer time + 20 developer-volunteer time. Expected output: an evidence-backed answer to "does chuzom save us money without hurting our developers?"

### Track B (concurrent): Phase-3 engineering

Begin the engineering required to close the 10 enterprise gaps (`GAP_ANALYSIS.md`, G-001 through G-010). This is a quarter-plus of focused work covering: RBAC wiring, per-identity budgets, multi-tenancy decision, control plane prototype, SSO/SCIM integration, reconciliation pipeline, distributed-safe audit, cancellation propagation, runaway guards, parent-child budgets.

**Do not** start Track C (agent-platform integration) until Track B's must-haves close and an agent pilot (`AGENT_PILOT_PLAN.md`) succeeds.

## Investment required

| Track | Headcount | Duration | Cost (rough) |
|---|---|---|---|
| Track A pilot | 1 engineer + light maintainer time + 20 dev-volunteers | 8 weeks | ~$120k including dev-time-share + provider-spend cap |
| Track B engineering | 4 engineers (1 platform lead, 2 backend, 1 security) | 16–20 weeks | ~$1.0M FTE-equivalent |
| Track C agent integration (post-Track B) | 2 engineers + 1 SRE | 8 weeks | ~$300k |

Numbers are placeholder; the relative shapes are what matter. **Track B is the load-bearing investment.** Without it, no broader rollout is responsible regardless of Track A's results.

## Decision gates

The decision to expand from pilot to broad rollout to mandatory deployment is gated by the criteria in `DEVELOPER_ROLLOUT_ASSESSMENT.md` §5 and `ROLLOUT_SCORECARD.md`. The gates are not subjective. They are testable, and they should be tested before each promotion.

To consolidate:

| Gate | For broad | For mandatory | For agent platform |
|---|---|---|---|
| Closed: G-001 RBAC | required | required | required |
| Closed: G-002 per-identity budgets | required (pilot OK without) | required | required |
| Closed: G-003 tenant axis | optional | required | required |
| Closed: G-004 control plane | optional | required | required |
| Closed: G-005 SSO | optional | required | optional |
| Closed: G-006 invoice reconciliation | required for Finance trust | required | required |
| Closed: G-007 cancellation | optional | optional | required |
| Closed: G-008 runaway guards | optional | optional | required |
| Closed: G-009 parent-child budgets | n/a | n/a | required |
| Closed: G-010 distributed audit | optional | required | required |

## Final recommendation

The 2026-06 remediation cycle materially improved chuzom's security posture and identity-attribution surface. The improvements are real and well-tested. They do not, however, change the fundamental reality that chuzom is a developer-tool with shelved enterprise scaffolding plus a per-turn audit row — it is not yet an enterprise control plane and it is not yet a safe agent-platform substrate.

**The audit's recommendation:**

1. **Approve** the controlled 20-developer pilot in `PILOT_PLAN.md`. Treat its outcome as the input to a later go/no-go on broader rollout.
2. **Do not approve** broad developer rollout, mandatory developer use, central governance adoption, or agentic-platform use at this time.
3. **Authorise** the Track B engineering investment if the organisation intends to make chuzom enterprise infrastructure within 2–3 quarters. Without that investment, the gap between current state and enterprise need will not close on its own.
4. **Defer** the agent-platform decision until Track B's must-haves close and an agent pilot (`AGENT_PILOT_PLAN.md`) succeeds — and even then, do not use chuzom for any agent with non-reversible side effects until idempotency, cancellation, and runaway guards are first-class chuzom features, not wrapper conveniences.

The cost of these recommendations is acknowledged: deferring broad rollout means a longer period before any meaningful spend reduction at fleet scale. The cost of *not* deferring is higher — mandatory use of an unverified routing strategy on top of an unenforced control plane, against unreconciled cost data, is not a posture this organisation should sign off on.

— End of memo —
