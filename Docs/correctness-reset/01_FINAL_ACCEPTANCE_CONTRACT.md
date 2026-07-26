# Chuzom Correctness Reset — 01. Final Executable Acceptance Contract

This contract is **executable**: every invariant names its owning component and the tests that prove
it. An invariant without a failing-before/passing-after test is **not** satisfied (working rule 13).
"Owning component" is where the invariant is enforced *after* the reset (Phase 2+), which may differ
from where the logic lives today (cited from `00_CURRENT_STATE.md`).

Legend for **Status**: `RED` = violated today (evidence in map); `GAP` = not currently provable
(no test/surface); `GREEN-TODAY` = already holds, must be regression-locked.

---

## Cost invariants

### INV-COST-001 — every billable attempt recorded exactly once
**Definition.** Every provider attempt that consumes billable tokens/quota is written to the canonical
execution ledger exactly once, as its own `attempt_id` event, for every outcome:
accepted · rejected(gate) · rejected(quality) · retry · escalation · emergency-fallback ·
timeout-with-known-usage · partial-with-known-usage.
**Owning component.** Canonical ledger writer (Phase 2) invoked from `router.py` `_dispatch_model_loop`.
**Status.** **RED.** Today rejected/escalated attempts (`router.py:2022,2074`) `continue` past
`cost.log_usage` (2085) and `session_spend.record` (2133); their cost reaches only the unread
`routing_quality.jsonl` (§5.1, §5.2 AC-1).
**Tests.** unit: ledger records N events for a chain of N attempts incl. rejects. integration:
`route_and_call` with 1 gate-reject + 1 accept → ledger has 2 attempt events, `usage`-equivalent
read-model has 2 rows. e2e: state-machine reject→escalate→accept reconciles.
**Failure behavior.** If usage for an attempt is unknown (timeout/partial), record the event with
`measured_cost_usd=null` and `terminal_state` set — never drop it, never fabricate a number.
**User consequence.** Dashboards stop undercounting spend on escalations.
**Closes.** AC-1 / audit P0-1.

### INV-COST-002 — route actual cost = Σ attempt costs
**Definition.** `route_actual_cost == sum(measured_cost_usd for all billable attempt events of the route)`.
**Owning component.** Aggregation layer `get_route_accounting(route_id)`.
**Status.** RED (follows from INV-COST-001). The honest total exists only at `router.py:2172`
(`_actual = _final_cost + _failed_attempt_cost`) and only in JSONL.
**Tests.** property (Hypothesis): for any generated chain, `get_route_accounting.actual == Σ attempts`.
**Failure behavior.** Aggregation raises/flags a reconciliation error if totals disagree; never silently coerces.
**Closes.** AC-1.

### INV-COST-003 — no attempt counted twice
**Definition.** Each `attempt_id` contributes to exactly one route total; re-aggregation is idempotent.
**Owning component.** Ledger (unique `attempt_id`) + aggregation.
**Status.** GAP (no dedup guarantee across the current split stores).
**Tests.** property: aggregating a ledger twice yields identical totals; duplicate `attempt_id` rejected.
**Failure behavior.** Duplicate event id → write rejected at ledger boundary.

### INV-COST-004 — one canonical actual-cost total
**Definition.** No user-facing spend surface may report an actual-cost total different from
`get_*_accounting()`.
**Owning component.** Aggregation layer; all surfaces delegate.
**Status.** RED. `session-end.py` (own stale prices, AC-3), `get_team_savings` (AC-2), and ~7 other
surfaces compute their own (§5.3).
**Tests.** integration per surface: surface total == aggregation total for the same window. A
"surface parity" test parametrized over every surface.
**Closes.** AC-2, AC-3, RC-1.

### INV-COST-005 — orchestration overhead measured or savings marked unknown
**Definition.** Hook/directive/orchestration token overhead is either measured and subtracted from
net token savings, or net savings is reported as `unknown` (never as an exact number that ignores it).
**Owning component.** Ledger event `directive_injected` (hook_input_tokens/hook_output_tokens) +
savings model.
**Status.** RED. Directive injection (`auto-route.py:3230-3271` ~446 tok; context-dep branch
~227 tok, §6.4) is unmeasured and absent from every savings figure.
**Tests.** unit: a turn with a hard directive records `hook_input_tokens>0`; net savings subtracts it.
integration: context-dependent turn (guaranteed no offload) shows overhead as cost, not savings.
**Closes.** audit A3 / §6.4.

### INV-COST-006 — subscription baseline avoidance is never labeled cash
**Definition.** Distinguish and label separately: (i) tokens/quota avoided, (ii) baseline-equivalent
cost avoided, (iii) real metered dollars avoided, (iv) net metered dollars saved. In subscription
mode, (iii)/(iv) are `$0.00` unless a genuinely-metered external provider cost was avoided.
**Owning component.** Savings model (Phase 3) + label constants shared by all surfaces.
**Status.** RED. `session-end.py`, `get_team_savings`, `llm_session_spend` show baseline-avoided as
"saved" without the metered gate (§5.2, §5.3). Only `admin.llm_savings` is honest today.
**Tests.** unit: in subscription mode every surface's "real $" == 0. integration: metered mode splits
correctly. Snapshot test on each surface's label vocabulary (INV-SAVE-005).
**Closes.** audit P0-2 / RC-1.

