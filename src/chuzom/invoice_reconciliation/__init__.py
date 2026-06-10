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


__all__ = [
    "InvoiceReport",
    "ReconciliationDiff",
    "compute_diff",
]
