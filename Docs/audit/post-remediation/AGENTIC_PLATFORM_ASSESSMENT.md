# Agentic-Platform Assessment

**Question being answered.** Could chuzom safely host hundreds-to-thousands of concurrent enterprise agents — nested, long-running, expensive, with production side effects?

**Verdict:** **No. Not for production. Suitable for low-risk experimentation only.** Use of chuzom on a real agentic platform today exposes the organisation to runaway-cost, attribution-gap, and side-effect-duplication risks that are not bounded by any in-product control.

---

## 1. Per-request attribution and lineage

| Required attribution | State | Evidence |
|---|---|---|
| Organisation | Partial — `org_id` in `TurnIdentity` from `CHUZOM_ORG_ID` env. Single-org per instance. | `identity.py:48-77` |
| Tenant | **Missing** | No `tenant_id` field anywhere. |
| Team | **Missing** | No `team_id`. |
| Project | **Missing** | No `project_id`. |
| Environment (dev / stage / prod) | **Missing** | Not modelled. |
| Agent definition | Partial — `agent_id` from env. No first-class agent registry. |
| Agent instance | **Missing** | No instance vs. definition distinction. |
| Workflow | **Missing** | Not modelled. |
| Workflow run | **Missing** | Not modelled. |
| Task | **Missing** | Not modelled. |
| Parent agent / parent request | Partial — `AgentSession.parent_session_id` field exists at `src/chuzom/agents/session.py`, schema column present. Routing path does **not** consume it. |
| Human initiator | **Missing** | No initiator field. |
| Service account | **Missing** | Same. |
| Tool call | Partial — request_id binds via contextvar; tool-call ids from LiteLLM are not propagated. |

**Survival of attribution across:**

- **Retries.** Same `correlation_id` is reused (good). Attribution survives.
- **Fallbacks.** Same `correlation_id` reused. Attribution survives.
- **Queueing.** No queueing layer in chuzom.
- **Async execution.** structlog contextvars are task-local; nested asyncio tasks inherit via `copy_context`. **Identity survives** in-process async.
- **Process restarts.** Attribution dies with the process. No durable workflow id.
- **Distributed workers.** No protocol for carrying identity across worker boundaries. Each chuzom process resolves its own identity from env.
- **Nested agent calls.** No parent-child linkage in routing.
- **Cross-service calls.** No identity propagation protocol.

**Result.** **Identity is single-process, single-org, single-tenant.** Outside that envelope, attribution is on a best-effort basis enforced by environment variables.

---

## 2. Budget enforcement

| Budget scope | Supported? | Evidence |
|---|---|---|
| Per organisation | ⚠️ Global `chuzom_monthly_budget` is the closest analog. |
| Per tenant | ❌ |
| Per team | ❌ |
| Per project | ❌ |
| Per user | ❌ |
| Per agent (definition) | ⚠️ `AgentSession.budget_cap_usd` is per-session-instance, not per-definition. |
| Per workflow | ❌ |
| Per workflow run | ⚠️ Same `AgentSession` if a workflow run = a session. |
| Per task | ❌ |
| Per environment | ❌ |
| Daily / weekly / monthly | ⚠️ Monthly only. |
| Hard / soft limits | ⚠️ Hard via `BudgetExceededError`. Soft at 90% warning. |
| Forecasting | ❌ |
| Reservations | ⚠️ `_pending_spend` is in-process only. |
| Atomic consumption | ⚠️ `asyncio.Lock` per-process. Multi-process: races. |
| Distributed enforcement | ❌ |
| Emergency shutdown | ❌ |
| Approval for budget increases | ❌ |

### Concurrency edge cases that today's code does **not** handle

1. **Multi-process race.** Two chuzom processes both read `monthly_spend` from `usage.db`, both reserve, both call provider. Aggregate spend ≈ 2× budget.
2. **Retry double-count.** A streaming partial-failure may bill twice on the provider while chuzom counts once (or vice versa); chuzom-side accounting is settled on successful return.
3. **Nested-agent escape.** A child agent's budget cap is its own `AgentSession.budget_cap_usd`; the parent's remaining budget is not decremented when the child opens. A workflow with 10 children of $5 each can burn $50 even if the parent was meant to spend $10.
4. **Tool-triggered re-entry.** A tool call that itself opens a new chuzom MCP session does not inherit any budget context.

---

## 3. Runaway-agent protection

| Guard | State | Notes |
|---|---|---|
| Maximum calls per task | ❌ | Not enforced. |
| Maximum iterations | ❌ | Not enforced. |
| Maximum tokens per turn | ⚠️ | `max_tokens` is a per-call parameter; no aggregate. |
| Maximum cost per task | ⚠️ | Only via session budget. |
| Maximum wall-clock duration | ❌ | No deadline. |
| Maximum parallelism | ❌ | Not constrained. |
| Maximum recursion depth | Partial | Inspection by sibling agent found a nested-depth guard around 2-3 levels; not configurable per workflow. |
| Maximum retries | ⚠️ | Per provider chain length; not per task. |
| Maximum fallback attempts | ⚠️ | Same as above. |
| Cancellation propagation | ❌ | No `asyncio.CancelledError` handling in `route_and_call`. |
| Deadline propagation | ❌ | No deadline passed to children. |
| Parent–child budget propagation | ❌ | See §2 (3). |
| Circuit breakers (provider) | ✅ | `health.py::HealthTracker`. |
| Circuit breakers (agent) | ❌ | No per-agent breaker. |
| Emergency workflow termination | ❌ | No kill switch. |

