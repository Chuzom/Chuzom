# Post-Remediation Acceptance Verdict

**Subject:** chuzom @ `main` after the 2026-06-08 remediation cycle (v0.2.0 + Tier 1 + Tier 2 identity wiring)
**Scope:** Enterprise developer rollout + central governance + agentic-platform use
**Audit mode:** Read-only verification against current source. Documentation claims explicitly do not count as evidence.

---

## TL;DR

**Direct recommendation for developer rollout:** **Controlled pilot only.** Not for broad rollout. Not mandatory.

**Direct recommendation for mandatory usage:** **No.** Mandatory usage requires central governance that does not yet exist.

**Direct recommendation for central governance:** **No.** What exists is shared configuration plus a single-process audit log, not a control plane.

**Direct recommendation for agent-platform usage:** **No.** Use for low-risk experimentation only. Not safe for production autonomous workloads, certainly not for hundreds-to-thousands of concurrent agents.

**Cost-saving verdict:** **Plausible but unverified.** Gross-savings instrumentation exists; net-savings (counterfactual, reconciliation against provider invoices, cost-per-outcome) does not.

---

## The five strongest capabilities (real, verified)

1. **Hook-based, host-agnostic routing.** 14 host integrations (Claude Code, Cursor, Codex CLI, Gemini CLI, etc.) work via the auto-route hook + MCP stdio. Routing chain walk + Retry-After + emergency fallback is genuinely implemented (`router.py:1284` route_and_call; `health.py` HealthTracker singleton).

2. **Critical-finding security cluster closed.** SEC-001 (chuzom-sse removed), SEC-002 (fs sandbox + opt-in), SEC-003 (agoragentic opt-in), INV-007/ROU-001 (per-session classification shards) are all verified in code with regression tests. `pyproject.toml:78`, `src/chuzom/tools/fs.py:32-56`, `src/chuzom/tools/agoragentic.py:29-32`, `src/chuzom/hooks/auto-route.py:2622`.

3. **Identity attribution per turn (Tier 1+2).** `route_and_call` resolves a `TurnIdentity` (`src/chuzom/identity.py:38-77`) and writes one tamper-evident audit row (`src/chuzom/audit_routing.py`) per successful routed turn. `verify_chain()` exists and passes a 1000-decision stress test (`tests/test_tier1_audit_per_turn.py`). `request_id` / `user_id` / `org_id` / `agent_id` bind into structlog contextvars at `router.py:1378-1386`.

4. **Honest test signal restored.** `tests/conftest.py:36` carries `collect_ignore: list[str] = []`. The 9 previously-hidden suites (206 tests) are collected and ~470 pass against the lineage subsystem and scenarios after the v0.2.x lineage API rewrite.

5. **Truth-in-claims aligned with code.** README hero matches `pyproject.toml: Development Status :: 3 - Alpha`. Prior self-audits (AUDIT_FINDINGS.txt + CHUZOM_AUDIT_REPORT.md) are rescoped to "lineage subsystem only".

## The ten most serious remaining gaps

1. **RBAC is not enforced at the routing chokepoint.** `grep -n "has_permission\|check_permission\|Permission\.ROUTE_PROMPT" src/chuzom/router.py` returns **zero** matches. `src/chuzom/enterprise/rbac.py` exists (file present) but nothing in the routing path consults it. INV-010 is **partially**, not fully, accepted.

2. **Budgets are still provider-keyed, not identity-keyed.** `src/chuzom/budget.py::reserve_tokens(provider, tokens)` and `_pending_tokens[provider]` (budget.py) — `router.py:1447` checks `config.chuzom_monthly_budget` against `cost.get_monthly_spend()` globally. INV-011 unaddressed.

3. **No tenant axis anywhere.** `tenant_id` does not appear in `TurnIdentity`, in the audit row, in log contextvars, in budgets, or in routing tables. Multi-tenancy is parked behind `Q-P-2` in `Docs/audit/OPEN_QUESTIONS.md` and has not been decided.

4. **Cost reconciliation against provider invoices: none.** `grep -rn "invoice\|reconcile_provider\|provider_billing" src/chuzom/` returns zero matches. Logged cost numbers cannot be reconciled with what providers actually charge.

5. **No counterfactual ("what would we have spent") tooling for the org level.** `tools/dashboard.py:162,205` carries a per-call `baseline_cost`, but there is no organisation-level cumulative counterfactual report and no comparison against direct-provider usage.

6. **Single-process audit log.** `src/chuzom/enterprise/audit.py:160` opens a single SQLite via `sqlite3.connect()`; no WAL mode set, no distributed-write coordination. Multi-process load on the same `audit.db` will serialise via SQLite file lock at best, race at worst. Inadequate for an enterprise agentic platform.

7. **No cancellation / deadline propagation.** `grep -n "CancelledError\|asyncio.timeout\|asyncio.wait_for" src/chuzom/router.py` returns zero. Killing a parent agent does NOT abort in-flight provider calls. Cost continues to accrue past cancellation.

8. **No runaway-agent guards beyond a per-session $5 cap.** No `max_iterations`, `max_recursion_depth`, `max_wall_clock`, no parent-child budget propagation. An agent loop making 5,000 1-cent calls hits no guard rail until the session-level budget is exhausted.

9. **No central control plane.** No admin API, no policy versioning/rollout/rollback, no SSO/SCIM/OIDC (`grep -rln SSO|SAML|OIDC|SCIM src/chuzom/` returns zero match in app code). Configuration is per-instance `.env` plus `~/.chuzom/profile.yaml`. Per-team / per-project policies do not exist as a first-class object.

