"""TQ-007 — daily spend caps DOWNGRADE to free-local, they do not hard-block.

Signed-off behavior (2026-07):
  cap hit → drop paid providers, keep {ollama, codex, gemini_cli} at $0.
    free-local available      → run free
    none available + hard     → block (BudgetExceededError)
    none available + smart/soft → fall through to Claude (original chain)
  Caps apply whenever configured, independent of enforce mode; enforce mode
  only governs the no-free-fallback branch.

Prior behavior (which this replaces): any daily cap hit raised
BudgetExceededError (warn only if enforce=soft).
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chuzom.repo_config import RepoConfig
from chuzom.types import BudgetExceededError, LLMResponse, RoutingProfile, TaskType


class _Cfg:
    chuzom_profile = RoutingProfile.BALANCED
    chuzom_monthly_budget = 0.0
    chuzom_daily_spend_limit = 0.0
    chuzom_escalate_above = 0.0
    chuzom_hard_stop_above = 0.0
    chuzom_claude_subscription = False
    chuzom_gemini_subscription = False
    chuzom_claw_code = False
    chuzom_routing_policy = "balanced"
    chuzom_agentic_model = ""
    codex_daily_limit = 1000
    compaction_mode = "off"
    compaction_threshold = 4000
    prompt_cache_enabled = False
    prompt_cache_min_tokens = 1024
    context_enabled = False
    caveman_mode = "off"
    # All providers used in tests must be "available" — in production
    # _build_and_filter_chain only ever returns available providers, so a free
    # provider surviving the downgrade filter is guaranteed available.
    available_providers = {"openai", "gemini", "ollama", "codex", "gemini_cli"}


def _response(model: str) -> LLMResponse:
    return LLMResponse(
        content=f"ok from {model}", model=model, input_tokens=7, output_tokens=3,
        cost_usd=0.0 if model.split("/")[0] in {"ollama", "codex", "gemini_cli"} else 0.001,
        latency_ms=15.0, provider=model.split("/", 1)[0],
    )


async def _run(chain, *, task_cap=None, total_cap=None, spend=9999.0, enforce="hard"):
    """Drive route_and_call with a given chain, cap, over-cap spend, enforce mode."""
    caps = {}
    if task_cap is not None:
        caps["code"] = task_cap
    if total_cap is not None:
        caps["_total"] = total_cap
    repo_cfg = RepoConfig(daily_caps=caps, enforce=enforce)

    route_log = MagicMock()
    mock_log = MagicMock()
    mock_log.bind.return_value = route_log
    tracker = MagicMock()
    tracker.is_healthy.return_value = True

    with ExitStack() as es:
        p = es.enter_context
        p(patch("chuzom.router.get_config", return_value=_Cfg()))
        p(patch("chuzom.router.get_tracker", return_value=tracker))
        p(patch("chuzom.router.log", mock_log))
        p(patch("chuzom.router._native_notify", lambda *a, **k: None))
        p(patch("chuzom.repo_config.effective_config", return_value=repo_cfg))
        p(patch("chuzom.router.cost.get_monthly_spend", new_callable=AsyncMock, return_value=0.0))
        p(patch("chuzom.router.cost.get_daily_spend", new_callable=AsyncMock, return_value=spend))
        p(patch("chuzom.router.cost.get_daily_spend_by_task_type", new_callable=AsyncMock, return_value=spend))
        p(patch("chuzom.policy.load_org_policy", return_value=None))
        p(patch("chuzom.router.cost.log_usage", new_callable=AsyncMock))
        p(patch("chuzom.router.reserve_envelope", new_callable=AsyncMock, return_value=(None, True, None)))
        p(patch("chuzom.router.commit_envelope", new_callable=AsyncMock))
        p(patch("chuzom.router.release_envelope", new_callable=AsyncMock))
        p(patch("chuzom.semantic_cache.check", new_callable=AsyncMock, return_value=None))
        p(patch("chuzom.semantic_cache.store", new_callable=AsyncMock))
        p(patch("chuzom.router._build_and_filter_chain", new_callable=AsyncMock, return_value=list(chain)))
        p(patch("chuzom.router.providers.call_llm", new_callable=AsyncMock,
                side_effect=lambda model, messages, **kw: _response(model)))
        from chuzom.router import route_and_call
        return await route_and_call(TaskType.CODE, "hello", profile=RoutingProfile.BALANCED)


@pytest.mark.asyncio
async def test_cap_hit_with_free_available_downgrades_to_free():
    # chain has both paid (openai) and free (ollama); cap exceeded → run free.
    resp = await _run(["openai/gpt-4o", "ollama/qwen2.5:7b"], task_cap=0.0001, enforce="hard")
    assert resp.provider == "ollama", f"expected downgrade to free, got {resp.model}"
    assert resp.cost_usd == 0.0


@pytest.mark.asyncio
async def test_cap_hit_no_free_hard_blocks():
    # chain is paid-only; cap exceeded + hard → BudgetExceededError.
    with pytest.raises(BudgetExceededError, match="daily limit|Daily spend"):
        await _run(["openai/gpt-4o"], task_cap=0.0001, enforce="hard")


@pytest.mark.asyncio
async def test_cap_hit_no_free_smart_falls_through_to_claude():
    # chain is paid-only; cap exceeded + smart → falls through (call proceeds).
    resp = await _run(["openai/gpt-4o"], task_cap=0.0001, enforce="smart")
    assert resp.provider == "openai", "smart mode should fall through, not block"


@pytest.mark.asyncio
async def test_no_cap_allows_paid_provider():
    # No cap configured → the paid provider is NOT downgraded or blocked
    # (paid-only chain so the local-first policy can't mask the result).
    resp = await _run(["openai/gpt-4o"], task_cap=None, total_cap=None)
    assert resp.provider == "openai", "no cap must allow the paid provider"


@pytest.mark.asyncio
async def test_total_cap_also_downgrades():
    # ollama is used (not codex/gemini_cli) because those dispatch via a
    # subprocess backend not covered by the call_llm mock; ollama exercises the
    # same downgrade filter through the mocked provider path.
    resp = await _run(["openai/gpt-4o", "ollama/qwen2.5:7b"], total_cap=0.0001, enforce="hard")
    assert resp.provider == "ollama", f"expected downgrade to free ollama, got {resp.model}"
