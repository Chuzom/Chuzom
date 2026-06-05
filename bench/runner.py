"""Benchmark runner — head-to-head over a corpus.

For each (router, prompt) pair: call the router, grade the response,
persist the row. Routers run sequentially per prompt (to keep load on the
local Ollama instance reasonable); prompts run sequentially across the
corpus (to keep the report ordered).

A response cache at bench/cache/<router>.json prevents re-spending on
re-runs. Cache key = (router_name, prompt_id). Delete the cache files to
force re-runs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from bench.judge import JudgeResult, grade
from bench.router_api import Router, RouterResult


CORPUS_DIR = Path(__file__).parent / "corpus"
CACHE_DIR = Path(__file__).parent / "cache"
RESULTS_DIR = Path(__file__).parent / "results"


@dataclass(frozen=True)
class RunRow:
    """One row of the benchmark output table."""

    corpus_id: str
    difficulty: str  # easy | moderate
    category: str
    router_name: str
    model_chosen: str
    response: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    judge_score: int
    judge_kind: str
    judge_rationale: str
    judge_model: str
    error: str
    notes: dict


def load_corpus(difficulty: str) -> list[dict]:
    """Read a JSONL corpus file. difficulty = 'easy' or 'moderate'."""
    path = CORPUS_DIR / f"{difficulty}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"corpus not found: {path}")
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            entry = json.loads(line)
            entry["difficulty"] = difficulty
            rows.append(entry)
    return rows


def load_full_corpus() -> list[dict]:
    return load_corpus("easy") + load_corpus("moderate")


def _cache_path(router_name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{router_name}.json"


def _load_cache(router_name: str) -> dict[str, dict]:
    path = _cache_path(router_name)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _save_cache(router_name: str, cache: dict[str, dict]) -> None:
    _cache_path(router_name).write_text(json.dumps(cache, indent=2))


def _cache_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


async def _route_with_cache(router: Router, entry: dict) -> RouterResult:
    cache = _load_cache(router.name)
    key = _cache_key(entry["prompt"])
    if key in cache:
        cached = cache[key]
        return RouterResult(**cached)
    result = await router.route(entry["prompt"])
    cache[key] = asdict(result)
    _save_cache(router.name, cache)
    return result


async def run_one(
    router: Router, entry: dict, judge_model: str
) -> RunRow:
    """Route one prompt through one router, judge it, build the row."""
    result = await _route_with_cache(router, entry)
    if result.failed:
        judge = JudgeResult(
            score=1, kind=entry.get("kind", "subjective"),
            rationale=f"router error: {result.error}", judge_model="",
        )
    else:
        judge = await grade(result.response, entry, judge_model=judge_model)
    return RunRow(
        corpus_id=entry["id"],
        difficulty=entry["difficulty"],
        category=entry.get("category", "unknown"),
        router_name=result.router_name,
        model_chosen=result.model_chosen,
        response=result.response,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        judge_score=judge.score,
        judge_kind=judge.kind,
        judge_rationale=judge.rationale,
        judge_model=judge.judge_model,
        error=result.error,
        notes=result.notes,
    )


async def run_benchmark(
    routers: Iterable[Router],
    corpus: list[dict] | None = None,
    judge_model: str = "anthropic/claude-3.5-sonnet",
) -> list[RunRow]:
    """Run every router against every prompt. Returns the flat row list."""
    corpus = corpus or load_full_corpus()
    rows: list[RunRow] = []
    for entry in corpus:
        for router in routers:
            row = await run_one(router, entry, judge_model=judge_model)
            rows.append(row)
    return rows


def save_results(rows: list[RunRow], run_id: str | None = None) -> Path:
    """Persist results to bench/results/<run_id>.json."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    out = RESULTS_DIR / f"{run_id}.json"
    out.write_text(json.dumps([asdict(r) for r in rows], indent=2))
    return out


# ─────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class RouterScorecard:
    router_name: str
    prompts_attempted: int
    prompts_succeeded: int
    avg_input_tokens: float
    avg_output_tokens: float
    avg_total_tokens: float
    total_cost_usd: float
    avg_cost_usd: float
    avg_latency_ms: float
    avg_judge_score: float
    quality_preserved_pct: float  # share of prompts scoring >= 4
    models_used: dict[str, int] = field(default_factory=dict)


def scorecards(rows: list[RunRow]) -> list[RouterScorecard]:
    by_router: dict[str, list[RunRow]] = {}
    for row in rows:
        by_router.setdefault(row.router_name, []).append(row)

    cards = []
    for name, router_rows in by_router.items():
        n = len(router_rows)
        succeeded = [r for r in router_rows if not r.error]
        models_used: dict[str, int] = {}
        for r in router_rows:
            models_used[r.model_chosen] = models_used.get(r.model_chosen, 0) + 1
        cards.append(
            RouterScorecard(
                router_name=name,
                prompts_attempted=n,
                prompts_succeeded=len(succeeded),
                avg_input_tokens=sum(r.input_tokens for r in router_rows) / n,
                avg_output_tokens=sum(r.output_tokens for r in router_rows) / n,
                avg_total_tokens=sum(r.input_tokens + r.output_tokens for r in router_rows) / n,
                total_cost_usd=sum(r.cost_usd for r in router_rows),
                avg_cost_usd=sum(r.cost_usd for r in router_rows) / n,
                avg_latency_ms=sum(r.latency_ms for r in router_rows) / n,
                avg_judge_score=sum(r.judge_score for r in router_rows) / n,
                quality_preserved_pct=sum(1 for r in router_rows if r.judge_score >= 4) / n,
                models_used=models_used,
            )
        )
    return cards


def pareto_frontier(cards: list[RouterScorecard]) -> list[str]:
    """Return the names of routers on the cost/quality Pareto frontier.

    A router is on the frontier if no other router has BOTH lower cost
    AND higher quality. Lower cost is better; higher quality is better.
    """
    frontier = []
    for card in cards:
        dominated = False
        for other in cards:
            if other.router_name == card.router_name:
                continue
            cheaper = other.avg_cost_usd < card.avg_cost_usd
            better = other.avg_judge_score > card.avg_judge_score
            if cheaper and better:
                dominated = True
                break
            equal_cost_better = (
                other.avg_cost_usd <= card.avg_cost_usd
                and other.avg_judge_score > card.avg_judge_score
            )
            equal_quality_cheaper = (
                other.avg_judge_score >= card.avg_judge_score
                and other.avg_cost_usd < card.avg_cost_usd
            )
            if equal_cost_better or equal_quality_cheaper:
                dominated = True
                break
        if not dominated:
            frontier.append(card.router_name)
    return frontier
