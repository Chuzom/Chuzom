"""Regression: RED1-3-01/02/03 — reservation must not leak on early exits.

route_and_call adds _reservation to _pending_spend but had no top-level
try/finally, so early exits (empty chain, semantic-cache hit, reserve_envelope
failure) leaked it. A single idempotent _release_reservation_if_held() is now
called on every such exit. These drive route_and_call through those paths and
assert _pending_spend returns to baseline.
"""
from __future__ import annotations

import os
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tests.test_tq007_daily_cap_downgrade as t
from chuzom import router
from chuzom.types import RoutingProfile, TaskType


async def _drive(**overrides):
    """Run route_and_call with the tq007 harness plus per-test overrides."""
    with ExitStack() as es:
        p = es.enter_context
        p(patch.dict(os.environ, {"CHUZOM_ENFORCE": "smart"}))
        p(patch("chuzom.router.get_config", return_value=t._Cfg()))
        tr = MagicMock(); tr.is_healthy.return_value = True
        p(patch("chuzom.router.get_tracker", return_value=tr))
        ml = MagicMock(); ml.bind.return_value = MagicMock()
        p(patch("chuzom.router.log", ml))
        p(patch("chuzom.router._native_notify", lambda *a, **k: None))
        p(patch("chuzom.router.cost.get_monthly_spend", new_callable=AsyncMock, return_value=0.0))
        p(patch("chuzom.router.cost.get_daily_spend", new_callable=AsyncMock, return_value=0.0))
        p(patch("chuzom.router.cost.get_daily_spend_by_task_type", new_callable=AsyncMock, return_value=0.0))
        p(patch("chuzom.policy.load_org_policy", return_value=None))
        p(patch("chuzom.policy.get_active_policy", return_value=None))
        p(patch("chuzom.router.cost.log_usage", new_callable=AsyncMock))
        p(patch("chuzom.router.commit_envelope", new_callable=AsyncMock))
        p(patch("chuzom.router.release_envelope", new_callable=AsyncMock))
        p(patch("chuzom.semantic_cache.store", new_callable=AsyncMock))
        for target, mock in overrides.items():
            p(patch(f"chuzom.router.{target}", **mock))
        from chuzom.router import route_and_call
        return await route_and_call(TaskType.CODE, "hello", profile=RoutingProfile.BALANCED)


@pytest.mark.asyncio
async def test_no_leak_on_empty_chain():
    before = router._pending_spend
    with pytest.raises(ValueError):
        await _drive(
            reserve_envelope={"new_callable": AsyncMock, "return_value": (None, True, "k")},
            _build_and_filter_chain={"new_callable": AsyncMock, "return_value": []},
        )
    assert abs(router._pending_spend - before) < 1e-9, (
        f"RED1-3-01: reservation leaked on empty-chain exit: {before}->{router._pending_spend}"
    )


@pytest.mark.asyncio
async def test_no_leak_on_cache_hit_fast_path():
    from chuzom.types import LLMResponse
    cached = LLMResponse(content="c", model="ollama/x", input_tokens=1, output_tokens=1,
                         cost_usd=0.0, latency_ms=1.0, provider="ollama")
    with patch("chuzom.semantic_cache.check", new_callable=AsyncMock, return_value=cached):
        before = router._pending_spend
        resp = await _drive(
            reserve_envelope={"new_callable": AsyncMock, "return_value": (None, True, "k")},
            _build_and_filter_chain={"new_callable": AsyncMock, "return_value": ["openai/gpt-4o"]},
        )
        assert abs(router._pending_spend - before) < 1e-9, (
            f"RED1-3-02: reservation leaked on cache-hit fast path: {before}->{router._pending_spend}"
        )
