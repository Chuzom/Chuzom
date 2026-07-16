"""R4 / G-BENCH-1 — benchmark guard + corpus integrity.

The guard is the mechanism that keeps the quality×cost frontier honest and fresh:
it fails CI when the primary router's quality drops below a floor, or when the
newest results have gone stale. These are pure-function tests (no model calls),
plus a corpus-integrity check that the expanded corpus is well-formed and large.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from bench.guard import (
    check_freshness,
    check_regression,
    results_age_days,
)
from bench.runner import RouterScorecard, load_full_corpus


def _card(router: str, quality_preserved: float) -> RouterScorecard:
    return RouterScorecard(
        router_name=router,
        prompts_attempted=50,
        prompts_succeeded=50,
        avg_input_tokens=100.0,
        avg_output_tokens=50.0,
        avg_total_tokens=150.0,
        total_cost_usd=0.0,
        avg_cost_usd=0.0,
        avg_latency_ms=1000.0,
        avg_judge_score=4.2,
        quality_preserved_pct=quality_preserved,
        models_used={},
    )


# ── regression check ─────────────────────────────────────────────────────────

def test_regression_passes_above_floor():
    ok, msg = check_regression([_card("chuzom", 0.90)], quality_floor=0.80)
    assert ok, msg


def test_regression_fails_below_floor():
    ok, msg = check_regression([_card("chuzom", 0.70)], quality_floor=0.80)
    assert not ok
    assert "quality" in msg.lower()


def test_regression_fails_when_router_missing():
    ok, msg = check_regression([_card("always-cheap", 0.99)], router="chuzom")
    assert not ok
    assert "no scorecard" in msg.lower()


# ── freshness check ──────────────────────────────────────────────────────────

def _write_result(results_dir: Path, name: str, age_days: float) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    p = results_dir / name
    p.write_text("[]")
    mtime = time.time() - age_days * 86400
    os.utime(p, (mtime, mtime))
    return p


def test_freshness_passes_for_recent_results(tmp_path):
    _write_result(tmp_path, "20260716-000000.json", age_days=2)
    ok, msg = check_freshness(tmp_path, max_age_days=14)
    assert ok, msg


def test_freshness_fails_for_stale_results(tmp_path):
    _write_result(tmp_path, "old.json", age_days=45)
    ok, msg = check_freshness(tmp_path, max_age_days=14)
    assert not ok
    assert "stale" in msg.lower()


def test_freshness_fails_with_no_results(tmp_path):
    ok, msg = check_freshness(tmp_path, max_age_days=14)
    assert not ok
    assert "no benchmark results" in msg.lower()


def test_results_age_uses_newest_file(tmp_path):
    _write_result(tmp_path, "old.json", age_days=40)
    _write_result(tmp_path, "new.json", age_days=1)
    age = results_age_days(tmp_path)
    assert age is not None and age < 2  # newest wins


# ── corpus integrity ─────────────────────────────────────────────────────────

def test_corpus_is_large_and_well_formed():
    corpus = load_full_corpus()
    # R4 acceptance: grow the corpus past 50 prompts.
    assert len(corpus) >= 50, f"corpus too small: {len(corpus)}"

    ids = [e["id"] for e in corpus]
    assert len(ids) == len(set(ids)), "duplicate corpus ids"

    difficulties = {e["difficulty"] for e in corpus}
    assert {"easy", "moderate", "hard"} <= difficulties, difficulties

    for e in corpus:
        assert e.get("prompt"), e["id"]
        kind = e.get("kind")
        assert kind in ("objective", "subjective"), e["id"]
        if kind == "objective":
            assert e.get("expected_contains"), f"{e['id']} objective needs expected_contains"
        else:
            assert e.get("judge_criteria"), f"{e['id']} subjective needs judge_criteria"


def test_corpus_jsonl_files_are_valid_json():
    corpus_dir = Path(__file__).resolve().parents[1] / "bench" / "corpus"
    for tier in ("easy", "moderate", "hard"):
        path = corpus_dir / f"{tier}.jsonl"
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if line.strip():
                json.loads(line)  # raises on malformed line