**Failure modes that today's code cannot detect or stop:**

- Infinite tool-call loops
- Recursive delegation explosions
- Retry storms across providers
- Token amplification (long context that grows on each turn)
- Multi-agent feedback loops
- Duplicate side effects after timeout
- Agents bypassing the router by holding provider keys directly

---

## 4. Agent-specific routing

A routing strategy suitable for interactive chat is **not** safe for autonomous agents. Today's router uses the same complexity-based chain for both. Specific risks:

1. **Tool-call accuracy.** Routing to a cheaper model can degrade tool-call validity. No tool-call-accuracy score informs the chain.
2. **Structured-output reliability.** Same.
3. **Determinism.** No "stickiness" — the same agent may oscillate between models across calls in one workflow.
4. **Latency budgets per task.** Not modelled. Long-running tasks may interleave with latency-sensitive ones.
5. **Risk of side effects.** No risk classification → no policy that says "high-side-effect actions need premium model + human approval".

---

## 5. Cost per outcome

Per `COST_SAVINGS_VALIDATION.md` §1.3: chuzom measures cost per call. It does **not** measure:

- Cost per successful task
- Cost per completed workflow
- Cost per accepted output
- Cost per production action

For an agent platform, cost-per-call is the **wrong** unit. A cheaper-per-call routing strategy that increases total agent steps may *raise* cost-per-outcome. There is no way to measure this with the current schemas.

---

## 6. Operational visibility

Questions a central agent-platform operations team would need to answer:

| Question | Answerable today? |
|---|---|
| Which agents are currently active? | ❌ |
| Which workflows are consuming the most money? | ❌ (no workflow id) |
| Which agents are stuck? | ❌ (no liveness signal) |
| Which agents are retrying? | ❌ |
| Which workflows are close to budget exhaustion? | ❌ |
| Which models are producing the most failures? | ⚠️ Per-provider error counts in `HealthTracker`; not joined to agent identity. |
| Which routing rules are increasing total workflow cost? | ❌ |
| Which providers are degrading? | ⚠️ Local circuit-breaker only. |
| Which agents are generating anomalous traffic? | ❌ |
| Which tasks produced duplicate calls? | ❌ |
| Which workflow created a specific provider charge? | ⚠️ Per request_id from logs; not reconciled. |
| Why was a specific model selected? | ⚠️ classifier_method + routing_hints in logs. |
| Why was a request retried? | ⚠️ LiteLLM error in logs. |
| Why did a workflow exceed its budget? | ❌ |
| Stop a workflow immediately? | ❌ |
| Disable a model without redeploy? | ❌ |

---

## 7. Retry / duplicate-action safety

- **Idempotency keys.** Not generated by chuzom. A retried call to a non-idempotent tool may execute the side effect twice.
- **Partial tool calls** (provider returns partial streamed tool call) — handled by LiteLLM at best-effort; chuzom does not add a deduplication layer.
- **Provider-charged-but-failed.** Reconciliation is on the provider invoice side; chuzom-side cost is recorded only on success.

---

## 8. Cancellation and deadline

- `asyncio.CancelledError` not caught / cleaned up in `route_and_call`. A cancelled parent agent may still bill for the in-flight provider call.
- No deadline parameter on the routing API.
- No timeout supervisor at the workflow level.

---

## 9. Production-readiness verdict

The audit charter requires that the agentic-platform standard be **higher** than the developer standard. Against that standard:

| Domain | Required | State |
|---|---|---|
| Identity & lineage | Hierarchical, durable, parent-child, across processes | Single-process, env-trusted |
| Budget enforcement | Atomic, hierarchical, distributed | Per-process, provider-keyed, no hierarchy |
| Runaway protection | Iterations, recursion, wall-clock, cost-per-task, cancellation | None or partial |
| Routing safety for agents | Tool-call-accuracy-aware, deterministic, side-effect-risk-aware | Same as developer routing |
| Retry safety | Idempotency, deduplication | Not provided |
| Tool-call safety | Identity-bound tool gating; allow/deny per tenant | Not provided |
| Cancellation | Propagated end-to-end | Not handled |
| Operational controls | Pause / kill / inspect agent + workflow | Not provided |

**Verdict (using the audit's four-level scale):**

| Level | Match? |
|---|---|
| Ready for production autonomous agents | ❌ |
| Ready for limited low-risk agents | ⚠️ Only with substantial wrapper engineering by the platform team |
| Ready only for experimentation | ✅ |
| Not ready | (close to this; experimentation works because most failure modes can be tolerated in a lab) |

**Specific scenarios where chuzom on `main` today should NOT be used:**

- Any agent with the authority to spend more than $50 / hour autonomously.
- Any agent with non-reversible side effects (production deploys, customer messages, transactions).
- Any multi-tenant agent platform.
- Any workflow with > 3 levels of nesting.
- Any workflow expected to run > 30 minutes.

**Specific scenarios where experimental use is OK:**

- Internal research / scoring agents with no production side effects.
- Single-tenant developer-driven agents with explicit per-developer budget caps.
- Stateless code-review / documentation agents that produce text outputs only.
