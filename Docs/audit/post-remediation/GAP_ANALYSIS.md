# Gap Analysis

Each gap below carries a single ID. The IDs are new — prefixed `G-` to distinguish from the original FINDINGS file. Where a gap maps directly to an original finding, the original ID is cited.

## Legend

- **Affected use case**: D = developer rollout, C = central governance, A = agentic platform, F = financial reporting.
- **Severity**: Critical (rollout-blocking), High (rollout-degrading), Medium (acceptable for pilot only), Low (track).
- **Rollout blocker status**: Yes / No per use case.

---

### G-001 · RBAC is not enforced in the routing path

| Field | Value |
|---|---|
| Origin | INV-010 (partial close) |
| Affected | C, A |
| Severity | Critical |
| Evidence | `grep -n "has_permission\|check_permission\|Permission\.ROUTE_PROMPT" src/chuzom/router.py` → no matches. |
| Root cause | RBAC scaffolding (`src/chuzom/enterprise/rbac.py`) exists; never wired. |
| Residual risk | Any process with env access can route as any identity. |
| Required remediation | Add `identity.has(Permission.ROUTE_PROMPT)` check at the top of `route_and_call`; per-model and per-provider permission checks before chain walk. |
| Acceptance criteria | (a) Missing `Permission.ROUTE_PROMPT` returns `PermissionDenied` before any provider call. (b) Per-provider deny audit row written. (c) Test fires under both single-process and (mock) distributed mode. |
| Tests required | `test_rbac_route_prompt_required`, `test_rbac_provider_deny`, `test_rbac_audit_row_on_deny`. |
| Rollout blocker | **Yes** for C; **Yes** for A. |

### G-002 · Budgets are not per-identity

| Field | Value |
|---|---|
| Origin | INV-011 (unchanged) |
| Affected | D, C, A, F |
| Severity | Critical |
| Evidence | `src/chuzom/budget.py::reserve_tokens(provider, tokens)` keyed on provider; `router.py:1447` checks global monthly budget only. |
| Root cause | Budget scope is provider, not principal. |
| Required remediation | Persist budgets per `(tenant_id, team_id, user_id, agent_id, scope)`; atomic check-then-charge under contention. |
| Acceptance criteria | 100 concurrent calls against a budget of N exactly N succeed, 100−N raise `QuotaExceeded` **before** any provider call. |
| Tests required | `test_budget_concurrency_per_identity` (TST-003). |
| Rollout blocker | **Yes** for C, A. Pilot-blocking for D under shared budget. |

### G-003 · No tenant axis anywhere

| Field | Value |
|---|---|
| Origin | Q-P-2 (unresolved) |
| Affected | C, A |
| Severity | Critical |
| Evidence | `tenant_id` absent from `TurnIdentity`, audit detail, log contextvars, budget schema, routing tables. |
| Root cause | Multi-tenancy product decision deferred. |
| Required remediation | Make the Q-P-2 decision; thread `tenant_id` through identity, audit row, log contextvars, budgets, routing. |
| Acceptance criteria | Cross-tenant write paths refused; audit chain verifiable per tenant; budgets scoped per tenant. |
| Rollout blocker | **Yes** for C, A. |

### G-004 · No central control plane

| Field | Value |
|---|---|
| Origin | New (post-remediation) |
| Affected | C |
| Severity | Critical |
| Evidence | See `CENTRAL_CONTROL_PLANE_ASSESSMENT.md` capability table — no row is fully met. |
| Required remediation | Control-plane service + admin API + policy-as-versioned-object + push/pull protocol to chuzom instances. |
| Acceptance criteria | (a) A policy change in the control plane reaches all instances within a defined SLO. (b) Effective policy at any instance is auditable. |
| Rollout blocker | **Yes** for C. |

### G-005 · No SSO / SCIM / OIDC

| Field | Value |
|---|---|
| Origin | New |
| Affected | C, D (mandatory) |
| Severity | Critical |
| Evidence | `grep -rln SSO\|SAML\|OIDC\|SCIM src/chuzom/` returns no application-code match. |
| Required remediation | OIDC integration; SCIM user-sync; service-account token issuance via IdP. |
| Rollout blocker | **Yes** for mandatory developer use; **Yes** for C. |

