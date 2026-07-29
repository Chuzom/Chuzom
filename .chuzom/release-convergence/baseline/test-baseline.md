# Test Baseline (Iteration 0) — HEAD 8fd4af1

Full suite: 6352 passed, 10 failed, 2 errors, 174 skipped, 1 xfail, wall 228s.

## Classification of the 12 non-passing (all ripple effects of this branch's changes)

| Test | Cause | Fix |
|---|---|---|
| test_host_integrations plugin_manifest_version ×6, test_plugin_packaging ×1 | pyproject bumped to 1.0.1, plugin manifests still 1.0.0 | Bump 5 plugin manifests → 1.0.1 (DONE) |
| test_audit_v5 test_daily_budget_exceeded_raises_immediately | TQ-007: env CHUZOM_DAILY_SPEND_LIMIT now downgrades (was hard block); test expects raise in default/smart | Update test to enforce=hard (daily cap still blocks with no free fallback) |
| test_tq007 test_cap_hit_no_free_hard_blocks | env-leak: ambient CHUZOM_ENFORCE overrides repo_cfg via effective_enforce | Set CHUZOM_ENFORCE in _run harness |
| test_policy_switching test_routing_yaml_daily_caps_are_wired_and_downgrade | same env-leak | setenv CHUZOM_ENFORCE=hard |
| test_st004 ×2 ERROR | asyncio.get_event_loop().run_until_complete() conflicts with pytest-asyncio in full-suite run | use asyncio.run() |

None indicate a product-code defect; all are test-robustness or version-sync consequences of the branch. Fixing to restore a clean baseline before the audit verdict.

## Re-run finding (post-repair)
- test_context.py::TestBuildContextMessages::test_no_context_returns_empty — non-hermetic.
  build_context_messages() reads the durable ~/.chuzom session-context accumulator (via
  session_store); the test isolated the summaries DB + in-memory buffer but not HOME, so it
  read the developer's LIVE session accumulator (populated by active chuzom hooks) and saw
  context where none was expected. Confirmed: clean HOME → passes; the earlier "main passes"
  was a cwd-scope artifact. NOT a product defect. Fix: reset_session_buffer fixture now points
  HOME at a fresh temp dir (hermetic). Stable 3×.

## Baseline verdict: GREEN after repairs (0 product-code defects among the 13 non-passing).

## FINAL baseline (post-repair) — confirmed GREEN
```
6364 passed, 174 skipped, 30 deselected, 1 xfailed, 13 warnings in 177.21s (0:02:57)
```
- FAILED/ERROR: 0
- Repairs committed: 7397700, 34be388, 3d01869 (+ TQ-007 8fd4af1)
- Gate B (automated correctness): PASS on baseline
