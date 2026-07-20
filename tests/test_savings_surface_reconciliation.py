"""RETROSPECTIVE B-6 — the savings surfaces must reconcile.

Three surfaces reported "savings" and disagreed by ~10-25x:
  1. SessionStart weekly digest (session-start.py) — priced against SONNET.
  2. SessionEnd banner (session-end.py) — printed the ALL-TIME total but
     labelled it "saved this week".
  3. llm_savings dashboard (cost.get_savings_by_period) — the only correct one.

The fixes (a) unify the baseline onto the latest Opus everywhere, (b) kill the
all-time-as-weekly mislabel, and (c) keep each window truthfully labelled. These
tests pin the aggregate invariants at runtime and guard the two banner sources
against the specific regressions that caused the divergence. (Full end-to-end
replay of all three surfaces over realistic sessions lives in bench/experiments.)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import chuzom.config as config_module
import pytest
from chuzom import cost
from chuzom.types import LLMResponse, RoutingProfile, TaskType

_SRC = Path(__file__).resolve().parents[1] / "src" / "chuzom"


# ── Runtime aggregate invariants ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_baseline_avoided_aliases_legacy_saved(temp_db):
    config_module._config = None
    free = LLMResponse(content="x", model="ollama/qwen3", input_tokens=1000,
                       output_tokens=2000, cost_usd=0.0, latency_ms=10, provider="ollama")
    await cost.log_usage(free, TaskType.QUERY, RoutingProfile.BUDGET)
    for bucket in (await cost.get_savings_by_period()).values():
        # The clearer name must equal the back-compat field for every window.
        assert bucket["baseline_avoided_usd"] == bucket["saved_usd"]


@pytest.mark.asyncio
async def test_window_nesting_today_le_week_le_month_le_all(temp_db):
    config_module._config = None
    now = LLMResponse(content="x", model="ollama/qwen3", input_tokens=1000,
                      output_tokens=2000, cost_usd=0.0, latency_ms=10, provider="ollama")
    await cost.log_usage(now, TaskType.QUERY, RoutingProfile.BUDGET)  # creates schema

    # An older row (40 days ago) lands ONLY in all-time.
    conn = sqlite3.connect(temp_db)
    conn.execute(
        """INSERT INTO usage
           (timestamp, model, provider, task_type, profile,
            input_tokens, output_tokens, cost_usd, latency_ms, success)
           VALUES (datetime('now','-40 days'), 'ollama/qwen3', 'ollama', 'query',
                   'budget', 1000, 2000, 0.0, 10, 1)""",
    )
    conn.commit()
    conn.close()

    d = await cost.get_savings_by_period()
    t = d["today"]["baseline_avoided_usd"]
    w = d["week"]["baseline_avoided_usd"]
    m = d["month"]["baseline_avoided_usd"]
    a = d["all_time"]["baseline_avoided_usd"]
    assert t <= w <= m <= a
    assert a > m  # the 40-day-old row is in all-time but not this month


# ── Source guards on the two banner surfaces ────────────────────────────────

def test_sessionend_no_alltime_labelled_weekly():
    txt = (_SRC / "hooks" / "session-end.py").read_text()
    # The exact regression: summing the "all time" row into a "saved this week"
    # string. Must not reappear.
    assert 'd[0] == "all time"' not in txt or "saved this week" not in txt, (
        "session-end must not label an all-time total 'saved this week'"
    )
    assert 'd[0] == "this week"' in txt  # the weekly fallback now reads the weekly bucket


def test_sessionstart_digest_uses_opus_not_sonnet_baseline():
    txt = (_SRC / "hooks" / "session-start.py").read_text()
    # The Sonnet-priced baseline that made the weekly digest disagree is gone.
    assert "_SONNET_IN_PER_M" not in txt
    assert "_SONNET_OUT_PER_M" not in txt
    # And it now sources the Opus host rate (with a documented fallback).
    assert "_HOST_INPUT_PER_M" in txt or "_HOST_IN_PER_M_FALLBACK" in txt