### G-006 · No cost reconciliation against provider invoices

| Field | Value |
|---|---|
| Origin | New |
| Affected | F |
| Severity | Critical |
| Evidence | `grep -rn "invoice\|reconcile_provider" src/chuzom/` → no matches. |
| Required remediation | Monthly job that ingests provider invoices and produces a variance report against logged `cost_usd`. |
| Acceptance criteria | Variance within defined tolerance (suggested ≤ 2% aggregate, ≤ 10% per user-month). |
| Rollout blocker | **Yes** for any mandatory or Finance-visible deployment. |

### G-007 · No cancellation / deadline propagation

| Field | Value |
|---|---|
| Origin | New |
| Affected | A, D (long sessions) |
| Severity | High |
| Evidence | `grep -n "CancelledError\|asyncio.timeout\|asyncio.wait_for" src/chuzom/router.py` → no matches. |
| Required remediation | Wrap `route_and_call` body in a cancel-aware shield; propagate workflow-level deadlines into provider clients; abort in-flight calls on parent cancel. |
| Acceptance criteria | Killing a parent task within N ms aborts the running provider call within N+T ms; no further billing accrues. |
| Rollout blocker | **Yes** for A. |

### G-008 · No runaway-agent guards (iterations / recursion / wall-clock / cost-per-task)

| Field | Value |
|---|---|
| Origin | New |
| Affected | A |
| Severity | Critical |
| Required remediation | Configurable per-workflow `max_iterations`, `max_recursion_depth`, `max_wall_clock_seconds`, `max_cost_per_task`. |
| Acceptance criteria | Synthetic loop test: an agent that returns "step me again" forever halts within configured bounds. |
| Rollout blocker | **Yes** for A. |

### G-009 · No parent-child budget propagation

| Field | Value |
|---|---|
| Origin | New |
| Affected | A |
| Severity | Critical |
| Evidence | `AgentSession.parent_session_id` field exists; routing path does not decrement parent budget on child spend. |
| Required remediation | Parent budget envelope passed to child; atomic decrement of parent on every child charge; child denied when parent budget exhausted. |
| Rollout blocker | **Yes** for A. |

### G-010 · No distributed-safe audit log

| Field | Value |
|---|---|
| Origin | New |
| Affected | C, A |
| Severity | High |
| Evidence | `enterprise/audit.py:160` opens default sqlite3 connection; per-process AuditLog singleton in `audit_routing.py`. Multi-process write coordination unspecified. |
| Required remediation | Decide architecture: per-tenant single-writer + reconciliation, or central event stream (Kafka / NATS) + replicated log. |
| Acceptance criteria | Concurrent multi-process write test produces a chain that `verify_chain` accepts. |
| Rollout blocker | **Yes** for C, A. |

### G-011 · `chuzom://status` MCP resource leaks provider configuration

| Field | Value |
|---|---|
| Origin | SEC-004 (unchanged) |
| Affected | D, C |
| Severity | Medium |
| Evidence | `src/chuzom/server.py::router_status` returns Profile/Tier/Providers/Text/Media + per-provider health to any MCP client that can read the resource; no identity check. |
| Required remediation | Identity-gate the resource; redact provider list when caller lacks `Permission.READ_CONFIG`. |
| Rollout blocker | No (informational), but should be closed before mandatory rollout. |

### G-012 · No no-retention / ZDR provider mode

| Field | Value |
|---|---|
| Origin | PRI-003 (unchanged) |
| Affected | D (sensitive workloads), C |
| Severity | High |
| Required remediation | Per-classification routing that picks ZDR-eligible providers; mark logs accordingly. |
| Rollout blocker | **Yes** for regulated workloads. |

### G-013 · Redaction module is unwired

| Field | Value |
|---|---|
| Origin | PRI-001 (unchanged) |
| Affected | D, C |
| Severity | High |
| Evidence | `grep "redact_prompt" src/chuzom/router.py` → no matches. |
| Required remediation | Pre-route redaction step gated by data classification + policy. |
| Rollout blocker | **Yes** for sensitive workloads. |

### G-014 · Semantic cache stores prompt fragments