---

## Savings invariants

### INV-SAVE-001 — savings ≤ baseline − complete actual
**Definition.** Any reported savings ≤ `baseline_equivalent_cost − route_actual_cost` (complete actual
per INV-COST-002).
**Owning component.** Savings model.
**Status.** RED (because actual is undercounted, AC-1 makes savings exceed the true bound).
**Tests.** property: for all generated scenarios, `reported_savings <= baseline - complete_actual`.

### INV-SAVE-002 — net token savings subtracts measurable overhead
**Owning component.** Savings model. **Status.** RED (A3). **Tests.** property + the INV-COST-005 tests.

### INV-SAVE-003 — potential ≠ realized (separate metrics)
**Owning component.** Savings model. **Status.** GREEN-TODAY-ish (`potential_savings_usd` vs
`realized_savings_usd` exist, `session_spend.py:355-369`) but both are baseline-derived and mislabeled
(INV-COST-006). Must be regression-locked with correct semantics + labels.

### INV-SAVE-004 — realized only with evidence of use; else `unknown`
**Definition.** A routed result counts as *verified realized* only with evidence the host used it.
No-evidence → `unknown`, never assumed realized.
**Owning component.** Realization accounting fed by BOTH override detectors + a positive "result used" signal.
**Status.** RED. Realized savings prorates only by `mark_overridden` (tool-call path); the
`stop-enforce.py` plain-text override and the context-dependent branch never decrement it (§6.3) →
systematic overcount. There is no positive "used" signal at all (binary used/overridden assumption).
**Tests.** e2e: routed→Claude answers in plain text→`realized` decreases (currently would not).
unit: unknown-realization event is excluded from verified realized.
**Closes.** audit B7 / RC-3.

### INV-SAVE-005 — identical terminology across all surfaces
**Definition.** Every surface uses exactly: `Actual spend`, `Baseline-equivalent avoided`,
`Real metered dollars avoided`, `Potential savings`, `Verified realized savings`,
`Unknown realization`, `Routing overhead`. Unqualified `Saved: $X` is banned unless X is real metered dollars.
**Owning component.** Shared label module; enforced by a lint/test.
**Status.** RED. `team.py:104/142/179` emit `Saved: $X`; surfaces use ad-hoc labels (§5.3).
**Tests.** grep-style test asserting no banned label; snapshot of each surface's vocabulary.

---

## Routing & capability invariants

### INV-ROUTE-001 — classification never removes required capability
### INV-ROUTE-002 — a forced door supports every capability the request needs
### INV-ROUTE-003 — uncertain classification preserves completion (fail-open on capability, log uncertainty)
**Owning component.** Enforcement (`enforce-route.py`) + door capability matrix (Phase 4).
**Status.** RED. QA-classified prompt under smart/hard/strict, needing an unseen file, is forced through
the text-only `llm` door (no `files` param); Read/Grep/Glob are blocked; `llm_edit` (only file-capable
door) is undiscoverable and tier-gated off under `CHUZOM_SLIM=core|routing` (§6.2). Dead-end.
**Tests.** integration: smart mode + "analyze unseen file X" → task completes (file tools remain, OR
the door can read the file). Must FAIL before Phase 4, PASS after. Parametrized over every enforcement mode.
**Failure behavior.** If classification is uncertain, native file tools stay available; the uncertainty
is recorded as a ledger `metadata` flag.
**Closes.** audit P1 / INV-ENF-001.

### INV-ROUTE-004 — exactly one terminal state per route
### INV-ROUTE-005 — every terminal state recorded in the canonical ledger
**Definition.** Terminal ∈ {accepted, rejected, failed, cancelled, bypassed, overridden, unknown};
each route ends in exactly one, recorded as a ledger field.
**Owning component.** Ledger `terminal_state` field.
**Status.** RED. States exist only as scattered log-string tags; several (context-dependent override,
DIRECT_ANSWER) touch no accounting (§6.5).
**Tests.** property: every completed route in a generated run has exactly one terminal_state in the ledger.

---

## Enforcement invariants

### INV-ENF-001 — no enforcement mode creates a structural dead-end
Same evidence/tests as INV-ROUTE-001/002. **Status.** RED (§6.2).

### INV-ENF-002 — tool-call and plain-text overrides use the same accounting semantics
**Status.** RED. `mark_overridden` (tool-call) updates `session_spend`; `stop-enforce.py` (plain-text)
does not (§6.3). **Tests.** unit: both override types decrement realized identically. **Closes.** B7.

