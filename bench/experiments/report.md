# Savings-integrity scorecard  (2026-07-20 21:19 UTC)

Deterministic offline replay of three realistic session shapes through the
real chuzom savings code. Baseline = latest Opus ($5/$25). See RETROSPECTIVE
Deliverable 4.

## Per-shape savings (all-time)

| Shape | Turns | Routed% | DIRECT-SKIP% | Baseline-avoided | Real $ (sub) | Real $ (metered) |
|---|---|---|---|---|---|---|
| local_repo_audit | 5 | 0.0 | 100.0 | $0.0000 | $0.0000 | $0.0000 |
| stateless_qa | 5 | 100.0 | 0.0 | $0.1350 | $0.0000 | $0.1350 |
| mixed_agentic | 5 | 60.0 | 40.0 | $0.0885 | $0.0000 | $0.0885 |

## Counterfactual: real dollars by quota state (all-time)

| Shape | Baseline-avoided | Real $ unpressured | Real $ over-cap | Real $ metered |
|---|---|---|---|---|
| local_repo_audit | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| stateless_qa | $0.1350 | $0.0000 | $0.1350 | $0.1350 |
| mixed_agentic | $0.0885 | $0.0000 | $0.0885 | $0.0885 |

**Reading:** on a flat-rate subscription with headroom, real dollars avoided is
~$0 (M-3: chuzom is a quota-smoother, not a dollar-saver); the baseline-avoided
figure is a token/quota story, not cash. Real dollars appear only over the cap
or in metered API mode.

## Invariants

- [PASS] [local_repo_audit] baseline_avoided == saved_usd (all windows)
- [PASS] [local_repo_audit] aggregate reproducible from cassette — prod=$0.0000 recompute=$0.0000
- [PASS] [local_repo_audit] real_$ <= baseline_avoided
- [PASS] [local_repo_audit] window nesting today<=week<=month<=all — 0.000<=0.000<=0.000<=0.000
- [PASS] [local_repo_audit] real_$ == 0 on flat-rate subscription — real=$0.0000
- [PASS] [local_repo_audit] deterministic replay
- [PASS] [stateless_qa] baseline_avoided == saved_usd (all windows)
- [PASS] [stateless_qa] aggregate reproducible from cassette — prod=$0.1350 recompute=$0.1350
- [PASS] [stateless_qa] real_$ <= baseline_avoided
- [PASS] [stateless_qa] window nesting today<=week<=month<=all — 0.135<=0.135<=0.135<=0.135
- [PASS] [stateless_qa] real_$ == 0 on flat-rate subscription — real=$0.0000
- [PASS] [stateless_qa] deterministic replay
- [PASS] [mixed_agentic] baseline_avoided == saved_usd (all windows)
- [PASS] [mixed_agentic] aggregate reproducible from cassette — prod=$0.0885 recompute=$0.0885
- [PASS] [mixed_agentic] real_$ <= baseline_avoided
- [PASS] [mixed_agentic] window nesting today<=week<=month<=all — 0.088<=0.088<=0.088<=0.088
- [PASS] [mixed_agentic] real_$ == 0 on flat-rate subscription — real=$0.0000
- [PASS] [mixed_agentic] deterministic replay

**18/18 invariants passed.**
