# Chuzom Correctness Reset — 03. Release Gates Evaluation

Evaluated against the working tree at the end of the reset session (base `d748d11`
+ reset commits `fec683c … 2c2ea7d`). Per working rules 14–15: a gate that is not
**proven** is FAIL, and the release fails explicitly rather than weakening the bar.

## Verdict: **RELEASE NOT QUALIFIED**

Mandatory gates unmet: 1, 2 (P1 open), 6/7 (partial), 11, 13, 15, 16, 17, and the
consecutive-audit rule. Detail below.

## Mandatory gate table

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | All critical invariants have unit+integration+e2e coverage | **FAIL (partial)** | Covered & tested: INV-COST-001/002/003/006 (ledger+router+team), INV-ENF-002/003, INV-HEALTH-001, INV-CLAIM-001..004, INV-TEST-000. Not covered: INV-COST-004 (full surface reconciliation), INV-COST-005 (hook overhead), INV-ROUTE-001/002/003 (dead-end) |
| 2 | Every historical P0/P1 has a regression test | **FAIL** | P0-1 ✓ (`test_route_ledger_integration`), P0-2/AC-2 ✓ (`test_real_dollars_avoided`), B7 ✓, C10 ✓, B0-1 ✓, B6 ✓. **P1 enforcement dead-end: NOT fixed, no test** |
| 3 | Every P2 fixed / accepted-with-rationale / removed | **FAIL** | AC-4..AC-7 (stale prices, dual-writer race, dead-accounting) documented in `00_CURRENT_STATE.md §5.4` but not yet fixed |
| 4 | No open P0 finding | **PASS** | P0-1, P0-2 both fixed with fail-before/pass-after proof |
| 5 | No open P1 finding | **FAIL** | Enforcement dead-end (INV-ROUTE-001/002) still reachable in smart/hard/strict |
| 6 | Every billable attempt reconciles exactly once | **PARTIAL** | Router emits accepted+rejected+escalated+emergency attempts to the ledger (INV-COST-001✓); semantic-cache-hit and pre-dispatch-denial paths (AC-6) not yet emitting |
| 7 | All user-facing surfaces reconcile with the canonical ledger | **FAIL** | Only `team.py` migrated. ~13 surfaces (session-end, digest, dashboard_data, summary, statusline_hud, retrospective, admin) still compute independent math |
| 8 | Subscription screens carry no unqualified cash claim | **PARTIAL** | `team.py` Slack/Discord/Telegram fixed; `admin.llm_savings` already honest. session-end / digest / dashboard_data not yet migrated |
| 9 | Plain-text & tool-call overrides both update realization | **PASS** | B7 fixed + tested (`test_stop_enforce_override`) |
| 10 | Hook overhead measured or savings marked unknown | **FAIL** | INV-COST-005 not implemented; directive tokens still unmeasured |
| 11 | Strong enforcement has no capability dead-ends | **FAIL** | INV-ROUTE-001/002 open (P1) |
| 12 | Doctor and router provider-health reconcile | **PASS** | C10 fixed + tested (`test_doctor_health_reconciliation`) |
| 13 | All critical mutations killed | **FAIL** | Mutation testing (mutmut) added as dep but not yet run against the invariants |
| 14 | No numeric public claim without current reproducible evidence | **PASS** | B6: unsupported "35–80% proven" retracted; claim-evidence registry + validator gate in CI |
| 15 | Control-group benchmark shows positive net verified token savings | **FAIL** | Phase 8 not built — no real Chuzom-off-vs-on A/B harness exists (only repricing counterfactuals) |
| 16 | Quality within non-inferiority margin | **FAIL** | Depends on Gate 15 |
| 17 | No benchmark event has unclassified spend | **FAIL** | Depends on Gate 15 |
| 18 | No unknown realization counted as verified realized | **PARTIAL** | Ledger models `realization_status` incl. `unknown`; full savings model not yet deriving realized from it |
| 19 | Schema migrations + rollback tested | **PARTIAL** | New `execution_events` table is `CREATE TABLE IF NOT EXISTS` (additive, no migration needed); legacy stores untouched |
| 20 | Complete suite passes from a clean checkout | **PASS** | B0-1 hermeticity fixed; full suite 0 failed / 0 error (deterministic) |

## Consecutive-audit rule
**NOT SATISFIED.** Requires two consecutive complete audits of a frozen commit with zero
new P0/P1 and no "not reached" sections. Not performed — the reset delivered fixes but the
final two-audit qualification pass has not run (and cannot pass while Gates 5/11/15 are open).

## What IS proven (regression-locked, won't regress silently)
INV-COST-001/002/003/006 · INV-ENF-002/003 · INV-HEALTH-001 · INV-CLAIM-001..004 ·
INV-TEST-000. Plus the pre-existing North-Star positives retained: objective verification
fails-closed (C9), router fails-closed on no-providers.

## Remaining backlog to reach QUALIFIED (defined, not vague)
1. Fix enforcement dead-end P1 (INV-ROUTE-001/002/003) + test → Gates 5, 11.
2. Migrate ~13 read surfaces to the aggregation layer + delete AC-7 dead code → Gates 3, 7, 8.
3. Emit `directive_injected` hook-overhead events; net them from savings → Gates 10, 18.
4. Emit cache-hit / pre-dispatch attempts → Gate 6.
5. Run mutmut against the invariants; kill critical mutations → Gate 13.
6. Build the real control-group benchmark (Phase 8) → Gates 15, 16, 17; only then may a
   savings magnitude be marked `supported` in the claim-evidence registry.
7. Freeze commit; run two consecutive complete audits → consecutive-audit rule.