### INV-ENF-003 — a bypass detected after generation still updates realization/override accounting
**Owning component.** `stop-enforce.py` → ledger override event (Phase 3).
**Status.** RED (§6.3). **Tests.** e2e plain-text bypass → ledger override event + realized decreases.

### INV-ENF-004 — every mode has documented, tested behavior; unprovable modes marked experimental/removed
**Status.** GAP. Modes advise/suggest/soft/smart/hard/strict/shadow/off exist with subtle differences
(§6.1) and partial tests (B0-1 shows the enforcement tests are order-fragile).
**Tests.** one behavioral test per mode × task-type; hermetic (resets global state). **Closes.** RC-0.

---

## Health invariants

### INV-HEALTH-001 — doctor inspects the same provider-health/breaker state the router uses
**Owning component.** Unified health snapshot (Phase 5): a shared store or an RPC to `llm_health()`.
**Status.** RED, and **structural** — tracker is in-memory per-process; doctor is a fresh CLI process,
so an import alone reads an empty tracker (§7.2). Requires a shared/queryable snapshot.
**Tests.** integration (spec Phase 5): valid creds + gateway ok + **breaker open** → doctor must NOT
report the provider fully healthy, and its reason must match the router's rejection reason. FAIL before, PASS after.
**Closes.** audit C10 / RC-4.

### INV-HEALTH-002 — healthy ⇒ router-eligible at the same moment (modulo reported policy filters)
**Status.** RED (same split). **Tests.** integration: a provider doctor calls healthy is accepted by a
concurrent router eligibility check, or the policy reason is reported.

### INV-HEALTH-003 — "no provider" diagnostic explains every rejected provider's reason
**Status.** RED. Router raises a generic `ValueError`/`RuntimeError` (fail-closed, good) but does not
enumerate per-provider reasons (§7.3-4). Reasons exist only in structlog.
**Tests.** integration: with 2 providers ineligible for different reasons, the diagnostic names both reasons.

Also fold in the **internal health defects** (§7.3) as regression tests: emergency-loop `record_failure`
symmetry; cross-process tracker note (documented limitation or shared store).

---

## Claims invariants

### INV-CLAIM-001 — every numeric public claim links to reproducible evidence
### INV-CLAIM-002 — grandfathered claims are revalidated, not permanently exempted
### INV-CLAIM-003 — generated benchmarks carry full provenance (commit, dataset, config, host mode,
prices, model versions, success criteria, quality, token/cost/overhead totals, override/escalation/failure rates)
### INV-CLAIM-004 — unsupported claims are removed/weakened, not preserved
**Owning component.** Evidence registry + rewritten claim linter (Phase 6), fed by the control-group
benchmark (Phase 8).
**Status.** RED. Guard's `CLAIM_RE` is blind to numeric savings language and only scans `.md`; the
"35–80% proven" line is grandfathered by trimmed-text signature; no control-group benchmark exists
(§8.1, §8.2). **Tests.** linter unit tests: fails on claim w/o evidence, expired evidence, missing
artifact, metric/wording mismatch, out-of-scope commit, subscription-quota-only dollar claim,
simulated-only "proven". e2e: the "35–80% proven" line must either gain a real benchmark artifact or be removed.
**Closes.** audit B6 / RC-5.

---

## Cross-cutting

### INV-TEST-000 (RC-0) — the suite is hermetic and green on a clean checkout
**Definition.** `pytest` from a clean checkout passes deterministically regardless of order/parallelism;
no test leaks env vars, `~/.chuzom` state, or module singletons.
**Status.** RED. 3 order-dependent failures in `test_zero_claude_bypass.py` (§2, B0-1).
**Tests.** run suite with `-p randomly`/reordered and under xdist; add fixtures that isolate
`~/.chuzom`, env, and singletons. This is a Gate-20 precondition and must be fixed first in Phase 7.

---

## Invariant → historical-finding index
| Invariant | Closes | Root cause |
|---|---|---|
| INV-COST-001/002/003/004 | AC-1, AC-2, AC-3, audit P0-1/P0-2 | RC-1, RC-2 |
| INV-COST-005, INV-SAVE-002 | audit A3 | RC-1 |
| INV-COST-006, INV-SAVE-001/003/005 | audit P0-2 | RC-1 |
| INV-SAVE-004, INV-ENF-002/003 | audit B7 | RC-3 |
| INV-ROUTE-001/002/003, INV-ENF-001 | audit P1 | (enforcement) |
| INV-ROUTE-004/005 | (terminal-state gap) | RC-2 |
| INV-HEALTH-001/002/003 | audit C10 | RC-4 |
| INV-CLAIM-001..004 | audit B6 | RC-5 |
| INV-TEST-000 | B0-1 | RC-0 |
| INV-ROUTE-003 (fail-open capability) + C9 verification (already GREEN, regression-lock) | audit C9 (refuted-positive) | — |

**Note (C9 positive):** objective verification (`agentic/acceptance.py`, `engine.py:_verify` fail-closed)
already holds; it must be regression-locked so a future change can't silently reintroduce self-report.
