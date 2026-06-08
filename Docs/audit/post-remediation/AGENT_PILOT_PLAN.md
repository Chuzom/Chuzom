# Agent Pilot Plan

**Objective.** Determine whether chuzom can host a small, low-risk set of agent workloads without producing runaway cost, attribution gaps, or duplicated side effects.

**Status.** The agent-platform readiness verdict (`AGENTIC_PLATFORM_ASSESSMENT.md`) is **experimentation only**. This pilot validates that even an experimentation envelope is safe; it does **not** validate production readiness.

---

## Eligible agent use cases

Only the following are eligible for this pilot:

1. **Internal code-review agents** producing review comments as plain text. No write authority. No PR creation.
2. **Documentation-generation agents** producing markdown drafts saved to a sandboxed directory. No commit / push.
3. **Test-scaffold agents** generating test files in a developer's local repo. Developer review required before commit.
4. **Internal Q&A agents** answering knowledge-base questions over internal docs. No tool calls with side effects.

## Prohibited use cases

Explicitly excluded from this pilot:

- Any agent with write access to production systems.
- Any agent that creates / modifies customer-visible content.
- Any agent that holds payment / wallet capability (notably `agoragentic_*` — must remain disabled).
- Any agent with > 3 levels of nesting.
- Any long-running agent (> 30 minutes wall-clock per task).
- Any multi-agent workflow that spawns > 5 children per parent.
- Any agent with credentials beyond its own scope.

## Budget limits

Per the budget-enforcement gap analysis (G-002, G-009):

- **Per-agent-session hard cap:** $5 USD (`AGENT_MAX_COST_USD` env or equivalent).
- **Per-developer per-day fleet cap:** $25 USD aggregate across all that developer's agent sessions.
- **Per-pilot per-day fleet cap:** $500 USD across the whole pilot.
- **Workflow cap (parent + children combined):** Manually enforced by the pilot operator using a wrapper that pre-aggregates expected child spend. **Chuzom does not enforce this today.**
- **Daily-spend review.** Pilot operator reviews the previous day's spend by 11am the next morning; any session > $10 triggers a same-day root-cause.

## Iteration limits

These are not enforced by chuzom on `main` (G-008). The pilot enforces them at the **agent-framework layer**, not chuzom:

| Limit | Value | Enforcement |
|---|---|---|
| Max iterations per task | 25 | Agent framework wrapper |
| Max recursion depth | 3 | Agent framework wrapper |
| Max wall-clock per task | 10 minutes | Async timeout in wrapper |
| Max parallel children | 5 | Wrapper semaphore |
| Max parallel sessions per developer | 3 | Wrapper-side counter |

**Pilot will not proceed** for any agent framework that cannot enforce these limits.

## Model policies (chuzom-side)

- Pilot agents may route through any chuzom profile **except** PREMIUM. Reasoning: cost-cap-per-session would be exhausted by a single Opus call.
- BUDGET and BALANCED profiles are allowed.
- The pilot operator may pin a specific model per-agent via `model_override`.

## Human approval gates

Two layers of human approval:

1. **Approval-on-creation.** Every agent definition is reviewed against the eligibility list by the pilot operator + one peer before being enabled.
2. **Approval-on-elevation.** Any pilot agent whose budget cap is requested to be raised above $5 requires explicit operator sign-off, recorded in the audit row's `detail`.

## Cancellation

`asyncio.CancelledError` is **not** wired through `route_and_call` (G-007). The pilot wrapper must therefore:

- Track in-flight provider calls per-session.
- On parent cancel, drop the parent's listening but record that the provider call is still billing.
- Reconcile post-cancel billing with the daily-spend review.

## Observability

Per `AGENTIC_PLATFORM_ASSESSMENT.md` §6, most agent-ops questions cannot be answered today. The pilot operates under explicit constraints:

- **Per-session live monitoring.** Pilot operator subscribes to the audit feed; alerts on any session > $2 in 5 minutes.
- **Daily lineage report.** Lineage SQLite queries produce a top-10 cost-by-agent table.
- **No live "stop agent" control.** Stopping a runaway is process-kill on the agent framework, not a chuzom action.

