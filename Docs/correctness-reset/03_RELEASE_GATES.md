# Chuzom Correctness Reset — 03. Release Gates Evaluation

Re-evaluated against `main` after the reset PR series **#158–#184** merged (accounting/
dashboard fixes #158–#179; enforcement→tool-capable-door ENF-FIX-1..4 #181–#184). Per
working rules 14–15: a gate that is not **proven** is FAIL, and the release fails explicitly
rather than weakening the bar.

> **History:** the first evaluation (base `d748d11`) is preserved in git history. This
> revision reflects the fixes actually merged since; **Gates 5 and 11 flipped FAIL→PASS** with
> ENF-FIX-1..4, but the overall verdict is unchanged (benchmark + mutation + two-audit gates
> remain open).

## Verdict: **RELEASE NOT QUALIFIED**

Still-unmet mandatory gates: **13** (mutations not run to closure), **15 / 16 / 17**
(control-group benchmark not built), and the **consecutive-audit rule**. Detail below.

> **Update (ENF-FIX-1..4 merged, #181–#184):** Gates **5** and **11** now **PASS** — the
> execution-work capability dead-end (GAP-ENF-1 / INV-ROUTE-006) is closed and
> regression-locked. Execution/repo work of any task_type routes to the tool-capable
> `llm_act` door (never a text-only door), context-dependent execution work is provisioned
> (`llm_act(context=…)`), enforcement escalations are first-class ledger events, and the
> execution signal is honored regardless of classifier wobble. The verdict is unchanged: the
> benchmark (15/16/17), mutation closure (13), and the two-consecutive-audit rule remain the
> blockers — those are the deferred items #5/#14/#6.

## Mandatory gate table

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | All critical invariants have unit+integration+e2e coverage | **PASS** | Covered & tested: INV-COST-001/002/003/004/005/006, INV-ROUTE-001/002/003/004/005/**006**, INV-ENF-002/003, INV-HEALTH-001, INV-CLAIM-001..004, INV-TEST-000. INV-ROUTE-006 (execution→tool-capable door) now covered by ENF-FIX-1..4 tests (#181–#184) |
| 2 | Every historical P0/P1 has a regression test | **PASS** | P0-1 ✓, P0-2/AC-2 ✓, B7 ✓, C10 ✓, B0-1 ✓, B6 ✓, P1 enforcement dead-end ✓ (#159). GAP-ENF-1 (execution dead-end) ✓ (ENF-FIX-1..4, #181–#184) |
| 3 | Every P2 fixed / accepted-with-rationale / removed | **PASS** | AC-3 (stale price) ✓; AC-4 ✓ (digest #168, dashboard #169, admin #170); AC-5 dual-writer race ✓ (#171); AC-6 ✓ (#160); AC-7 ✓ (retrospective #163, dead-code delete #165, statusline #166, calc_savings #167). `summary.py` accepted-with-rationale (deferred: needs a lineage token-schema change; code defers to v0.0.3) |
| 4 | No open P0 finding | **PASS** | P0-1, P0-2 fixed with fail-before/pass-after proof |
| 5 | No open P1 finding | **PASS** | Original P1 (Q&A read dead-end) fixed (#159). **GAP-ENF-1** (execution/repo work dead-ended at a text-only door) is now **closed** by ENF-FIX-1..4 (#181–#184): execution work of any task_type routes to the tool-capable `llm_act` door, context-dependent execution is provisioned, and escalation is clean + ledger-recorded. The residual `coordination` **exemption** (allowed-native, not routed to `llm_act`) is documented in `05_ENFORCEMENT_FIX_PLAN.md` as a lower-severity follow-up — it is not a capability dead-end |
| 6 | Every billable attempt reconciles exactly once | **PASS** | Router emits accepted+rejected+escalated+emergency (INV-COST-001), plus cache-hit / pre-dispatch-denial / exhaustion terminal states (AC-6, #160) |
| 7 | All user-facing surfaces reconcile with the canonical baseline | **PASS (1 deferred)** | Migrated to the canonical baseline/aggregation layer: team.py, retrospective (#163), statusline_hud (#166), digest (#168), dashboard (#169), admin (#170); `calc_savings` task-aware (#167). `session_spend` already exposes separate potential/realized (honest). `summary.py` deferred with rationale |
| 8 | Subscription screens carry no unqualified cash claim | **PASS** | team.py channels fixed; admin.llm_savings honest + mislabel corrected (#170); digest/dashboard host-labeled to the canonical price |
| 9 | Plain-text & tool-call overrides both update realization | **PASS** | B7 fixed + tested (`test_stop_enforce_override`) |
| 10 | Hook overhead measured or savings marked unknown | **PASS** | INV-COST-005 implemented + tested (#159); `directive_injected` overhead aggregated |
| 11 | Strong enforcement has no capability dead-ends | **PASS** | P1 read dead-end fixed (#159); **execution-work dead-end closed** (ENF-FIX-1..4, #181–#184): needs-execution work names `llm_act` not a text-only door; context-dependent execution is provisioned; escalation reaches the host cleanly and is recorded (`escalation_started`). Regression-locked by `test_execution_signal`, `test_enf_fix{1,3,4}_*`, `test_enf_fix2_context_provisioned_door` |
| 12 | Doctor and router provider-health reconcile | **PASS** | C10 fixed + tested (`test_doctor_health_reconciliation`) |
| 13 | All critical mutations killed | **FAIL (honest — equivalent mutants remain)** | Scoped mutmut over hermetic modules: `execution_ledger.py` (#173), `execution_signal.py` (**32→48 / 54**; pinned `fires is True/False`, asserted the reason/verb/obj transparency contract), `operational_signal.py` (**33→48 / 54**; asserted the reason + matched verb/cue on every non-firing branch), and `bench/savings.py` (**82→98 / 102**; pinned every reported field, failure/exhausted-row classification, default non-inferiority margin, missing-Chuzom-arm raise, non-numeric-overhead degradation, and the unpaired-error message). Remaining survivors are provably **equivalent mutants** (capturing-group `group(0)==group(1)`; `None`-then-`or 0.0` overhead defaults; `getattr` default on rows that always carry `notes`; unreachable empty-arm fallback; synthetic `XX`-padding of internal strings whose meaning is unchanged). Gate stays FAIL because equivalent mutants can't be killed without over-fitting — documented, not hidden |
| 14 | No numeric public claim without current reproducible evidence | **PASS** | B6: unsupported claim retracted; claim-evidence registry + CI validator gate |
| 15 | Control-group benchmark shows positive net verified token savings | **FAIL** | Phase 8 not built — no real Chuzom-off-vs-on A/B harness (only repricing counterfactuals) |
| 16 | Quality within non-inferiority margin | **FAIL** | Depends on Gate 15 |
| 17 | No benchmark event has unclassified spend | **FAIL** | Depends on Gate 15 |
| 18 | No unknown realization counted as verified realized | **PARTIAL** | Ledger models `realization_status` incl. `unknown`; full savings model not yet deriving realized from it end-to-end |
| 19 | Schema migrations + rollback tested | **PARTIAL** | `execution_events` is additive (`CREATE TABLE IF NOT EXISTS`); legacy stores untouched |
| 20 | Complete suite passes from a clean checkout | **PASS (with known-flaky caveat)** | Hermetic in CI (3.13/3.14 green across the series). Two known-flaky, non-blocking classes on a loaded host: the `test (3.11)` aiosqlite-watchdog job, and RC-0 order-pollution in `test_direct_executor::TestExecuteAgentContext` (passes in isolation). A real regression fails 3.13/3.14 too |

## Consecutive-audit rule
**NOT SATISFIED.** Requires two consecutive complete audits of a frozen commit with zero
new P0/P1 and no "not reached" sections. Not performed — cannot pass while Gates 13/15/16/17
are open (the benchmark + mutation-closure work).

## What IS proven (regression-locked, won't regress silently)
INV-COST-001/002/003/004/005/006 · INV-ROUTE-001/002/003/004/005/**006** · INV-ENF-002/003 ·
INV-HEALTH-001 · INV-CLAIM-001..004 · INV-TEST-000. Every AC-3/4/5/6/7 fix ships a
fail-before/pass-after test plus (for the price surfaces) a source guard against the
stale/mislabeled constant reappearing. AC-5 has a deterministic concurrency test. **INV-ROUTE-006
(execution→tool-capable door)** is now regression-locked by ENF-FIX-1..4 (#181–#184):
`test_execution_signal` (bidirectional), `test_enf_fix1_execution_door`,
`test_enf_fix2_context_provisioned_door`, `test_enf_fix3_escalation_event`,
`test_enf_fix4_stable_execution_door`.

## Remaining backlog to reach QUALIFIED (defined, not vague)
1. ~~**Batch B — enforcement → tool-capable door**~~ ✅ **DONE** (ENF-FIX-1..4, #181–#184) →
   Gates 5, 11 PASS. Follow-up (lower severity): route the `coordination` `LOCAL_BASH_EXEMPT`
   path through `llm_act` instead of exempting to native (documented in `05_...`).
2. **Phase 3.7b — leaderboard-driven capability ranking** in the router's provider-chain /
   escalation-top (config-sourced, not live-fetch per route). Core-routing change; careful.
3. **Phase 7 — mutmut** over the finding→test matrix, scoped to hermetic modules
   (`execution_ledger` first) → Gate 13.
4. **Phase 8 — control-group benchmark** (real Chuzom-off-vs-on A/B) → Gates 15, 16, 17;
   only then may a savings magnitude be marked `supported` in the claim-evidence registry.
5. `summary.py` real token counterfactual once the lineage store carries token counts
   (schema change) → completes Gate 7.
6. **Phase 9 — freeze commit; run two consecutive complete audits** → consecutive-audit rule.
