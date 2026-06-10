"""Loop-5 #3 — Gemini billing ingestor.

Mirror of the OpenAI ingestor's shape so the diff endpoint can
dispatch on ``provider`` without caring which provider produced
the ``InvoiceReport``.

Google's Gemini API (``generativelanguage.googleapis.com``) does
not expose a per-month invoice endpoint the way Anthropic Console
does. The canonical "what did we spend" path is the Cloud Billing
BigQuery export, which requires per-org configuration and a
multi-day setup before any data lands. That's outside the scope
of a smallest-viable ingestor.

The viable smallest-shape path: **Cloud Monitoring API
time-series query** for the API request count metric. This gives
us authoritative ``call_count`` data scoped to
``generativelanguage.googleapis.com`` for the requested period.
Like the OpenAI ingestor, ``total_usd`` is reported as ``0.0``
with a ``pricing_note`` in ``raw`` — a future price-table
integration multiplies call_count by a per-model SKU price to
produce the dollar figure.

Auth model: operators issue a short-lived OAuth2 access token via
``gcloud auth application-default print-access-token``. We do NOT
implement the full service-account-JSON path here — that's a
heavier integration that lands in a follow-up slice. The operator
either passes the token explicitly or sets
``GEMINI_ACCESS_TOKEN`` in the env.

Required scope on the token: ``monitoring.read``.
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


_MONITORING_BASE_URL = (
    "https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries"
)
# The service-runtime metric is emitted automatically by GCP for
# every API call to a Google-managed service. Filtering by
# ``resource.labels.service`` narrows the result to Gemini.
_REQUEST_COUNT_METRIC = "serviceruntime.googleapis.com/api/request_count"
_GEMINI_SERVICE_LABEL = "generativelanguage.googleapis.com"


def _default_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Real HTTP fetch. Stubbed in tests."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pull_monthly_invoice(
    *,
    period: str,
    project_id: str | None = None,
    access_token: str | None = None,
    fetch: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
) -> InvoiceReport:
    """Pull Gemini usage for ``period`` (``YYYY-MM``).

    Args:
        period: ``YYYY-MM`` month identifier.
        project_id: GCP project ID hosting the Gemini API key.
            Falls back to ``GEMINI_PROJECT_ID`` env. Raises
            ``ValueError`` if neither is provided.
        access_token: Short-lived OAuth2 access token with
            ``monitoring.read`` scope. Falls back to
            ``GEMINI_ACCESS_TOKEN`` env. Raises ``ValueError`` if
            neither is provided.
        fetch: Injected HTTP function. Tests pass a stub; production
            uses ``_default_fetch``.

    Returns:
        ``InvoiceReport`` with ``provider="gemini"``, ``total_usd=0.0``
        (pricing-note carried in ``raw``), and ``call_count`` summed
        from the Cloud Monitoring time series.

    The Cloud Monitoring API returns a response shaped like::

        {
            "timeSeries": [
                {
                    "metric": {"type": "...", "labels": {…}},
                    "resource": {"type": "...", "labels": {…}},
                    "points": [
                        {"interval": {…}, "value": {"int64Value": "123"}},
                        …
                    ],
                },
                …
            ],
            "nextPageToken": "…"
        }

    Note that the ``int64Value`` is a string per protobuf JSON
    encoding conventions — we coerce defensively.
    """
    _validate_period(period)
    proj = project_id or os.environ.get("GEMINI_PROJECT_ID")
    if not proj:
        raise ValueError(
            "GEMINI_PROJECT_ID env (or project_id arg) is required "
            "to pull the Gemini usage report"
        )
    token = access_token or os.environ.get("GEMINI_ACCESS_TOKEN")
    if not token:
        raise ValueError(
            "GEMINI_ACCESS_TOKEN env (or access_token arg) is required "
            "to pull the Gemini usage report; generate one via "
            "`gcloud auth application-default print-access-token`"
        )
    actual_fetch = fetch or _default_fetch

    start_rfc3339, end_rfc3339 = _month_to_rfc3339_range(period)
    metric_filter = (
        f'metric.type="{_REQUEST_COUNT_METRIC}" '
        f'AND resource.labels.service="{_GEMINI_SERVICE_LABEL}"'
    )
    query = urllib.parse.urlencode({
        "filter": metric_filter,
        "interval.startTime": start_rfc3339,
        "interval.endTime": end_rfc3339,
        "aggregation.alignmentPeriod": "86400s",  # daily
        "aggregation.perSeriesAligner": "ALIGN_SUM",
    })
    url = _MONITORING_BASE_URL.format(project_id=proj) + "?" + query
    headers = {
        "Authorization": f"Bearer {token}",
        "content-type": "application/json",
    }
    payload = actual_fetch(url, headers)
    return _payload_to_report(payload, period)


def _validate_period(period: str) -> None:
    """Same contract as the other ingestors — ``YYYY-MM`` only.
    Kept duplicated rather than imported because the validation
    is the kind of thing each ingestor should pin independently:
    if one provider ever needs a different shape (e.g. quarterly),
    we don't want a shared validator to leak that across all
    three."""
    if not isinstance(period, str) or len(period) != 7 or period[4] != "-":
        raise ValueError(f"period must be YYYY-MM, got {period!r}")
    year, month = period.split("-")
    if not (year.isdigit() and month.isdigit()):
        raise ValueError(f"period must be numeric YYYY-MM, got {period!r}")
    m = int(month)
    if not 1 <= m <= 12:
        raise ValueError(
            f"period month must be 01-12, got {period!r}"
        )


def _month_to_rfc3339_range(period: str) -> tuple[str, str]:
    """Convert ``YYYY-MM`` to the inclusive RFC 3339 range
    ``[start_of_month, end_of_month_23:59:59]``. The Cloud Monitoring
    API documents RFC 3339 with a ``Z`` suffix for UTC; we match
    that exactly."""
    year, month = int(period[:4]), int(period[5:7])
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = monthrange(year, month)[1]
    end = datetime(
        year, month, last_day, 23, 59, 59, tzinfo=timezone.utc,
    )
    return (
        start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _payload_to_report(
    payload: dict[str, Any], period: str,
) -> InvoiceReport:
    series = payload.get("timeSeries") or []
    call_count = 0
    has_rows = False
    for entry in series:
        for point in entry.get("points", []):
            value = point.get("value") or {}
            raw_int = value.get("int64Value")
            if raw_int is None:
                continue
            try:
                # Per protobuf JSON encoding, int64 fields ship as
                # strings to survive JavaScript's float precision
                # limits. Defensively accept ints too — Google
                # could shorten the contract any time.
                call_count += int(raw_int)
                has_rows = True
            except (TypeError, ValueError):
                continue
    if not has_rows:
        return InvoiceReport(
            provider="gemini",
            period=period,
            total_usd=0.0,
            call_count=None,
            raw={
                "period": period, "missing": True,
                "envelope": payload,
            },
        )
    return InvoiceReport(
        provider="gemini",
        period=period,
        # Per-token pricing is out of scope for the smallest-viable
        # closure — same note as the OpenAI ingestor. call_count
        # is the authoritative field this slice provides; a future
        # slice multiplies it by a SKU price table to compute
        # total_usd.
        total_usd=0.0,
        call_count=call_count,
        raw={
            "period": period,
            "pricing_note": (
                "Google Cloud Monitoring API does not expose dollar "
                "totals; call_count is authoritative until a "
                "BigQuery-billing-export integration lands."
            ),
            "envelope": payload,
        },
    )


__all__ = ["pull_monthly_invoice"]