## Cost-per-outcome metrics

Even at pilot scale we can collect:

- Cost per accepted review comment (with a thumbs-up / thumbs-down review by the receiving developer).
- Cost per merged documentation PR.
- Cost per accepted test scaffold.

These are the **right** unit for evaluating cost optimisation on an agent platform. Pilot must capture them; they are the input for any future decision to route cheaply at scale.

## Quality metrics

- **Review-comment usefulness:** rated 0–3 by the reviewed developer; goal ≥ 1.5 mean.
- **Doc draft acceptance:** % of drafts accepted with ≤ 1 round of edits; goal ≥ 60%.
- **Test scaffold completeness:** % of scaffolds that run without modification; goal ≥ 50%.

## Failure injection

Run at week 2 and week 4:

1. **Provider outage simulation.** Block one provider's hostname for 30 minutes; verify chuzom fallback chain works and audit rows reflect the outage.
2. **Rate-limit simulation.** Reduce one provider's effective quota; verify Retry-After is honoured.
3. **Slow-network simulation.** Add 500ms latency; verify wrapper timeout enforces correctly and chuzom does not silently retry past it.
4. **Audit-DB disk-full simulation.** Fill `~/.chuzom/audit.db` parent disk; verify chuzom does **not** crash the agent (fail-open verified at `audit_routing.py:103-105`).

## Rollback

- Disable the agent definition in the framework's registry.
- Kill any running sessions via `kill -9` on the framework worker processes.
- Restore the previous chuzom config from backup (taken at pilot start).
- Audit `~/.chuzom/audit.db` for any post-rollback writes; verify chain integrity.

## Production-promotion gates

Even after a successful agent pilot, **no agent moves to production** until the following are met:

- [ ] G-001 RBAC enforced
- [ ] G-002 Per-identity atomic budgets
- [ ] G-007 Cancellation propagation
- [ ] G-008 Runaway guards (chuzom-side, not just wrapper-side)
- [ ] G-009 Parent-child budget propagation
- [ ] G-010 Distributed-safe audit log
- [ ] G-017 Container + Helm chart
- [ ] G-018 Runbook including agent-emergency-kill procedure
- [ ] G-020 500+-concurrent load test passing
- [ ] Cost-per-outcome (not cost-per-call) reporting available to platform operator
- [ ] Idempotency-key mechanism for non-idempotent tool calls

These are not pilot-success gates; they are **engineering-precondition** gates.

## Pilot duration and participants

- **Duration:** 6 weeks (2-week setup + 4-week run).
- **Operator:** 1 dedicated platform engineer + 1 chuzom maintainer on-call.
- **Agent count:** 3 agents, max.
- **Eligible developers:** 5–10 across the agent definitions above. Voluntary.

## Exit criteria

**Continue / expand if all of these:**

- Zero P0/P1 incidents.
- All budget caps held — no session exceeded $5; no developer-day exceeded $25.
- All four failure-injection drills passed without manual intervention beyond expected.
- Cost-per-outcome metrics meet defined targets.
- No audit-row gaps detected.

**Terminate if any one:**

- A runaway session was stopped only by manual process kill, not by any in-product or wrapper guard.
- A budget cap was exceeded by ≥ 10%.
- A non-idempotent tool was invoked twice for the same logical task.
- A multi-process audit-write incident corrupted the chain.
- Failure-injection drills required > 1 engineering-hour of manual recovery.

---

## Note on framing

A successful agent pilot proves that chuzom can be **wrapped** to host low-risk agents safely. It does **not** prove that chuzom itself provides the guardrails needed for a production agent platform. The wrapper is doing most of the heavy lifting; the pilot is therefore primarily a test of the wrapper's discipline.

For chuzom to **be** the agent platform's safety layer (not be wrapped by it), the production-promotion gates above must be closed at the chuzom level, not the wrapper level.
