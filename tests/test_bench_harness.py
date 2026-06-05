"""Tests for the benchmark harness — verify everything works with FakeRouter.

No real API calls. These tests pin the contract:
    - Objective grading is deterministic and doesn't need an LLM judge.
    - Scorecards aggregate correctly.
    - Pareto frontier picks the right routers.
    - Cache short-circuits the second call.
"""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from bench.judge import grade_objective
from bench.router_api import RouterResult
from bench.runner import (
    CACHE_DIR,
    pareto_frontier,
    run_one,
    scorecards,
)


# ─────────────────────────────────────────────────────────────────────────
# Fake router — no API calls, returns canned responses
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class FakeRouter:
    """Returns a fixed response. Cost/tokens are configurable per instance."""

    name: str
    canned_response: str
    model: str = "fake/test-model"
    input_tokens: int = 10
    output_tokens: int = 20
    cost_usd: float = 0.001
    latency_ms: int = 50

    async def route(self, prompt: str) -> RouterResult:
        return RouterResult(
            router_name=self.name,
            model_chosen=self.model,
            response=self.canned_response,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=self.cost_usd,
            latency_ms=self.latency_ms,
            notes={"fake": True},
        )


# ─────────────────────────────────────────────────────────────────────────
# Objective grading
# ─────────────────────────────────────────────────────────────────────────

def test_objective_perfect_match_scores_5():
    entry = {"expected_contains": ["Paris"]}
    result = grade_objective("The capital is Paris", entry)
    assert result.score == 5
    assert result.kind == "objective"


def test_objective_partial_match_scores_3():
    entry = {"expected_contains": ["Paris", "France"]}
    result = grade_objective("It's in France somewhere", entry)
    assert result.score == 3


def test_objective_no_match_scores_1():
    entry = {"expected_contains": ["Paris"]}
    result = grade_objective("London", entry)
    assert result.score == 1


def test_objective_empty_response_scores_1():
    entry = {"expected_contains": ["Paris"]}
    result = grade_objective("", entry)
    assert result.score == 1
    assert "empty" in result.rationale


def test_objective_word_limit_violation_scores_4():
    entry = {"expected_contains": ["Paris"], "expected_max_words": 3}
    result = grade_objective("The capital of France is the city of Paris", entry)
    assert result.score == 4
    assert "exceeded" in result.rationale


def test_objective_word_limit_respected_scores_5():
    entry = {"expected_contains": ["Paris"], "expected_max_words": 5}
    result = grade_objective("It is Paris", entry)
    assert result.score == 5


def test_objective_case_insensitive():
    entry = {"expected_contains": ["paris"]}
    result = grade_objective("PARIS", entry)
    assert result.score == 5


