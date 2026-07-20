"""RETROSPECTIVE Deliverable 4 — the savings-integrity experiments run in CI.

Drives the offline experiment harness (bench/experiments) and asserts every
invariant passes for every session shape, so the reconciliation / counterfactual
guarantees can't silently regress. Offline, deterministic, $0.
"""
from __future__ import annotations

import pytest

from bench.experiments import analysis, replay


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", replay.SHAPES)
async def test_shape_reconciliation_and_properties(shape):
    trace = replay.load_trace(shape)
    sub = await replay.replay(shape, subscription=True)

    checks = list(analysis.check_reconciliation(sub, trace))
    checks.append(analysis.check_window_nesting(sub))
    checks.append(analysis.check_real_zero_on_subscription(sub))
    for name, ok, detail in checks:
        assert ok, f"{shape}: {name} {detail}"


@pytest.mark.asyncio
async def test_local_audit_saves_nothing():
    # The retro's own workload: 100% context-dependent -> DIRECT SKIP -> $0.
    sub = await replay.replay("local_repo_audit", subscription=True)
    assert sub["direct_skip_pct"] == 100.0
    assert sub["baseline_avoided_usd"] == 0.0
    assert sub["real_dollars_avoided_usd"] == 0.0


@pytest.mark.asyncio
async def test_stateless_qa_real_zero_on_sub_positive_metered():
    # M-2/M-3 made concrete: baseline-avoided > 0, but real $ is 0 on a
    # subscription and only becomes positive in metered API mode.
    sub = await replay.replay("stateless_qa", subscription=True)
    met = await replay.replay("stateless_qa", subscription=False)
    assert sub["baseline_avoided_usd"] > 0.0
    assert sub["real_dollars_avoided_usd"] == 0.0
    assert met["real_dollars_avoided_usd"] == sub["baseline_avoided_usd"]


def test_counterfactual_real_zero_under_cap_positive_over_cap():
    trace = replay.load_trace("stateless_qa")
    ample = analysis.counterfactual(trace, cap_headroom_usd=1e9)
    overcap = analysis.counterfactual(trace, cap_headroom_usd=0.0)
    assert ample.real_subscription_usd == 0.0          # unpressured -> $0 real
    assert overcap.real_subscription_usd == ample.baseline_avoided_usd  # overage billed
    assert ample.real_metered_usd == ample.baseline_avoided_usd
