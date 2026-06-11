"""P0-1 (part B) — the admin-pushed versioned policy actually drives routing.

Before this, the router resolved its org policy from the local
``~/.chuzom/org-policy.yaml`` file (`load_org_policy`) and never consulted
the admin ``PolicyVersionStore``, so ``POST /v1/admin/policy`` and its
rollback returned 200 + persisted a version while routing was unchanged.
``load_active_org_policy`` now prefers the active version in the shared
store, so push/rollback changes routing.
"""
from __future__ import annotations

from typing import Any

import pytest

from chuzom.profiles import provider_from_model

_INJECTED = {"codex", "ollama", "gemini_cli"}  # added AFTER apply_policy


@pytest.fixture
def store(tmp_path, monkeypatch):
    from chuzom import policy_versions as pv

    s = pv.PolicyVersionStore(db_path=tmp_path / "pv.db", check_same_thread=False)
    monkeypatch.setattr(pv, "_global_policy_store", s)
    return s


# ── 1. load_active_org_policy resolution ────────────────────────────────────


def test_falls_back_when_no_active_version(store, monkeypatch, tmp_path):
    from chuzom.policy import load_active_org_policy

    # point the file fallback at a non-existent path so we get the default
    monkeypatch.setattr(
        "chuzom.policy.load_org_policy",
        lambda *a, **k: __import__("chuzom.policy", fromlist=["OrgPolicy"]).OrgPolicy(source="default"),
    )
    p = load_active_org_policy()
    assert p.source != "versioned"


def test_prefers_versioned_policy(store):
    from chuzom.policy import load_active_org_policy

    store.push(
        yaml_text="block_models:\n  - openai/gpt-4o\n",
        actor_user_id="admin", actor_email="a@x",
    )
    p = load_active_org_policy()
    assert p.source == "versioned"
    assert "openai/gpt-4o" in p.block_models


def test_rollback_restores_prior_policy(store):
    from chuzom.policy import load_active_org_policy

    v1 = store.push(
        yaml_text="block_models:\n  - openai/gpt-4o\n",
        actor_user_id="admin", actor_email="a@x",
    )
    # v2 lifts the block → active policy no longer blocks it
    store.push(yaml_text="block_models: []\n", actor_user_id="admin", actor_email="a@x")
    assert "openai/gpt-4o" not in load_active_org_policy().block_models
    # rollback to v1 → the block is active again
    store.rollback(target_version=v1["version"], actor_user_id="admin", actor_email="a@x")
    assert "openai/gpt-4o" in load_active_org_policy().block_models


# ── 2. End-to-end: a versioned block drops a model from routing ─────────────


@pytest.mark.asyncio
async def test_versioned_block_drops_model_from_routing(store, monkeypatch, tmp_path):
    from chuzom import router as router_mod
    from chuzom.audit_routing import reset_audit_log_for_tests
    from chuzom.idempotency import reset_store_for_tests
    from chuzom.router import route_and_call
    from chuzom.types import LLMResponse, TaskType

    monkeypatch.setenv("CHUZOM_IDEMPOTENCY_PATH", str(tmp_path / "idem.db"))
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(tmp_path / "audit.db"))
    reset_store_for_tests()
    reset_audit_log_for_tests()

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

    reset_store_for_tests()
    await route_and_call(task_type=TaskType.QUERY, prompt="natural chain")
    chain = captured.get("chain", [])
    # Pick a base-chain model (apply_policy runs before injection, so only
    # non-injected providers are reliably affected by a block_models policy).
    victim = next((m for m in chain if provider_from_model(m) not in _INJECTED), None)
    if victim is None:
        pytest.skip("no base-chain (non-injected) model available in this env to block")

    store.push(
        yaml_text=f"block_models:\n  - {victim}\n",
        actor_user_id="admin", actor_email="a@x",
    )
    reset_store_for_tests()
    await route_and_call(task_type=TaskType.QUERY, prompt="after admin policy push")
    assert victim not in captured["chain"], f"{victim} blocked via admin policy but still routed"