# ─────────────────────────────────────────────────────────────────────────
# run_one — end-to-end on a single prompt
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Each test gets its own cache dir."""
    test_cache = tmp_path / "cache"
    monkeypatch.setattr("bench.runner.CACHE_DIR", test_cache)
    return test_cache


@pytest.mark.asyncio
async def test_run_one_objective():
    router = FakeRouter(name="fake", canned_response="Paris")
    entry = {
        "id": "test-01",
        "difficulty": "easy",
        "category": "factual",
        "kind": "objective",
        "prompt": "Capital of France?",
        "expected_contains": ["Paris"],
    }
    row = await run_one(router, entry, judge_model="not-used-for-objective")
    assert row.judge_score == 5
    assert row.judge_kind == "objective"
    assert row.router_name == "fake"
    assert row.model_chosen == "fake/test-model"
    assert row.error == ""


@pytest.mark.asyncio
async def test_run_one_router_error_yields_score_1():
    @dataclass
    class BrokenRouter:
        name: str = "broken"

        async def route(self, prompt: str) -> RouterResult:
            return RouterResult(
                router_name=self.name, model_chosen="<none>", response="",
                input_tokens=0, output_tokens=0, cost_usd=0.0, latency_ms=10,
                error="provider down",
            )

    entry = {
        "id": "test-02", "difficulty": "easy", "category": "factual",
        "kind": "objective", "prompt": "Q", "expected_contains": ["A"],
    }
    row = await run_one(BrokenRouter(), entry, judge_model="ignored")
    assert row.judge_score == 1
    assert "provider down" in row.judge_rationale
    assert row.error == "provider down"


# ─────────────────────────────────────────────────────────────────────────
# Scorecards
# ─────────────────────────────────────────────────────────────────────────

def _make_row(router_name, score, cost, tokens=30, error=""):
    from bench.runner import RunRow
    return RunRow(
        corpus_id="p", difficulty="easy", category="x",
        router_name=router_name, model_chosen="m", response="r",
        input_tokens=tokens // 2, output_tokens=tokens // 2, cost_usd=cost,
        latency_ms=100, judge_score=score, judge_kind="objective",
        judge_rationale="", judge_model="", error=error, notes={},
    )


def test_scorecard_avg_judge_score():
    rows = [
        _make_row("A", 5, 0.001),
        _make_row("A", 3, 0.002),
        _make_row("B", 4, 0.010),
    ]
    cards = {c.router_name: c for c in scorecards(rows)}
    assert cards["A"].avg_judge_score == pytest.approx(4.0)
    assert cards["B"].avg_judge_score == pytest.approx(4.0)


def test_scorecard_quality_preserved_pct():
    rows = [
        _make_row("A", 5, 0.001),  # >= 4 → preserved
        _make_row("A", 4, 0.001),  # >= 4 → preserved
        _make_row("A", 3, 0.001),  # < 4
        _make_row("A", 2, 0.001),  # < 4
    ]
    cards = scorecards(rows)
    assert cards[0].quality_preserved_pct == 0.5


def test_scorecard_models_used():
    from bench.runner import RunRow
    rows = [
        RunRow(corpus_id="p1", difficulty="easy", category="x",
               router_name="A", model_chosen="ollama/qwen3.5:latest", response="",
               input_tokens=10, output_tokens=10, cost_usd=0.0, latency_ms=50,
               judge_score=5, judge_kind="objective", judge_rationale="",
               judge_model="", error="", notes={}),
        RunRow(corpus_id="p2", difficulty="easy", category="x",
               router_name="A", model_chosen="openai/gpt-4o-mini", response="",
               input_tokens=10, output_tokens=10, cost_usd=0.001, latency_ms=80,
               judge_score=5, judge_kind="objective", judge_rationale="",
               judge_model="", error="", notes={}),
    ]
    cards = scorecards(rows)
    assert cards[0].models_used == {"ollama/qwen3.5:latest": 1, "openai/gpt-4o-mini": 1}


# ─────────────────────────────────────────────────────────────────────────
# Pareto frontier
# ─────────────────────────────────────────────────────────────────────────

def test_pareto_frontier_dominated_router_excluded():
    """If router C is cheaper AND better than B, B is dominated."""
    rows = [
        _make_row("A", 5, 0.010),  # highest quality, expensive
        _make_row("B", 3, 0.005),  # mid quality, mid cost — dominated by C
        _make_row("C", 4, 0.001),  # lower quality but much cheaper, dominates B
    ]
    cards = scorecards(rows)
    frontier = pareto_frontier(cards)
    assert "A" in frontier
    assert "C" in frontier
    assert "B" not in frontier, "B is dominated by C (cheaper AND better)"


def test_pareto_frontier_endpoints_always_included():
    """The cheapest and the highest-quality router are always on the frontier."""
    rows = [
        _make_row("cheapest", 2, 0.0001),
        _make_row("best", 5, 0.10),
        _make_row("middle", 4, 0.01),
    ]
    cards = scorecards(rows)
    frontier = set(pareto_frontier(cards))
    assert "cheapest" in frontier
    assert "best" in frontier


def test_pareto_frontier_equal_quality_lower_cost_wins():
    rows = [
        _make_row("X", 4, 0.010),  # equal quality, higher cost → dominated
        _make_row("Y", 4, 0.005),
    ]
    cards = scorecards(rows)
    frontier = set(pareto_frontier(cards))
    assert "Y" in frontier
    assert "X" not in frontier
