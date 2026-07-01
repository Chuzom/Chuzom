"""Regression: "today"/period SQL must convert UTC-stored timestamps to LOCAL
before comparing to the local day, or non-UTC users lose the last N hours of
savings/usage near midnight (same bug class as the test_sidecar tz fix).
"""

from __future__ import annotations

import inspect
from pathlib import Path


def test_digest_today_period_uses_localtime():
    from chuzom import digest
    today_sql = digest._PERIOD_SQL["today"]
    assert "localtime" in today_sql, today_sql
    # both sides converted: column AND 'now'
    assert today_sql.count("localtime") >= 2, today_sql


def test_digest_spike_query_uses_localtime():
    from chuzom import digest
    src = inspect.getsource(digest)
    # the daily-spike "today" comparison must be localtime on both sides
    assert "date(timestamp,'localtime') = date('now','localtime')" in src


def _cost_src() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "chuzom" / "cost.py").read_text()


def test_cost_period_maps_use_localtime():
    src = _cost_src()
    # No bare UTC "today" boundary should remain in the period maps.
    assert '"today": "date(\'now\')"' not in src
    # The localtime today boundary is present (both period maps).
    assert src.count('"today": "date(\'now\',\'localtime\')"') >= 2


def test_cost_where_clauses_convert_column_to_localtime():
    src = _cost_src()
    # The savings/usage period WHERE clauses compare the localtime-converted column.
    assert "date(timestamp,'localtime') >=" in src
    # And the old bare-UTC column comparison is gone from those clauses.
    assert "WHERE date(timestamp) >=" not in src
