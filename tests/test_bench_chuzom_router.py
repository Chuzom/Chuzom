"""#5 — the benchmark's ChuzomRouter drives the REAL router, not a stub.

Verifies the wiring maps `classify` + `route_and_call` onto a `RouterResult`
faithfully, suppresses the ledger, and never fabricates routing overhead. The
real router is mocked so CI makes no API calls.
"""
from __future__ import annotations

import chuzom.classify as classify_mod
import chuzom.router as router_mod
import pytest

from bench.routers import ChuzomRouter
from chuzom.classify import ClassifySignal
from chuzom.types import Complexity, LLMResponse, TaskType


@pytest.mark.asyncio
async def test_chuzom_router_wires_classify_and_route_and_call(monkeypatch):
    captured = {}

    async def fake_classify(prompt, allow_llm=True):
        captured["allow_llm"] = allow_llm
        return ClassifySignal(TaskType.CODE, Complexity.MODERATE, 10, True, method="heuristic")

    async def fake_route_and_call(task_type, prompt, **kw):
        captured["task_type"] = task_type
        captured["complexity_hint"] = kw.get("complexity_hint")
        captured["suppress_ledger"] = kw.get("suppress_ledger")
        return LLMResponse(
            content="def f(): pass", model="qwen3", input_tokens=120, output_tokens=40,
            cost_usd=0.0, latency_ms=15.0, provider="ollama",
            chain_attempts=["ollama/qwen3"], cache_hit=False,
        )

    monkeypatch.setattr(classify_mod, "classify", fake_classify)
    monkeypatch.setattr(router_mod, "route_and_call", fake_route_and_call)

    r = await ChuzomRouter().route("refactor the parser module")

    # It routed the REAL way: classify → route_and_call, ledger suppressed.
    assert captured["task_type"] == TaskType.CODE
    assert captured["complexity_hint"] == Complexity.MODERATE
    assert captured["suppress_ledger"] is True
    assert captured["allow_llm"] is True

    # Faithful mapping onto the RouterResult.
    assert r.error == ""
    assert r.model_chosen == "ollama/qwen3"
    assert r.response == "def f(): pass"
    assert (r.input_tokens, r.output_tokens) == (120, 40)
    assert r.cost_usd == 0.0
    assert r.notes["classification_method"] == "heuristic"
    assert r.notes["task_type"] == "code"
    assert r.notes["chain_attempts"] == ["ollama/qwen3"]
    # Overhead is never fabricated when classify() doesn't report it.
    assert "routing_overhead_usd" not in r.notes


@pytest.mark.asyncio
async def test_chuzom_router_keeps_already_qualified_model_id(monkeypatch):
    async def fake_classify(prompt, allow_llm=True):
        return ClassifySignal(TaskType.QUERY, Complexity.SIMPLE, 9, True)

    async def fake_route_and_call(task_type, prompt, **kw):
        return LLMResponse(content="hi", model="openai/gpt-4o-mini", input_tokens=10,
                           output_tokens=5, cost_usd=0.0001, latency_ms=8.0, provider="openai")

    monkeypatch.setattr(classify_mod, "classify", fake_classify)
    monkeypatch.setattr(router_mod, "route_and_call", fake_route_and_call)

    r = await ChuzomRouter().route("what is a foreign key")
    # model already provider-qualified → not double-prefixed.
    assert r.model_chosen == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_chuzom_router_error_path_is_a_failed_row(monkeypatch):
    async def boom(prompt, allow_llm=True):
        raise RuntimeError("classifier down")

    monkeypatch.setattr(classify_mod, "classify", boom)
    r = await ChuzomRouter().route("x")
    assert r.failed
    assert r.model_chosen == "<exhausted>"
    assert "classifier down" in r.error
    assert r.cost_usd == 0.0
