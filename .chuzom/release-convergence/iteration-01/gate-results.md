# Iteration 1 — GATE Results

**Verdict: PASS (all Iteration-1 findings fixed, full suite green).**

## Full suite (final, all 12 findings fixed)
```
6389 passed, 174 skipped, 30 deselected, 1 xfailed, 13 warnings in 201.76s
FAILED/ERROR: 0
```

## Per-finding reproduction → fixed evidence

| Finding | Pre-fix reproduction | Post-fix result | Acceptance test |
|---------|----------------------|-----------------|-----------------|
| P-CAP-INJECT (Crit) | precision+cap+hard → openai billed ($0.001) | → ollama $0 | test_cap_hit_precision_prompt_stays_free, ..._org_specialist_stays_free |
| P-DRAFT (Crit) | default auto → block (turn replaced by draft) | → echo (advisory) | test_draft01_no_block_outside_zero_claude |
| P-CLAIMS (High) | "60-90%" in install_hooks + 4 more | 0 occurrences in src | test_no_fabricated_magnitude_claims_anywhere_in_src |
| P-PRIVACY (High) | local mode → history to perplexity | → blocked | test_red2_04_privacy_local_blocks_all_external |
| P-LOCK (High) | 5 distinct locks, lost updates | 1 shared lock, N*ITERS exact | test_red1_09_budget_lock_cross_thread |
| P-ROUTEID (High) | route_id always None, no dedup | route_id threaded, retries dedup | test_red1_0506_routeid_and_dedup |
| P-SPENDBLIND (High) | rejected paid attempt invisible | counted (0.10+0.05=0.15) | test_red1_08_cap_sees_rejected_attempts |
| P-BOUNDARY (Med) | UTC month vs local day | same local frame | test_red1_07_spend_boundary_consistency |
| P-OBSERV (Med) | no downgrade field | cap_downgraded=True + reason | test_red2_02_downgrade_observable |
| P-INSTALL2 (Low) | shell installer no backup | backs up malformed file | test_red2_03_shell_installer_backup |

## Gates status (this iteration)
- **Gate A (static):** ruff clean on all changed files.
- **Gate B (correctness):** 6389 passed, 0 failed; GATE re-run caught + fixed one test-regression (fcff7cc).
- **Gate C (North Star):** cap-downgrade confines to free-local (never paid under cap); block-mode fabrication removed outside zero-Claude; privacy gate covers all external providers.
- **Gate D (accounting):** route_id per-route attribution; event dedup; rejected-attempt spend visible; consistent time frame.
- **Gate E (failure safety):** budget lock atomic cross-thread; installer backup.

## Convergence status
Iteration 1 FIX complete: all 12 findings fixed + validated. Clean-audit counter still **0** (no fresh audit has run against this state yet). Next: fresh RED-1/RED-2 round against HEAD, then PLAN.