10. **No deployment artefacts for shared infrastructure.** No `Dockerfile`, no Helm chart, no K8s manifests, no Terraform, no air-gapped story. The shipping unit is `pip install chuzom-router` — fine for a dev workstation, inadequate for hosted shared infrastructure.

---

## Conditions required for approval

These are the **minimum** conditions to flip each of the three rollout questions from "no" to "yes". Each must be met by code + test + operational evidence, not by documentation.

### To approve **developer rollout** (move from "controlled pilot" to "broad / mandatory"):

- [ ] **Net-savings reconciliation pipeline** — automated comparison of logged cost against the most recent provider invoice, with tolerance and variance reporting. Pre-condition for `mandatory`, since mandatory use removes the developer's "I'll just go around it" option.
- [ ] **Quality regression measurement** — controlled comparison (direct provider vs. routed) on a representative developer task corpus, with a statistical bound on completion / latency / token differences.
- [ ] **Central enforcement against bypass** — a deployment mode in which a developer cannot reach the provider directly using their own keys. Today the keys live in the user's env; bypass is trivial.
- [ ] **Operational runbook** owned by the platform team, including: install, upgrade, rollback, secret rotation, model/provider retirement, debugging a routing decision, exporting audit data, and reconciling cost with Finance.

### To approve **central governance**:

- [ ] **Real control plane**, not configuration files: per-team / per-project / per-user policies as first-class versioned objects with rollout, preview, rollback, approval, audit.
- [ ] **Runtime enforcement** of allow/deny lists for providers and models, observable from the same control plane that defines them. Bypass via custom model names or alternate provider endpoints must be rejected server-side.
- [ ] **SSO/SCIM/OIDC integration** for principal identity. The current `CHUZOM_USER_ID` env-var trust model is incompatible with the "company credentials hidden from users" requirement.
- [ ] **Distributed-safe audit log** — write coordination across multiple chuzom instances, or a chosen single-writer architecture with documented failure semantics.

### To approve **agent-platform usage**:

- [ ] **Parent-child budget propagation** — a child agent's spend must decrement the parent's budget atomically; concurrent siblings against a shared budget must race correctly.
- [ ] **Runaway guards** — `max_iterations`, `max_recursion_depth`, `max_wall_clock`, `max_cost_per_task`, with cancellation propagation through `asyncio.CancelledError`.
- [ ] **Emergency kill switch** — a control-plane action that disables a model / provider / agent / workflow without a process restart, propagated to running tasks.
- [ ] **Load + concurrency tests** — at least one suite that runs hundreds of concurrent `route_and_call` invocations against a budget and shows correct enforcement under contention. TST-003 must be addressed.
- [ ] **Cost-per-outcome reporting** — the platform must report cost per successful workflow, not cost per call, so the cost-routing strategy can be evaluated against quality.

---

## Conditions that should cause rejection

Any of the following, if observed in pre-rollout validation, should reject Chuzom for the relevant deployment:

- A budget can be exceeded by ≥10% under 100-way concurrency on a single instance.
- Two chuzom instances configured against the same `audit.db` produce a `verify_chain` failure.
- A developer can reach `openai.com` (or any other configured provider) from their workstation using the company credentials, bypassing the router.
- A routing strategy reduces gross cost but increases tokens-per-successful-task by more than the cost saving on a representative corpus.
- A runaway agent (deliberately fanning out for >5 minutes) is not stopped by any in-product guard.
- A provider invoice for a known billing period diverges from logged cost by more than a defined tolerance (suggested: 2% on aggregate, 10% on any single user).
- A configuration change (e.g. retiring a model) requires a process restart on every instance instead of a control-plane action that propagates.

---

## Confidence

- **Verification of code state**: high. Citations are grepped from `main` at audit time.
- **Acceptance against original audit acceptance criteria** (e.g. INV-010 acceptance: "every routed turn writes one AuditEvent, verify_chain passes after 1000 decisions"): **directly confirmed via `tests/test_tier1_audit_per_turn.py`**.
- **RBAC / multi-tenancy / runaway guards**: **directly confirmed absent** via grep.
- **Reconciliation, deployment artefacts, SSO**: **directly confirmed absent** via grep + file-system listing.
- **Routing quality** (does the cheap-model strategy preserve developer productivity?): **not validated**. No controlled comparison exists. This is the audit's largest unresolved evidence gap.

---

## Bottom line

The 2026-06-08 remediation cycle moved chuzom from "experimental developer tool with shelved enterprise scaffolding" (audit score 1.65 / 5) to "developer tool with provable security hygiene + per-turn identity attribution and a tamper-evident audit row, with most enterprise gaps unchanged." The change is real and worth shipping.

It does **not** move chuzom into a state where putting it between every developer in the company and the provider, or onto an enterprise agentic platform, is responsible. The remaining gaps are not configuration polish; they are missing systems (control plane, multi-tenancy, reconciliation, runaway protection). Those will not be closed by another six-PR cycle; they require explicit product decisions — starting with the Q-P-2 multi-tenancy model — and a roadmap of meaningful engineering.

**Recommendation for the next step:** a controlled developer pilot (per `PILOT_PLAN.md`) on a non-mandatory basis, in parallel with a Phase-3 engineering effort that closes the 10 gaps above. Do not adopt for the agent platform until the agent-pilot gates in `AGENT_PILOT_PLAN.md` are explicitly green.
