"""#28 (Gate 7) + #30 (Gate 19) — lineage token-count schema + additive migration.

The lineage record now carries actual measured input_tokens/output_tokens so
summary.py can compute a REAL token counterfactual instead of estimating from
latency. This pins:
  - round-trip of the new columns through record()/recent();
  - the additive ALTER-TABLE migration of a pre-#28 db (Gate 19: migration tested);
  - summary.collect() using real tokens when present, and falling back to the
    latency estimate (flagged via baseline_estimated_rows) for legacy 0-token rows.
"""
from __future__ import annotations

import sqlite3

import pytest

from chuzom.agents import SessionStore
from chuzom.lineage import LineageStore, make_record
from chuzom.summary import collect


def _rec(model="ollama/qwen3.5:latest", *, input_tokens=0, output_tokens=0, latency_ms=100):
    return make_record(
        host="h", prompt_fingerprint="fp", task_type="query", complexity="simple",
        classifier_method="heuristic", signal_scores={}, fired_decisions=(),
        chain_attempted=(), model_chosen=model, outcome="success",
        latency_ms=latency_ms, cost_usd=0.0,
        input_tokens=input_tokens, output_tokens=output_tokens,
    )


def test_record_roundtrips_token_counts(tmp_path):
    store = LineageStore(db_path=tmp_path / "lineage.db")
    r = _rec(input_tokens=1234, output_tokens=567)
    store.record(r)
    got = [x for x in store.recent(limit=50) if x.get("id") == r.id]
    assert got, "recorded row must be retrievable"
    assert got[0]["input_tokens"] == 1234
    assert got[0]["output_tokens"] == 567


def test_defaults_are_zero_when_not_passed(tmp_path):
    store = LineageStore(db_path=tmp_path / "lineage.db")
    r = _rec()  # no tokens
    store.record(r)
    got = [x for x in store.recent(limit=50) if x.get("id") == r.id][0]
    assert got["input_tokens"] == 0 and got["output_tokens"] == 0


def test_migration_adds_token_columns_to_pre_28_db(tmp_path):
    """Gate 19: a lineage.db created WITHOUT the token columns is migrated
    additively (ALTER TABLE ADD COLUMN ... DEFAULT 0) when LineageStore opens it,
    and a legacy row backfills to 0 — no data loss, no rewrite."""
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE lineage (id TEXT PRIMARY KEY, timestamp REAL, host TEXT, "
        "prompt_fingerprint TEXT, task_type TEXT, complexity TEXT, classifier_method TEXT, "
        "signal_scores TEXT, fired_decisions TEXT, chain_attempted TEXT, model_chosen TEXT, "
        "model_tier TEXT, inversion TEXT, outcome TEXT, latency_ms INTEGER, cost_usd REAL, "
        "notes TEXT, agent_id TEXT, session_id TEXT, step_index INTEGER, "
        "parent_session_id TEXT, framework TEXT)"
    )
    conn.execute(
        "INSERT INTO lineage (id, timestamp, host, model_chosen, model_tier, inversion, "
        "outcome, latency_ms, cost_usd) VALUES "
        "('legacy1', 1.0, 'h', 'ollama/x', 'local', 'none', 'success', 400, 0.0)"
    )
    conn.commit()
    conn.close()

    before = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(lineage)")}
    assert "input_tokens" not in before and "output_tokens" not in before

    LineageStore(db_path=db)  # opening triggers the additive migration

    after = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(lineage)")}
    assert {"input_tokens", "output_tokens"} <= after, "migration must add both columns"
    # Legacy row survives and backfills to the DEFAULT 0.
    row = dict(zip(
        [c[1] for c in sqlite3.connect(db).execute("PRAGMA table_info(lineage)")],
        sqlite3.connect(db).execute("SELECT * FROM lineage WHERE id='legacy1'").fetchone(),
    ))
    assert row["input_tokens"] == 0 and row["output_tokens"] == 0


def test_summary_uses_real_tokens_when_present(tmp_path):
    """collect() over rows with REAL tokens computes the baseline from them and
    marks the baseline fully measured (baseline_estimated_rows == 0)."""
    ls = LineageStore(db_path=tmp_path / "lineage.db")
    ls.record(_rec(input_tokens=1000, output_tokens=500))
    ls.record(_rec(input_tokens=2000, output_tokens=800))
    ss = SessionStore(db_path=tmp_path / "sessions.db")
    data = collect(lineage_store=ls, session_store=ss)
    assert data.baseline_estimated_rows == 0, "all rows had real tokens — no estimate"
    assert data.baseline_cost_usd > 0


def test_summary_falls_back_to_estimate_for_legacy_rows(tmp_path):
    """A row with 0/0 tokens falls back to the latency estimate, and that is
    counted in baseline_estimated_rows so callers can label it honestly."""
    ls = LineageStore(db_path=tmp_path / "lineage.db")
    ls.record(_rec(input_tokens=1000, output_tokens=500))     # real
    ls.record(_rec(input_tokens=0, output_tokens=0, latency_ms=4000))  # legacy → estimate
    ss = SessionStore(db_path=tmp_path / "sessions.db")
    data = collect(lineage_store=ls, session_store=ss)
    assert data.baseline_estimated_rows == 1
