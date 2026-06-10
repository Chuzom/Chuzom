"""G-017 (Loop-5 #2) — OpenAI Usage API invoice ingestor.

Mirror of the Anthropic ingestor's shape so the diff endpoint can
dispatch on ``provider`` without caring which provider produced
the ``InvoiceReport``.

OpenAI exposes usage at the per-day grain via the Admin Usage API
(``GET https://api.openai.com/v1/organization/usage/completions``
and related ``/embeddings``, ``/images`` endpoints). To get a
month-level total we request the period whose start/end dates
match the requested ``YYYY-MM`` and sum the daily buckets the
response returns.

Auth model: a separate **admin API key** with usage-read scope. The
regular ``OPENAI_API_KEY`` typically does NOT have it; operators
should issue a scoped admin key just for chuzom reconciliation.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Callable

from chuzom.invoice_reconciliation import InvoiceReport


_USAGE_BASE_URL = "https://api.openai.com/v1/organization/usage/completions"


def _default_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Real HTTP fetch. Stubbed in tests."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pull_monthly_invoice(
    *,
    period: str,
    admin_key: str | None = None,
    fetch: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
) -> InvoiceReport:
    """Pull the OpenAI usage for ``period`` (``YYYY-MM``).

    Args:
        period: ``YYYY-MM`` month identifier.
        admin_key: OpenAI admin-scoped API key. Falls back to
            ``OPENAI_ADMIN_KEY`` env, then ``OPENAI_API_KEY`` env.
            Raises ``ValueError`` when none of them is set.
        fetch: Injected HTTP function. Tests pass a stub; production
            uses ``_default_fetch``.

    Returns:
        ``InvoiceReport`` with ``provider="openai"``.

    Shape of the response we expect (per OpenAI's Admin Usage API
    docs)::

        {
            "data": [
                {"start_time": 1234567890, "end_time": 1234654290,
                 "results": [{"input_tokens": 10, "output_tokens": 20,
                              "num_model_requests": 5}, …]},
                …
            ],
            "has_more": false
        }

    The shape doesn't expose dollar totals directly — OpenAI bills
    per-token. We aggregate ``num_model_requests`` as ``call_count``
    and report ``total_usd = 0.0`` with a note in ``raw["missing"]``
    until a price-table integration lands (a future slice; out of
    scope for the smallest-viable closure this round delivers).
    """
    _validate_period(period)
    key = (
        admin_key
        or os.environ.get("OPENAI_ADMIN_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if not key:
        raise ValueError(
            "OPENAI_ADMIN_KEY (or OPENAI_API_KEY) env is required to "
            "pull the OpenAI usage report"
        )
    actual_fetch = fetch or _default_fetch

    start_ts, end_ts = _month_to_unix_range(period)
    query = urllib.parse.urlencode({
        "start_time": int(start_ts),
        "end_time": int(end_ts),
        "bucket_width": "1d",
    })
    url = f"{_USAGE_BASE_URL}?{query}"
    headers = {
        "Authorization": f"Bearer {key}",
        "OpenAI-Beta": "usage=v1",
        "content-type": "application/json",
    }
    payload = actual_fetch(url, headers)
    return _payload_to_report(payload, period)


def _validate_period(period: str) -> None:
    if not isinstance(period, str) or len(period) != 7 or period[4] != "-":
        raise ValueError(f"period must be YYYY-MM, got {period!r}")
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


def _month_to_unix_range(period: str) -> tuple[int, int]:
    """Convert ``YYYY-MM`` to the inclusive Unix-time range
    ``[start_of_month, start_of_next_month)``."""
    year, month = int(period[:4]), int(period[5:7])
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = monthrange(year, month)[1]
    end = datetime(
        year, month, last_day, 23, 59, 59, tzinfo=timezone.utc,
    )
    return int(start.timestamp()), int(end.timestamp())


def _payload_to_report(
    payload: dict[str, Any], period: str,
) -> InvoiceReport:
    rows = payload.get("data") or []
    call_count = 0
    has_rows = False
    for row in rows:
        for result in row.get("results", []):
            n = result.get("num_model_requests")
            if isinstance(n, (int, float)):
                call_count += int(n)
                has_rows = True
    if not has_rows:
        return InvoiceReport(
            provider="openai",
            period=period,
            total_usd=0.0,
            call_count=None,
            raw={
                "period": period, "missing": True,
                "envelope": payload,
            },
        )
    return InvoiceReport(
        provider="openai",
        period=period,
        # Per-token pricing is out of scope for the smallest-viable
        # closure — see module docstring. Call count is the
        # ground-truth field this slice provides; a future slice
        # adds the price table to compute total_usd.
        total_usd=0.0,
        call_count=call_count,
        raw={
            "period": period,
            "pricing_note": (
                "OpenAI usage API does not expose dollar totals; "
                "call_count is authoritative until a price-table "
                "integration lands."
            ),
            "envelope": payload,
        },
    )


__all__ = ["pull_monthly_invoice"]
