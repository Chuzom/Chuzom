"""North Star S3: the routing-quality measurement ledger.

"Route to the cheapest capable model, escalate on failure" must be MEASURED, not
assumed. record() appends per-route metrics fail-open (never breaks routing);
summarize() reads them back into escalation / mis-route / completion rates + savings.
"""
from __future__ import annotations

import json

from chuzom.routing_quality import RouteRecord, record, summarize


def _rec(**kw):
    base = dict(task_type="code", chosen_tier=0, needed_escalation=False,
                completion=True, tool_success=True, actual_cost=0.0,
                baseline_cost=0.20, saved=0.20, mis_route=False)
    base.update(kw)
    return RouteRecord(**base)


def test_record_appends_a_row(tmp_path):
    ledger = tmp_path / "rq.jsonl"
    assert record(_rec(), path=str(ledger)) is True
    rows = [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["task_type"] == "code" and rows[0]["saved"] == 0.20
    assert rows[0]["ts"] > 0  # stamped on write


def test_summarize_computes_rates(tmp_path):
    ledger = tmp_path / "rq.jsonl"
    record(_rec(needed_escalation=False, mis_route=False, completion=True), path=str(ledger))
    record(_rec(needed_escalation=True, mis_route=True, completion=True, saved=0.10), path=str(ledger))
    record(_rec(needed_escalation=False, mis_route=False, completion=False,
                tool_success=False, saved=0.0), path=str(ledger))
    s = summarize(path=str(ledger))
    assert s["routes"] == 3
    assert abs(s["escalation_rate"] - 1 / 3) < 1e-9
    assert abs(s["mis_route_rate"] - 1 / 3) < 1e-9
    assert abs(s["completion_rate"] - 2 / 3) < 1e-9
    assert abs(s["total_saved"] - 0.30) < 1e-9


def test_record_is_fail_open_on_bad_path(tmp_path):
    # A path whose parent can't be created (a file used as a dir) must NOT raise.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    bad = blocker / "nested" / "rq.jsonl"
    assert record(_rec(), path=str(bad)) is False  # swallowed, returned False


def test_summarize_missing_ledger_is_empty(tmp_path):
    assert summarize(path=str(tmp_path / "nope.jsonl")) == {"routes": 0}
