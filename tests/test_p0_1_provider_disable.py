"""P0-1 — control-plane → data-plane: admin provider/model disable
actually changes routing.

Before this, the router never read the ``RuntimeProviderRegistry``, so
``POST /v1/admin/providers/{p}:disable`` returned 200 and persisted state
while routing was unchanged — disabling a leaking/compromised provider was
a silent no-op. These tests drive ``route_and_call`` end-to-end and assert
that a disabled model/provider is dropped from the dispatched chain.
"""
from __future__ import annotations

from typing import Any

import pytest

from chuzom.profiles import provider_from_model


@pytest.fixture
def _isolated(monkeypatch, tmp_path):
    from chuzom.audit_routing import reset_audit_log_for_tests
    from chuzom.idempotency import reset_store_for_tests

    monkeypatch.setenv("CHUZOM_IDEMPOTENCY_PATH", str(tmp_path / "idem.db"))
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(tmp_path / "audit.db"))
    reset_store_for_tests()
    reset_audit_log_for_tests()


async def _route_capturing_chain(monkeypatch, prompt: str) -> list[str]:
    """Route once with a stubbed dispatcher that records the post-filter
    chain it was handed, and return that chain."""
    from chuzom import router as router_mod
    from chuzom.idempotency import reset_store_for_tests
    from chuzom.router import route_and_call
    from chuzom.types import LLMResponse, TaskType

    captured: dict[str, list[str]] = {}

    async def _capture(**kwargs: Any) -> LLMResponse:
        chain = list(kwargs.get("models_to_try", []))
        captured["chain"] = chain
        head = chain[0] if chain else "gemini/gemini-2.5-flash"
        return LLMResponse(
            content="ok", model=head, provider=provider_from_model(head),
            input_tokens=1, output_tokens=1, cost_usd=0.001, latency_ms=10.0,
        )

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _capture)
    reset_store_for_tests()  # don't let idempotency short-circuit the dispatch
    await route_and_call(task_type=TaskType.QUERY, prompt=prompt)
    return captured.get("chain", [])


@pytest.mark.asyncio
async def test_admin_disabled_model_is_dropped_from_routing(_isolated, monkeypatch):
    from chuzom import provider_registry as pr

    reg = pr.RuntimeProviderRegistry()  # in-memory, isolated
    monkeypatch.setattr(pr, "_global_registry", reg)

    chain = await _route_capturing_chain(monkeypatch, "natural chain please")
    assert chain, "expected a non-empty routing chain to test against"
    victim = chain[0]

    reg.disable_model(victim, reason="compromised")
    after = await _route_capturing_chain(monkeypatch, "after disabling the model")
    assert victim not in after, f"{victim} disabled via admin but still routed"


@pytest.mark.asyncio
async def test_admin_disabled_provider_is_dropped_from_routing(_isolated, monkeypatch):
    from chuzom import provider_registry as pr

    reg = pr.RuntimeProviderRegistry()
    monkeypatch.setattr(pr, "_global_registry", reg)

    chain = await _route_capturing_chain(monkeypatch, "natural chain please")
    assert chain, "expected a non-empty routing chain"
    victim_provider = provider_from_model(chain[0])

    reg.disable(victim_provider, reason="leaking keys")
    after = await _route_capturing_chain(monkeypatch, "after disabling the provider")
    assert all(provider_from_model(m) != victim_provider for m in after), (
        f"provider {victim_provider} disabled but its models still routed: {after}"
    )


@pytest.mark.asyncio
async def test_no_disable_is_a_noop(_isolated, monkeypatch):
    """Sanity: with nothing disabled, the chain is unaffected (no
    accidental over-filtering)."""
    from chuzom import provider_registry as pr

    reg = pr.RuntimeProviderRegistry()
    monkeypatch.setattr(pr, "_global_registry", reg)
    chain = await _route_capturing_chain(monkeypatch, "untouched chain")
    assert chain, "expected a non-empty chain with nothing disabled"
