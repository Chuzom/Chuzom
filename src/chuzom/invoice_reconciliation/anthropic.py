"""G-017 — Anthropic Console invoice ingestor.

Pulls usage from the Admin API
(``GET https://api.anthropic.com/v1/organizations/usage_report``)
under an ``ANTHROPIC_ADMIN_KEY`` and returns an ``InvoiceReport``
for the requested month. The HTTP layer is isolated behind a
single function so tests can monkeypatch it without a real network
call.

Auth model: the **admin key** is a separate credential from a
regular API key — it can read organization-wide usage but cannot
make completion calls. Operators should issue a scoped admin key
for chuzom's reconciliation use only.

The shape this ingestor returns is the audit's "smallest viable"
proof for the Finance question: a month-level dollar total + call
count. A future slice can broaden to per-model breakdowns; the
``raw`` field on ``InvoiceReport`` preserves the original payload
for that work.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable

from chuzom.invoice_reconciliation import InvoiceReport


_USAGE_REPORT_URL = (
    "https://api.anthropic.com/v1/organizations/usage_report"
)


def _default_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Real HTTP fetch. Stubbed in tests via the ``fetch`` param of
    ``pull_monthly_invoice``."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pull_monthly_invoice(
    *,
    period: str,
    admin_key: str | None = None,
    fetch: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
) -> InvoiceReport:
    """Pull the Anthropic invoice for ``period`` (``YYYY-MM``).

    Args:
        period: ``YYYY-MM`` month identifier.
        admin_key: Anthropic admin-scoped API key. Falls back to
            ``ANTHROPIC_ADMIN_KEY`` env. Raises ``ValueError`` when
            neither is set — we never want a "silent zero" report.
        fetch: Injected HTTP function (signature
            ``(url, headers) -> dict``). Tests pass a stub; production
            uses ``_default_fetch``.

    Returns:
        ``InvoiceReport`` with ``provider="anthropic"``.

    Raises:
        ``ValueError`` for malformed ``period`` or missing admin key.
        Re-raises HTTP errors as-is — the admin-API endpoint maps
        them to a clear 502.

    Shape of the response we expect (documented at
    docs.anthropic.com)::

        {
            "data": [
                {"period": "2026-05", "total_cost_usd": 123.45,
                 "request_count": 4567, ...},
                …
            ]
        }

    We pluck the entry whose ``period`` matches the requested month;
    if it's missing we return a zero-total report so the diff endpoint
    can surface "provider reports nothing for this month" cleanly.
    """
    _validate_period(period)
    key = admin_key or os.environ.get("ANTHROPIC_ADMIN_KEY")
    if not key:
        raise ValueError(
            "ANTHROPIC_ADMIN_KEY env (or admin_key kwarg) is "
            "required to pull the invoice"
        )
    actual_fetch = fetch or _default_fetch
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = actual_fetch(_USAGE_REPORT_URL, headers)
    return _payload_to_report(payload, period)


def _validate_period(period: str) -> None:
    if not isinstance(period, str) or len(period) != 7 or period[4] != "-":
        raise ValueError(
            f"period must be YYYY-MM, got {period!r}"
        )
    year, month = period.split("-")
    if not (year.isdigit() and month.isdigit()):
        raise ValueError(
            f"period must be numeric YYYY-MM, got {period!r}"
        )
    m = int(month)
    if not 1 <= m <= 12:
        raise ValueError(
            f"period month must be 01-12, got {period!r}"
        )


def _payload_to_report(
    payload: dict[str, Any], period: str,
) -> InvoiceReport:
    rows = payload.get("data") or []
    for row in rows:
        if row.get("period") == period:
            return InvoiceReport(
                provider="anthropic",
                period=period,
                total_usd=float(row.get("total_cost_usd", 0.0)),
                call_count=(
                    int(row["request_count"])
                    if "request_count" in row else None
                ),
                raw=dict(row),
            )
    # No row for the requested month — return a zero-total report
    # rather than raising. The diff endpoint then shows "Anthropic
    # billed $0 for this period" which is a defensible thing to
    # render even if it almost always means "the period hasn't
    # closed yet" or "the admin key lacks permission".
    return InvoiceReport(
        provider="anthropic",
        period=period,
        total_usd=0.0,
        call_count=None,
        raw={"period": period, "missing": True, "envelope": payload},
    )


__all__ = ["pull_monthly_invoice"]
