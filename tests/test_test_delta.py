"""Tests for the quota test-delta framework.

Pins three contracts:

1. Snapshot → save → load round-trips cleanly. The JSON shape on disk
   is the schema future clients will rely on.
2. Diff arithmetic is correct — `added_*` fields are after minus before,
   never negative (the framework's job is to report new activity, not
   rollback). Tier histograms only surface buckets that grew.
3. The Opus-baseline counterfactual + savings math match the
   $15/$75 per-million-tokens reference pricing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from chuzom.test_delta import (
    OPUS_INPUT_PER_M,
    OPUS_OUTPUT_PER_M,
    Snapshot,
    diff,
    load_snapshot,
    save_snapshot,
    snapshot,
)


def _seed_db(tmp_path: Path, *, routing_rows=(), claude_rows=(), usage_rows=()) -> Path:
    """Create a usage.db with optional pre-seeded rows."""
    db = tmp_path / "usage.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute("""
            CREATE TABLE routing_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, prompt_hash TEXT, task_type TEXT,
                profile TEXT, complexity TEXT, final_model TEXT,
                final_provider TEXT, input_tokens INTEGER,
                output_tokens INTEGER, cost_usd REAL,
                reason_code TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE claude_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, model TEXT, tokens_used INTEGER,
                complexity TEXT, cost_saved_usd REAL
            )
        """)
        conn.execute("""
            CREATE TABLE usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, model TEXT, provider TEXT, task_type TEXT,
                profile TEXT, input_tokens INTEGER, output_tokens INTEGER,
                cost_usd REAL, success INTEGER
            )
        """)
        conn.executemany(
            "INSERT INTO routing_decisions (timestamp, task_type, complexity, "
            "final_model, input_tokens, output_tokens, cost_usd, reason_code) "
            "VALUES (?,?,?,?,?,?,?,?)",
            routing_rows,
        )
        conn.executemany(
            "INSERT INTO claude_usage (timestamp, model, tokens_used, complexity, "
            "cost_saved_usd) VALUES (?,?,?,?,?)",
            claude_rows,
        )
        conn.executemany(
            "INSERT INTO usage (timestamp, model, input_tokens, output_tokens, "
            "cost_usd, success) VALUES (?,?,?,?,?,?)",
            usage_rows,
        )
        conn.commit()
    finally:
        conn.close()
    return db


# ── Snapshot round-trip ─────────────────────────────────────────────────


def test_snapshot_of_missing_db_is_empty(tmp_path):
    snap = snapshot(tmp_path / "nope.db")
    assert snap.routing.rows == 0
    assert snap.claude.rows == 0
    assert snap.usage.rows == 0


def test_snapshot_save_load_roundtrip(tmp_path):
    db = _seed_db(tmp_path, routing_rows=[
        ("2026-06-06 17:00", "query", "simple", "gemini-flash", 10, 20, 0.001, None),
    ])
    snap = snapshot(db)
    path = save_snapshot(snap, root=tmp_path / "snaps")
    loaded = load_snapshot(snap.id, root=tmp_path / "snaps")
    assert loaded.routing.rows == 1
    assert loaded.routing.by_tier.get("simple") == 1
    assert loaded.routing.cost_usd == pytest.approx(0.001)


def test_snapshot_excludes_sidecar_backfill(tmp_path):
    """Backfilled sidecars don't reflect real traffic — must be excluded."""
    db = _seed_db(tmp_path, routing_rows=[
        ("2026-06-06 17:00", "query", "simple", "gemini-flash", 10, 20, 0.001, None),
        ("2026-06-06 16:00", "query", "simple", "gemini-flash", 5, 8, 0.0,
         "sidecar_backfill"),
    ])
    snap = snapshot(db)
    assert snap.routing.rows == 1  # backfill row excluded


# ── Diff arithmetic ─────────────────────────────────────────────────────