| Field | Value |
|---|---|
| Origin | PRI-002 (unchanged) |
| Affected | D, C |
| Severity | Medium |
| Required remediation | Per-tenant cache isolation; opt-out per classification. |
| Rollout blocker | **Yes** for regulated workloads. |

### G-015 · Two parallel `AuditEvent` classes

| Field | Value |
|---|---|
| Origin | INV-012 (unchanged) |
| Severity | Medium |
| Required remediation | Pick one (the `enterprise/audit.py` chain-aware variant); migrate `storage/` consumers. |
| Rollout blocker | No (architectural debt). |

### G-016 · `_dynamic_routing_table` module-global

| Field | Value |
|---|---|
| Origin | ROU-002 (unchanged) |
| Affected | C, A |
| Severity | High |
| Required remediation | Per-tenant routing state; or stateless rebuild per call (perf?). |
| Rollout blocker | **Yes** for multi-tenant. |

### G-017 · No deployment artefacts for shared infrastructure

| Field | Value |
|---|---|
| Origin | New |
| Affected | C, A |
| Severity | High |
| Evidence | No `Dockerfile`, no Helm chart, no K8s manifests. |
| Required remediation | Container image; Helm chart; example multi-instance topology. |
| Rollout blocker | **Yes** for C, A. |

### G-018 · No operator runbook

| Field | Value |
|---|---|
| Origin | New |
| Severity | Critical (mandatory rollout-blocking) |
| Required remediation | Runbook covering: install, upgrade, rollback, secret rotation, model retirement, debug-a-routing, export-audit, reconcile-cost, emergency kill, incident response. |
| Rollout blocker | **Yes** for mandatory rollout. |

### G-019 · `Docs/` remains gitignored

| Field | Value |
|---|---|
| Origin | INV-013 |
| Severity | Low (but persistent) |
| Required remediation | Move audit corpus to a non-gitignored path. This new audit set is at `docs/audit/post-remediation/` (lowercase) — verify behaviour on case-sensitive filesystems and commit deliberately. |
| Rollout blocker | No (governance-hygiene). |

### G-020 · No load / concurrency test for `route_and_call`

| Field | Value |
|---|---|
| Origin | TST-003 + new |
| Affected | A |
| Severity | High |
| Evidence | `grep -r "asyncio.gather" tests/` → small fan-outs (≤ 100) on caches, no real-routing fan-out. |
| Required remediation | Synthetic load suite at 500+ concurrent routed calls. |
| Rollout blocker | **Yes** for A. |

---

## Summary table

| Gap | Severity | Blocks D | Blocks C | Blocks A | Blocks F |
|---|---|---|---|---|---|
| G-001 RBAC | Critical | — | Yes | Yes | — |
| G-002 Budgets per identity | Critical | (pilot) | Yes | Yes | Yes |
| G-003 No tenant | Critical | — | Yes | Yes | — |
| G-004 No control plane | Critical | — | Yes | — | — |
| G-005 No SSO | Critical | (mandatory) | Yes | — | — |
| G-006 No invoice reconciliation | Critical | (mandatory) | (mandatory) | (mandatory) | Yes |
| G-007 No cancellation | High | — | — | Yes | — |
| G-008 No runaway guards | Critical | — | — | Yes | — |
| G-009 No parent-child budget | Critical | — | — | Yes | — |
| G-010 No distributed audit | High | — | Yes | Yes | — |
| G-011 chuzom://status leak | Medium | (mandatory) | (mandatory) | — | — |
| G-012 No ZDR | High | (sensitive) | (regulated) | (regulated) | — |
| G-013 Redaction unwired | High | (sensitive) | (regulated) | (regulated) | — |
| G-014 Semantic cache | Medium | (regulated) | (regulated) | — | — |
| G-015 Parallel AuditEvent | Medium | — | — | — | — |
| G-016 Module-global routing | High | — | Yes | Yes | — |
| G-017 No deploy artefacts | High | — | Yes | Yes | — |
| G-018 No operator runbook | Critical | (mandatory) | (mandatory) | Yes | — |
| G-019 Docs/ gitignored | Low | — | — | — | — |
| G-020 No concurrency test | High | — | — | Yes | — |

**Critical-severity gaps that block at least one rollout: 9.**
