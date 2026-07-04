from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chuzom.codex_agent import CodexResult
from chuzom.router import _build_and_filter_chain, route_and_call
from chuzom.types import Complexity, LLMResponse, RoutingProfile, TaskType


class _NoPins:
    block_providers: list[str] = []
    block_models: list[str] = []
    allow_models: list[str] = []
    agentic_model = ""

    def model_override(self, task_type: str) -> None:
        return None

    def provider_override(self, task_type: str) -> None:
        return None


class _AuditConfig:
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

    def __init__(
        self,
        *,
        available_providers: set[str],
        ollama_models: list[str] | None = None,
    ) -> None:
        self.available_providers = available_providers
        self._ollama_models = ollama_models or []

    def all_ollama_models(self) -> list[str]:
        return list(self._ollama_models)

    def all_openai_compat_models(self) -> list[str]:
        return []


@pytest.fixture
def chain_building_isolated(monkeypatch):
    monkeypatch.setenv("CHUZOM_BANDIT", "off")
    monkeypatch.setattr("chuzom.dynamic_routing.get_dynamic_model_chain", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("chuzom.router.get_repo_config", lambda: _NoPins())
    monkeypatch.setattr("chuzom.claude_usage.get_claude_pressure", lambda: 0.2)
    monkeypatch.setattr("chuzom.router.is_codex_available", lambda: True)
    monkeypatch.setattr("chuzom.router.is_gemini_cli_available", lambda: False)
    monkeypatch.setattr("chuzom.cost.get_model_failure_rates", AsyncMock(return_value={}))
    monkeypatch.setattr("chuzom.cost.get_model_latency_stats", AsyncMock(return_value={}))
    monkeypatch.setattr("chuzom.cost.get_model_acceptance_scores", AsyncMock(return_value={}))
    monkeypatch.setattr("chuzom.policy.load_org_policy", lambda: None)


async def _chain(task_type: TaskType, config: _AuditConfig) -> list[str]:
    return await _build_and_filter_chain(
        task_type,
        RoutingProfile.BALANCED,
        None,
        Complexity.MODERATE,
        Complexity.MODERATE,
        config,
    )


@pytest.mark.asyncio
async def test_mixed_environment_does_not_collapse_all_tasks_to_one_head(
    chain_building_isolated,
):
    config = _AuditConfig(
        available_providers={"openai", "gemini", "ollama"},
        ollama_models=[
            "ollama/qwen2.5-coder:7b",
            "ollama/hermes3:8b",
            "ollama/mistral-nemo:latest",
        ],
    )

    heads = {
        task: (await _chain(task, config))[0]
        for task in (TaskType.QUERY, TaskType.CODE, TaskType.ANALYZE)
    }

    assert len(set(heads.values())) >= 2, heads


@pytest.mark.asyncio
async def test_codex_failure_falls_through_and_logs_routing_fallback(
    temp_db,
    monkeypatch,
):
    config = _AuditConfig(available_providers={"openai"})
    route_log = MagicMock()
    mock_log = MagicMock()
    mock_log.bind.return_value = route_log

    async def successful_call(model, messages, **kwargs):
        return LLMResponse(
            content="fallback ok",
            model=model,
            input_tokens=8,
            output_tokens=3,
            cost_usd=0.001,
            latency_ms=20.0,
            provider="openai",
        )

    tracker = MagicMock()
    tracker.is_healthy.return_value = True

    with (
        patch("chuzom.router.get_config", return_value=config),
        patch("chuzom.router._build_and_filter_chain", new_callable=AsyncMock) as build_chain,
        patch("chuzom.router.run_codex", new_callable=AsyncMock) as run_codex,
        patch("chuzom.router.providers.call_llm", new_callable=AsyncMock, side_effect=successful_call) as call_llm,
        patch("chuzom.router.get_tracker", return_value=tracker),
        patch("chuzom.router.log", mock_log),
        patch("chuzom.router._native_notify", lambda *_args, **_kwargs: None),
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
        build_chain.return_value = ["codex/gpt-5.5", "openai/gpt-4o-mini"]
        run_codex.return_value = CodexResult(
            content="codex exploded",
            model="gpt-5.5",
            exit_code=1,
            duration_sec=0.01,
        )

        response = await route_and_call(
            TaskType.CODE,
            "write a tiny function",
            profile=RoutingProfile.BALANCED,
        )

    assert response.content == "fallback ok"
    assert run_codex.await_count == 1
    assert call_llm.await_count == 1
    fallback_events = [
        call for call in route_log.warning.call_args_list
        if call.args and call.args[0] == "routing_fallback"
    ]
    assert fallback_events
    assert fallback_events[0].kwargs["model"] == "codex/gpt-5.5"
