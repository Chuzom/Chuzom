"""CF-1 integration: a real route_and_call() emits exactly one v2 completion row.

The unit tests in test_route_ledger_v2.py prove the ledger *logic*; this proves the
*wiring* — that driving route_and_call through the dispatch loop with a mocked provider
actually appends a v2 row with honest completion semantics (§18 CF-1: "every top-level
route emits exactly one v2 ledger row"), and that suppress_ledger=True suppresses it.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chuzom.routing_quality import load_records
from chuzom.types import LLMResponse, RoutingProfile, TaskType


class _Cfg:
    chuzom_claude_subscription = False
    chuzom_gemini_subscription = False
    chuzom_claw_code = False
    chuzom_routing_policy = "balanced"
    chuzom_agentic_model = ""
    chuzom_profile = RoutingProfile.BALANCED
    chuzom_monthly_budget = 0.0
    chuzom_daily_spend_limit = 0.0
    chuzom_escalate_above = 0.0
    chuzom_hard_stop_above = 0.0
    codex_daily_limit = 1000
    compaction_mode = "off"
    compaction_threshold = 4000
    prompt_cache_enabled = False
    prompt_cache_min_tokens = 1024
    context_enabled = False
    caveman_mode = "off"
    available_providers = {"openai"}

    def all_ollama_models(self):
        return []

    def all_openai_compat_models(self):
        return []


async def _run(prompt: str, ledger, monkeypatch, *, suppress: bool):
    monkeypatch.setenv("CHUZOM_ROUTING_LEDGER", str(ledger))
    monkeypatch.setenv("CHUZOM_BANDIT", "off")

    async def successful_call(model, messages, **kwargs):
        return LLMResponse(content="ok", model=model, input_tokens=10,
                           output_tokens=5, cost_usd=0.001, latency_ms=12.0,
                           provider="openai")

    tracker = MagicMock()
    tracker.is_healthy.return_value = True
    mock_log = MagicMock()
    mock_log.bind.return_value = MagicMock()

    from chuzom.router import route_and_call
    with (
        patch("chuzom.router.get_config", return_value=_Cfg()),
        patch("chuzom.router._build_and_filter_chain", new_callable=AsyncMock,
              return_value=["openai/gpt-4o"]),
        patch("chuzom.router.providers.call_llm", new_callable=AsyncMock,
              side_effect=successful_call),
        patch("chuzom.router.get_tracker", return_value=tracker),
        patch("chuzom.router.log", mock_log),
        patch("chuzom.router._native_notify", lambda *a, **k: None),
        patch("chuzom.router.cost.get_monthly_spend", new_callable=AsyncMock, return_value=0.0),
        patch("chuzom.router.cost.get_daily_spend", new_callable=AsyncMock, return_value=0.0),
        patch("chuzom.router.cost.get_daily_spend_by_task_type", new_callable=AsyncMock, return_value=0.0),
        patch("chuzom.router.cost.log_usage", new_callable=AsyncMock),
        patch("chuzom.router.reserve_envelope", new_callable=AsyncMock, return_value=(None, True, None)),
        patch("chuzom.router.commit_envelope", new_callable=AsyncMock),
        patch("chuzom.router.release_envelope", new_callable=AsyncMock),
        patch("chuzom.semantic_cache.check", new_callable=AsyncMock, return_value=None),
        patch("chuzom.semantic_cache.store", new_callable=AsyncMock),
    ):
        return await route_and_call(
            TaskType.QUERY, prompt, profile=RoutingProfile.BALANCED,
            suppress_ledger=suppress,
        )


@pytest.mark.asyncio
async def test_route_and_call_emits_one_completion_row(temp_db, tmp_path, monkeypatch):
    ledger = tmp_path / "rq.jsonl"
    resp = await _run("what is the capital of France?", ledger, monkeypatch, suppress=False)
    assert resp.content == "ok"
    rows = [r for r in load_records(str(ledger)) if not r.get("_invalid")]
    assert len(rows) == 1, f"expected exactly one ledger row, got {len(rows)}"
    r = rows[0]
    assert r["schema_version"] == 2
    assert r["route_kind"] == "completion"
    assert r["route_succeeded"] is True
    # honesty: no tools, no verification → None (never True)
    assert r["tool_execution_attempted"] is False and r["tool_execution_succeeded"] is None
    assert r["verification_attempted"] is False and r["verification_passed"] is None
    assert r["final_model"] == "openai/gpt-4o"
    assert r["final_tier"] == 2  # mid external


@pytest.mark.asyncio
async def test_suppress_ledger_emits_no_row(temp_db, tmp_path, monkeypatch):
    ledger = tmp_path / "rq.jsonl"
    await _run("internal planner call", ledger, monkeypatch, suppress=True)
    rows = [r for r in load_records(str(ledger)) if not r.get("_invalid")]
    assert rows == [], "suppress_ledger=True must not emit a top-level row"
