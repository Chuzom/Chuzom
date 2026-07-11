"""G-017 — provider invoice reconciliation.

The audit's G-017 row was the single biggest blocker on
Finance-certifiable savings. Until chuzom's reported usage is
matched against the provider's own billing, the savings number is
"directionally credible" (slice 12 verdict) but not certifiable.

This package starts the close. Each provider gets its own ingestor
module (``anthropic.py`` for now); each ingestor returns a
common-shape ``InvoiceReport`` so the diff logic can operate on a
single shape regardless of source.

The first ingestor (Anthropic Console) is the smallest viable shape
the audit asked for: pull last-month usage, match against chuzom's
own log of ``anthropic/*`` calls for the same month, surface the
diff via ``GET /v1/admin/invoice/diff?provider=anthropic&month=…``.

Why "smallest viable" not "all providers"? Each provider has a
different billing API and different auth flow. Closing G-017 across
all three (Anthropic + OpenAI + Gemini) is a multi-week effort.
Closing it for ONE provider proves the shape and provides Finance
its first data point — that's what unblocks the
"directionally-credible → certifiable" verdict transition for
Anthropic-routed traffic specifically.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvoiceReport:
    """The shared shape every provider ingestor produces.

    ``period`` is the YYYY-MM string the invoice covers.
    ``total_usd`` is the dollar total the provider billed for that
    period. ``call_count`` is the call count the provider attributes
    to that period (may be missing for providers that don't expose
    it; ``None`` then). ``raw`` carries the original JSON for
    forensics — a future "let me see the actual invoice" admin
    endpoint can render it.
    """

    provider: str
    period: str
    total_usd: float
    call_count: int | None
    raw: dict


@dataclass(frozen=True)
class ReconciliationDiff:
    """The output of comparing one ``InvoiceReport`` with chuzom's
    own log for the same period.

    ``provider_reported_usd`` and ``chuzom_reported_usd`` should
    converge as the integration matures. ``diff_pct`` makes the
    Finance question ("are we within 2%?") a single field.
    """

    provider: str
    period: str
    provider_reported_usd: float
    chuzom_reported_usd: float
    diff_usd: float
    diff_pct: float
    provider_call_count: int | None
    chuzom_call_count: int


def compute_diff(
    *,
    invoice: InvoiceReport,
    chuzom_total_usd: float,
    chuzom_call_count: int,
) -> ReconciliationDiff:
    """Pure-function diff calculator. Given the provider's invoice
    + chuzom's own tallies, produce the comparison.

    ``diff_usd`` is signed: positive means the provider billed MORE
    than chuzom tracked (we under-reported), negative means we
    over-reported.

    ``diff_pct`` uses the provider's number as the denominator
    because the provider's number is the ground truth — Finance is
    asking "how close is chuzom's number to the invoice", not the
    reverse.
    """
    diff_usd = invoice.total_usd - chuzom_total_usd
    diff_pct = (
        diff_usd / invoice.total_usd
        if invoice.total_usd > 0 else 0.0
    )
    return ReconciliationDiff(
        provider=invoice.provider,
        period=invoice.period,
        provider_reported_usd=invoice.total_usd,
        chuzom_reported_usd=chuzom_total_usd,
        diff_usd=diff_usd,
        diff_pct=diff_pct,
        provider_call_count=invoice.call_count,
        chuzom_call_count=chuzom_call_count,
    )


def alert_if_discrepant(
    diff: "ReconciliationDiff",
    *,
    threshold_pct: float | None = None,
) -> bool:
    """Emit an ``invoice_discrepancy`` alert when a reconciliation diff
    breaches the Finance tolerance, so an unreconciled month PAGES
    instead of sitting unnoticed behind a pollable endpoint.

    ``threshold_pct`` defaults to ``CHUZOM_INVOICE_DISCREPANCY_PCT``
    (fraction, e.g. ``0.02`` for 2%) or ``0.02`` when unset — matching
    the G-006 "within 2%" acceptance bar. Returns True iff an alert was
    emitted. Best-effort: the alert sink itself never raises.
    """
    import os

    if threshold_pct is None:
        raw = (os.environ.get("CHUZOM_INVOICE_DISCREPANCY_PCT") or "").strip()
        try:
            threshold_pct = float(raw) if raw else 0.02
        except ValueError:
            threshold_pct = 0.02

    if abs(diff.diff_pct) <= threshold_pct:
        return False

    from chuzom.alerts import INVOICE_DISCREPANCY, emit_alert

    emit_alert(
        INVOICE_DISCREPANCY,
        detail={
            "provider": diff.provider,
            "period": diff.period,
            "diff_pct": diff.diff_pct,
            "diff_usd": diff.diff_usd,
            "threshold_pct": threshold_pct,
            "provider_reported_usd": diff.provider_reported_usd,
            "chuzom_reported_usd": diff.chuzom_reported_usd,
        },
    )
    return True


def build_reconciliation_report(*, period: str, diffs: list[ReconciliationDiff]) -> dict:
    """Aggregate per-provider ReconciliationDiffs into a finance-facing summary.

    Produces one row per provider plus a TOTAL, and answers Finance's
    "are we within 2% overall?" via ``within_2pct_aggregate`` (aggregate
    pct uses summed provider dollars as the denominator).
    """
    providers = []
    total_provider = 0.0
    total_chuzom = 0.0
    total_diff = 0.0

    for diff in diffs:
        total_provider += diff.provider_reported_usd
        total_chuzom += diff.chuzom_reported_usd
        total_diff += diff.diff_usd

        providers.append(
            {
                "provider": diff.provider,
                "provider_reported_usd": round(diff.provider_reported_usd, 2),
                "chuzom_reported_usd": round(diff.chuzom_reported_usd, 2),
                "diff_usd": round(diff.diff_usd, 2),
                "diff_pct": round(diff.diff_pct, 4),
                "within_2pct": abs(diff.diff_pct) <= 0.02,
            }
        )

    aggregate_diff_pct = total_diff / total_provider if total_provider > 0 else 0.0

    return {
        "period": period,
        "providers": providers,
        "totals": {
            "provider_reported_usd": round(total_provider, 2),
            "chuzom_reported_usd": round(total_chuzom, 2),
            "diff_usd": round(total_diff, 2),
            "diff_pct": round(aggregate_diff_pct, 4),
        },
        "within_2pct_aggregate": abs(aggregate_diff_pct) <= 0.02,
    }


def format_report(report: dict, *, fmt: str = "text") -> str:
    """Render a report dict (from build_reconciliation_report) as text or CSV."""
    if fmt == "csv":
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "provider",
                "provider_reported_usd",
                "chuzom_reported_usd",
                "diff_usd",
                "diff_pct",
                "within_2pct",
            ]
        )

        for provider in report["providers"]:
            writer.writerow(
                [
                    provider["provider"],
                    provider["provider_reported_usd"],
                    provider["chuzom_reported_usd"],
                    provider["diff_usd"],
                    provider["diff_pct"],
                    provider["within_2pct"],
                ]
            )

        totals = report["totals"]
        writer.writerow(
            [
                "TOTAL",
                totals["provider_reported_usd"],
                totals["chuzom_reported_usd"],
                totals["diff_usd"],
                totals["diff_pct"],
                report["within_2pct_aggregate"],
            ]
        )
        return output.getvalue()

    if fmt == "text":
        rows = report["providers"]
        totals = report["totals"]

        provider_width = max(
            [len("Provider"), len("TOTAL"), *(len(str(row["provider"])) for row in rows)]
        )
        money_width = 14
        pct_width = 9
        tolerance_width = len("Within 2%")

        lines = [
            f"Invoice reconciliation — {report['period']}",
            (
                f"{'Provider':<{provider_width}}  "
                f"{'Provider USD':>{money_width}}  "
                f"{'Chuzom USD':>{money_width}}  "
                f"{'Diff USD':>{money_width}}  "
                f"{'Diff %':>{pct_width}}  "
                f"{'Within 2%':>{tolerance_width}}"
            ),
        ]
        lines.append("-" * len(lines[-1]))

        for row in rows:
            lines.append(
                f"{row['provider']:<{provider_width}}  "
                f"{row['provider_reported_usd']:>{money_width}.2f}  "
                f"{row['chuzom_reported_usd']:>{money_width}.2f}  "
                f"{row['diff_usd']:>{money_width}.2f}  "
                f"{row['diff_pct']:>{pct_width}.4f}  "
                f"{'yes' if row['within_2pct'] else 'no':>{tolerance_width}}"
            )

        lines.append("-" * len(lines[1]))
        lines.append(
            f"{'TOTAL':<{provider_width}}  "
            f"{totals['provider_reported_usd']:>{money_width}.2f}  "
            f"{totals['chuzom_reported_usd']:>{money_width}.2f}  "
            f"{totals['diff_usd']:>{money_width}.2f}  "
            f"{totals['diff_pct']:>{pct_width}.4f}  "
            f"{'yes' if report['within_2pct_aggregate'] else 'no':>{tolerance_width}}"
        )
        lines.append(
            f"WITHIN 2% TOLERANCE: {'yes' if report['within_2pct_aggregate'] else 'no'}"
        )
        return "\n".join(lines)

    raise ValueError(f"unknown report format: {fmt}")


__all__ = [
    "InvoiceReport",
    "ReconciliationDiff",
    "compute_diff",
    "alert_if_discrepant",
    "build_reconciliation_report",
    "format_report",
]
