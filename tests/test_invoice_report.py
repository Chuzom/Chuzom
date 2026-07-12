"""Tests for the finance-facing invoice reconciliation report (#58)."""
from __future__ import annotations

import pytest

from chuzom.invoice_reconciliation import (
    ReconciliationDiff,
    build_reconciliation_report,
    format_report,
)


def _diff(provider: str, prov_usd: float, chuzom_usd: float) -> ReconciliationDiff:
    diff_usd = prov_usd - chuzom_usd
    diff_pct = diff_usd / prov_usd if prov_usd > 0 else 0.0
    return ReconciliationDiff(
        provider=provider, period="2026-06",
        provider_reported_usd=prov_usd, chuzom_reported_usd=chuzom_usd,
        diff_usd=diff_usd, diff_pct=diff_pct,
        provider_call_count=None, chuzom_call_count=0,
    )


def test_build_report_aggregates_and_flags_tolerance() -> None:
    diffs = [
        _diff("anthropic", 100.0, 99.0),   # 1% under → within 2%
        _diff("openai", 200.0, 180.0),     # 10% under → NOT within 2%
    ]
    r = build_reconciliation_report(period="2026-06", diffs=diffs)
    assert r["period"] == "2026-06"
    assert len(r["providers"]) == 2
    assert r["providers"][0]["within_2pct"] is True
    assert r["providers"][1]["within_2pct"] is False
    # Totals: provider 300, chuzom 279, diff 21, aggregate pct 21/300 = 0.07
    assert r["totals"]["provider_reported_usd"] == 300.0
    assert r["totals"]["chuzom_reported_usd"] == 279.0
    assert r["totals"]["diff_usd"] == 21.0
    assert r["totals"]["diff_pct"] == 0.07
    assert r["within_2pct_aggregate"] is False


def test_build_report_zero_provider_total_no_div_by_zero() -> None:
    r = build_reconciliation_report(period="2026-06", diffs=[_diff("gemini", 0.0, 0.0)])
    assert r["totals"]["diff_pct"] == 0.0
    assert r["within_2pct_aggregate"] is True


def test_format_report_csv_has_header_rows_and_total() -> None:
    r = build_reconciliation_report(
        period="2026-06", diffs=[_diff("anthropic", 100.0, 99.0)]
    )
    csv_out = format_report(r, fmt="csv")
    lines = [ln for ln in csv_out.splitlines() if ln]
    assert lines[0] == "provider,provider_reported_usd,chuzom_reported_usd,diff_usd,diff_pct,within_2pct"
    assert lines[1].startswith("anthropic,")
    assert lines[-1].startswith("TOTAL,")


def test_format_report_text_has_title_and_verdict() -> None:
    r = build_reconciliation_report(
        period="2026-06", diffs=[_diff("openai", 200.0, 180.0)]
    )
    txt = format_report(r, fmt="text")
    assert txt.startswith("Invoice reconciliation — 2026-06")
    assert "TOTAL" in txt
    assert "WITHIN 2% TOLERANCE: no" in txt


def test_format_report_unknown_fmt_raises() -> None:
    r = build_reconciliation_report(period="2026-06", diffs=[])
    with pytest.raises(ValueError):
        format_report(r, fmt="pdf")


# ── End-to-end CLI (#58 "produce") ───────────────────────────────────────────


def test_cmd_invoice_produces_report_and_exit_code(monkeypatch, capsys) -> None:
    from chuzom.commands import invoice as inv
    from chuzom.invoice_reconciliation import InvoiceReport

    def fake_pull(provider, month):
        if provider == "anthropic":
            return InvoiceReport("anthropic", month, 100.0, None, {})
        return None  # others "unreachable" (missing key) → skipped

    monkeypatch.setattr(inv, "_pull_invoice", fake_pull)
    monkeypatch.setattr(inv, "_chuzom_tally", lambda p, m: (80.0, 5))  # 20% under → out of tol

    rc = inv.cmd_invoice(["report", "--month", "2026-06", "--format", "text"])
    out = capsys.readouterr().out
    assert "Invoice reconciliation — 2026-06" in out
    assert "anthropic" in out
    assert "WITHIN 2% TOLERANCE: no" in out
    assert rc == 1  # out of tolerance → non-zero for scheduled-job alerting


def test_cmd_invoice_within_tolerance_exit_zero(monkeypatch, capsys) -> None:
    from chuzom.commands import invoice as inv
    from chuzom.invoice_reconciliation import InvoiceReport

    monkeypatch.setattr(inv, "_pull_invoice",
                        lambda p, m: InvoiceReport("anthropic", m, 100.0, None, {}) if p == "anthropic" else None)
    monkeypatch.setattr(inv, "_chuzom_tally", lambda p, m: (99.5, 5))  # 0.5% → within 2%
    rc = inv.cmd_invoice(["report", "--month", "2026-06"])
    assert rc == 0