def test_diff_counts_only_new_rows(tmp_path):
    db = _seed_db(tmp_path, routing_rows=[
        ("2026-06-06 17:00", "query", "simple", "gemini-flash", 10, 20, 0.001, None),
    ])
    before = snapshot(db)

    # Add a new row, take a fresh snapshot
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO routing_decisions (timestamp, task_type, complexity, "
        "final_model, input_tokens, output_tokens, cost_usd) "
        "VALUES ('2026-06-06 17:05','query','moderate','sonnet',100,200,0.05)"
    )
    conn.commit()
    conn.close()

    after = snapshot(db)
    report = diff(before, after)
    assert report.routing.added_rows == 1
    assert report.routing.added_cost_usd == pytest.approx(0.05)
    assert report.routing.added_input_tokens == 100
    assert report.routing.added_output_tokens == 200


def test_diff_tier_histogram_surfaces_only_growth(tmp_path):
    """If a bucket was 3 before and 3 after, it must NOT appear in
    ``by_tier_added`` — that report only shows new activity."""
    db = _seed_db(tmp_path, routing_rows=[
        ("t", "query", "simple", "flash", 1, 2, 0.001, None),
        ("t", "query", "moderate", "sonnet", 1, 2, 0.005, None),
    ])
    before = snapshot(db)
    # Add only "simple" rows
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO routing_decisions (timestamp, task_type, complexity, "
        "final_model, input_tokens, output_tokens, cost_usd) "
        "VALUES (?,?,?,?,?,?,?)",
        [("t", "query", "simple", "flash", 1, 2, 0.001),
         ("t", "query", "simple", "flash", 1, 2, 0.001)],
    )
    conn.commit()
    conn.close()
    after = snapshot(db)
    report = diff(before, after)
    assert report.routing.by_tier_added == {"simple": 2}
    assert "moderate" not in report.routing.by_tier_added


# ── Opus-baseline math ─────────────────────────────────────────────────


def test_opus_baseline_pricing_constants():
    """If the constants drift away from the published Opus 4.6 prices,
    every historical delta report becomes incomparable. Pin them."""
    assert OPUS_INPUT_PER_M == 15.0
    assert OPUS_OUTPUT_PER_M == 75.0


def test_opus_baseline_for_routed_uses_token_arithmetic(tmp_path):
    """1_000_000 input tokens + 1_000_000 output tokens at Opus baseline
    = $15 + $75 = $90. Verify the calculation."""
    db = _seed_db(tmp_path)
    before = snapshot(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO routing_decisions (timestamp, task_type, complexity, "
        "final_model, input_tokens, output_tokens, cost_usd) "
        "VALUES ('t','query','simple','flash', 1000000, 1000000, 5.00)"
    )
    conn.commit()
    conn.close()
    after = snapshot(db)
    report = diff(before, after)
    assert report.opus_baseline_for_routed == pytest.approx(90.0)
    assert report.savings_usd_vs_opus == pytest.approx(85.0)


def test_simple_share_proportional(tmp_path):
    db = _seed_db(tmp_path)
    before = snapshot(db)
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO routing_decisions (timestamp, task_type, complexity, "
        "final_model, input_tokens, output_tokens, cost_usd) "
        "VALUES (?,?,?,?,?,?,?)",
        [("t", "query", "simple",    "flash",  10, 20, 0.0001) for _ in range(3)]
        + [("t", "query", "moderate", "sonnet", 10, 20, 0.005)],
    )
    conn.commit()
    conn.close()
    after = snapshot(db)
    report = diff(before, after)
    assert report.simple_share == pytest.approx(0.75)


def test_zero_routed_returns_zero_baseline(tmp_path):
    db = _seed_db(tmp_path)
    before = snapshot(db)
    after = snapshot(db)  # nothing changed
    report = diff(before, after)
    assert report.opus_baseline_for_routed == 0.0
    assert report.savings_usd_vs_opus == 0.0
