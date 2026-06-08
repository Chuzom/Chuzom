# Q-P-2 Decision Record: Multi-tenancy Model for Phase-3 Engineering

**Status:** **Decided** · 2026-06-08
**Decision:** **Hybrid A → B path** — Single-org-per-instance now (Phase 3a); add Sidecar-per-tenant as a deployment topology in Phase 3b; defer the full multi-tenant-within-process decision to Phase 4 based on actual hosted-SaaS demand.
**Owner of the decision:** chuzom product / tech lead (recorded by the post-remediation audit).

---

## Why this record exists

`Q-P-2` was the highest-leverage open product question in `Docs/audit/OPEN_QUESTIONS.md`. It blocked ~60% of the Critical / Medium queue in `docs/audit/post-remediation/GAP_ANALYSIS.md` and was the implicit prerequisite for the score-to-4 path in `docs/audit/post-remediation/EXECUTIVE_DECISION_MEMO.md`. The audit charter required this kind of question be answered explicitly and recorded so future engineers don't re-litigate it without context.

## The three options considered

| Dimension | A: Single-org-per-instance | B: Sidecar-per-tenant | C: Multi-tenant-within-process |
|---|---|---|---|
| Process model | 1 chuzom = 1 org | 1 chuzom = 1 tenant; ops run N processes | 1 chuzom = N tenants |
| Identity primitive | `user_id` (env) | `user_id` + implicit `tenant_id` (process) | `(tenant_id, user_id)` per call |
| Engineering effort | S–M | M | XL |
| Operational effort | S | L (N processes to manage) | M (one stack; control plane does the work) |
| Time-to-pilot | weeks | weeks | quarters |
| Time-to-GA | quarter | 2 quarters | 3+ quarters |

## The chosen path

### Phase 3a — Single-org-per-instance (Q1 / next ~13 weeks)

- `tenant_id` = `org_id` for now; remains implicit at the process level.
- Identity-layer Track-1 work shrinks because there is nothing to multiplex.
- Most of the score-to-4 work in Tracks 1, 2, 4 lands cleanly under A:
  - G-001 RBAC enforced at the routing chokepoint (no tenant dimension required).
  - G-002 per-identity atomic budgets (per user/team/agent within the single org).
  - G-006 cost-reconciliation pipeline against a single org's invoices.
  - Partial G-010 (audit log is single-writer per instance).

### Phase 3b — Sidecar-per-tenant as a deployment topology (Q2 / weeks 14–26)

- chuzom stays single-org per process. The control plane (T5-XL1) becomes a **tenant-aware manager** that operates N chuzom sidecars.
- Budgets / audit / RBAC remain per-process; tenancy is a deployment-and-ops concern, not a code-level one.
- Most engineering complexity moves to orchestration (Helm chart, control-plane reconciliation), not into chuzom itself.
- Closes G-003 (tenant axis) in the **operational** vocabulary — the *control plane* knows which sidecar serves which tenant, even though each sidecar code-path remains option A internally.

### Phase 4 — Decide on full multi-tenant-within-process (Q3+)

- If real hosted-SaaS demand materialises by Q3, evaluate the deeper rewrite to option C.
- If demand does not materialise, sidecar-per-tenant + control plane is sufficient.
- The decision is gated by **data**, not speculation.

## Why this path over the alternatives

| Alternative | Why not chosen |
|---|---|
| **A only** | Locks out hosted-SaaS without a future rewrite. The user has not ruled out SaaS, so the hybrid keeps options open at zero immediate cost. |
| **C up front** | XL engineering bill (~6 FTE × 4 quarters per the executive memo's Track-B estimate). Doubles down on a market that has not been validated. Forces every Phase-3 track to be re-scoped against multi-tenant shape from day 1, slowing the score-to-4 path. |
| **Defer the decision** | Keeps ~60% of the Critical / Medium queue parked indefinitely. The score-to-4 trajectory stalls. Defers a decision that has a clear default given current constraints. |

## Engineering consequences

The Critical / Medium queue items now unblock as follows:

| Task | Reframe under A→B path |
|---|---|
| **T1-M1** `tenant_id` in TurnIdentity | Single-org per instance: keep `tenant_id` as a typed-but-implicit field that equals `org_id`. The code carries it for forward-compat without forcing every caller to populate it. |
| **T1-M2 / M3** RBAC at routing entry | Lands fully under A: per-user / per-team / per-provider / per-model permission checks; one org's policy. |
| **T2-M1** BudgetKey | `BudgetKey = (org_id, team_id, user_id, agent_id, scope)` — no tenant axis needed at the key level for now. |
| **T2-XL1** Distributed audit | Phase 3a: per-instance SQLite single-writer (acceptable for A). Phase 3b: per-tenant single-writer + nightly reconciliation across sidecars. |
| **T5-XL1** Control plane | Phase 3b's scope: manage N sidecars + per-sidecar policy + cross-sidecar cost rollup. Smaller than full multi-tenant control plane. |
| **G-003 tenant axis** | Implicit in Phase 3a (one tenant per process); explicit in Phase 3b at the **operational** layer (control plane); only requires code-level work if Phase 4 chooses C. |
| **G-004 control plane** | Phase 3b scope, not Phase 3a. Reduces Q1 surface area significantly. |
| **G-005 SSO / SCIM / OIDC** | Required in Phase 3a — single-org SSO is simpler than multi-tenant SSO. |
| **G-010 distributed audit** | Phase 3a: in-process audit chain. Phase 3b: cross-sidecar reconciliation job. |

## Tasks affected on the master plan

The wave plan in this session's response moves accordingly:

- **Wave 1** (was: foundation): still ships under A, no re-scope.
- **Wave 2** (was: per-identity governance + privacy): drops the `tenant_id` plumbing from T1-M1; expands G-003 explanation in code comments.
- **Wave 3** (was: enterprise foundations): SSO scoped single-org; reconciliation single-org.
- **Wave 4** (was: multi-tenant + distributed + control plane + agent-aware routing): becomes "sidecar-per-tenant + control plane operates N sidecars" rather than multi-tenant-within-process.
- **Wave 5** (was: control plane finish): becomes Phase 4 / option C — only revisited if hosted-SaaS demand materialises.

## Acceptance criteria for this decision

- [x] One of A / B / C / Hybrid chosen explicitly.
- [x] Rationale recorded with citations to GAP_ANALYSIS and EXECUTIVE_DECISION_MEMO.
- [x] Engineering consequence per Critical / Medium task documented.
- [x] Wave plan updated to reflect the chosen path.
- [ ] `Docs/audit/OPEN_QUESTIONS.md` Q-P-2 entry updated to "Decided 2026-06-08 — see `Docs/audit/decisions/Q-P-2_multi-tenancy.md`" (follow-up, not blocking).

## What this record does not commit to

This record commits to **Phase 3a (A) immediately and Phase 3b (B) after**. It does **not** commit to ever shipping option C. The Phase 4 decision is explicit and data-driven; this record is intentionally open about that.

It also does not change the answers in `ACCEPTANCE_VERDICT.md`:

- Developer rollout: still **controlled pilot only** until Phase 3a closes the RBAC + reconciliation gates.
- Central governance: still **no** until Phase 3b ships the control plane.
- Agentic platform: still **experimentation only** until Track-3 agent-safety items land.
- Cost-saving claims: still **plausible but unverified** until the reconciliation pipeline (T4-L1) lands in Phase 3a.

The decision unblocks the path to "yes" on each of those without flipping any of the verdicts today.
