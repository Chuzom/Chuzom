"""Loop-5 #2 — OpenAI Usage API invoice ingestor.

Mirrors the shape of ``test_g017_invoice_reconciliation.py`` so the
two ingestors are exercised symmetrically. The OpenAI Usage API
differs from Anthropic Console in two material ways:

* It bills per-token, not per-dollar. The response has
  ``num_model_requests`` / ``input_tokens`` / ``output_tokens`` but
  **no aggregated dollar field**. Until a price-table integration
  lands, ``total_usd`` is forced to ``0.0`` and ``raw["pricing_note"]``
  documents why.
* It uses Unix-time range parameters (``start_time``, ``end_time``)
  instead of a ``YYYY-MM`` query string, so the ingestor has to
  translate the period to a UTC time range.

Tests cover:

1. Period validation (well-formed ``YYYY-MM`` only).
2. Auth resolution (``OPENAI_ADMIN_KEY`` first, then
   ``OPENAI_API_KEY``, otherwise raise).
3. URL/query construction (the right base URL, the right Unix-time
   range, the right ``bucket_width``).
4. Payload → ``InvoiceReport`` happy path (call_count aggregation
   across multiple buckets).
5. Empty payload → "missing" report rather than raise.
6. Per-token pricing note is carried in ``raw`` for downstream
   visibility.
7. Auth header is set correctly (``Authorization: Bearer <key>``).
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Any

import pytest

from chuzom.invoice_reconciliation import InvoiceReport
from chuzom.invoice_reconciliation.openai import (
    _month_to_unix_range,
    _validate_period,
    pull_monthly_invoice,
)


# ── 1. Period validation ──────────────────────────────────────────────────


@pytest.mark.parametrize("good", ["2026-01", "2026-12", "2025-06", "2024-02"])
def test_validate_period_accepts_well_formed(good: str) -> None:
    """Same period contract as the Anthropic ingestor. Pinning so a
    future "let's accept ``2026/05`` too" patch can't slip past the
    diff endpoint that dispatches on this exact format."""
    _validate_period(good)  # no raise


@pytest.mark.parametrize(
    "bad",
    [
        "2026",        # too short
        "2026-1",      # single-digit month
        "2026/06",     # wrong separator
        "26-06",       # 2-digit year
        "abc-de",      # non-numeric
        "2026-13",     # month > 12
        "2026-00",     # month < 1
        "",            # empty
    ],
)
def test_validate_period_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        _validate_period(bad)


# ── 2. Auth resolution chain ─────────────────────────────────────────────


def test_pull_invoice_uses_admin_key_arg_when_provided(monkeypatch) -> None:
    """An explicit ``admin_key=...`` overrides anything in env. Pinning
    the precedence so an operator passing the key explicitly isn't
    silently overridden by a stale env var."""
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "env-admin")
    monkeypatch.setenv("OPENAI_API_KEY", "env-fallback")
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["headers"] = headers
        return {"data": []}

    pull_monthly_invoice(
        period="2026-05", admin_key="arg-key", fetch=fake_fetch,
    )
    assert captured["headers"]["Authorization"] == "Bearer arg-key"


def test_pull_invoice_falls_back_to_admin_env_when_no_arg(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "env-admin")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["headers"] = headers
        return {"data": []}

    pull_monthly_invoice(period="2026-05", fetch=fake_fetch)
    assert captured["headers"]["Authorization"] == "Bearer env-admin"


def test_pull_invoice_falls_back_to_api_key_env_when_admin_unset(
    monkeypatch,
) -> None:
    """``OPENAI_API_KEY`` is the last-resort fallback. Per the
    ingestor docstring, operators *should* issue a scoped admin
    key, but we let the regular key try — if it lacks the usage-read
    scope the API will reply 403 and the diff endpoint surfaces that
    as a 502."""
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-key")
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["headers"] = headers
        return {"data": []}

    pull_monthly_invoice(period="2026-05", fetch=fake_fetch)
    assert captured["headers"]["Authorization"] == "Bearer fallback-key"


def test_pull_invoice_admin_key_wins_over_api_key(monkeypatch) -> None:
    """When both env names are set we use the admin one. Pinning so
    an operator who set both during a key rotation isn't surprised
    by the fallback winning."""
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "admin-wins")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-be-used")
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["headers"] = headers
        return {"data": []}

    pull_monthly_invoice(period="2026-05", fetch=fake_fetch)
    assert captured["headers"]["Authorization"] == "Bearer admin-wins"


def test_pull_invoice_raises_when_no_key_at_all(monkeypatch) -> None:
    """No arg + no env → ValueError. The error must name both env
    vars so the operator knows which one to set."""
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_ADMIN_KEY"):
        pull_monthly_invoice(period="2026-05")


# ── 3. URL & query construction ──────────────────────────────────────────


def test_pull_invoice_hits_completions_usage_endpoint(monkeypatch) -> None:
    """Smallest-viable closure scopes the ingestor to the
    ``/usage/completions`` endpoint. A future slice can add
    ``/embeddings`` / ``/images`` and aggregate — pin the current
    URL so that future change is visible in the diff."""
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["url"] = url
        return {"data": []}

    pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    parsed = urllib.parse.urlparse(captured["url"])
    assert parsed.scheme == "https"
    assert parsed.netloc == "api.openai.com"
    assert parsed.path == "/v1/organization/usage/completions"


def test_pull_invoice_passes_unix_time_range(monkeypatch) -> None:
    """The OpenAI Usage API takes Unix seconds. Pinning the exact
    ``start_time`` / ``end_time`` pair so a refactor that moves to
    nanoseconds or millis can't ship without updating the test."""
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["url"] = url
        return {"data": []}

    pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(captured["url"]).query
    )
    start_ts = int(query["start_time"][0])
    end_ts = int(query["end_time"][0])
    expected_start = int(
        datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp()
    )
    assert start_ts == expected_start
    # End is the last second of the month (we use inclusive-end
    # semantics to match the bucket semantics the API documents).
    expected_end = int(
        datetime(2026, 5, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    )
    assert end_ts == expected_end


def test_pull_invoice_uses_daily_bucket_width(monkeypatch) -> None:
    """Daily buckets keep the response small (≤ 31 rows per month)
    while still giving us granular call-count data."""
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["url"] = url
        return {"data": []}

    pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(captured["url"]).query
    )
    assert query["bucket_width"] == ["1d"]


def test_pull_invoice_sends_required_headers(monkeypatch) -> None:
    """The Usage API still gates on the ``OpenAI-Beta: usage=v1``
    header at the time of writing. Pinning so a future "we no
    longer need the beta header" change is visible in the diff."""
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["headers"] = headers
        return {"data": []}

    pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer dummy"
    assert headers["OpenAI-Beta"] == "usage=v1"
    assert headers["content-type"] == "application/json"


# ── 4. Unix-time helper (covers Feb leap-year edge case) ─────────────────


def test_month_to_unix_range_normal_month() -> None:
    start, end = _month_to_unix_range("2026-05")
    assert start == int(
        datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp()
    )
    assert end == int(
        datetime(2026, 5, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    )


def test_month_to_unix_range_february_leap_year() -> None:
    """2024 was a leap year — Feb has 29 days. Pinning the calendar
    correctness so a naive ``28``-day refactor can't ship."""
    start, end = _month_to_unix_range("2024-02")
    assert end == int(
        datetime(2024, 2, 29, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    )


def test_month_to_unix_range_february_non_leap_year() -> None:
    """2025 is NOT a leap year — Feb has 28 days. Symmetric with
    the leap-year test."""
    start, end = _month_to_unix_range("2025-02")
    assert end == int(
        datetime(2025, 2, 28, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    )


def test_month_to_unix_range_december_rolls_to_next_year() -> None:
    """December's last day is the 31st — pinning so a future "use
    first-of-next-month" semantics shift is visible."""
    start, end = _month_to_unix_range("2026-12")
    assert end == int(
        datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    )


# ── 5. Payload → InvoiceReport ──────────────────────────────────────────


def test_payload_to_report_happy_path() -> None:
    """Daily buckets with ``num_model_requests`` are summed into
    the report's ``call_count``. ``total_usd`` stays 0 (per-token
    pricing is out of scope for this slice; pinned by the explicit
    assertion below)."""
    def fake_fetch(url, headers):
        return {
            "data": [
                {
                    "start_time": 1714521600, "end_time": 1714608000,
                    "results": [
                        {
                            "input_tokens": 100,
                            "output_tokens": 200,
                            "num_model_requests": 50,
                        },
                    ],
                },
                {
                    "start_time": 1714608000, "end_time": 1714694400,
                    "results": [
                        {
                            "input_tokens": 300,
                            "output_tokens": 400,
                            "num_model_requests": 75,
                        },
                    ],
                },
            ],
            "has_more": False,
        }
    report = pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    assert isinstance(report, InvoiceReport)
    assert report.provider == "openai"
    assert report.period == "2026-05"
    assert report.call_count == 125  # 50 + 75
    # Per the module docstring: dollar total is intentionally 0
    # until a price-table integration lands.
    assert report.total_usd == 0.0
    assert "pricing_note" in report.raw


def test_payload_to_report_aggregates_multiple_results_per_bucket() -> None:
    """A single daily bucket can carry multiple per-model rows under
    ``results`` (one per model used that day). All should sum into
    the same ``call_count``."""
    def fake_fetch(url, headers):
        return {
            "data": [
                {
                    "start_time": 1714521600, "end_time": 1714608000,
                    "results": [
                        {
                            "model": "gpt-4o-mini",
                            "num_model_requests": 10,
                        },
                        {
                            "model": "gpt-4o",
                            "num_model_requests": 5,
                        },
                        {
                            "model": "o3",
                            "num_model_requests": 1,
                        },
                    ],
                },
            ],
        }
    report = pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    assert report.call_count == 16  # 10 + 5 + 1


def test_payload_to_report_empty_data_returns_missing_report() -> None:
    """When the provider hasn't billed for the period yet (or the
    key lacks usage-read scope), we return a zero-total ``missing``
    report rather than raising. Symmetric with the anthropic
    ingestor — the diff endpoint surfaces it as a Finance signal,
    not as a 5xx."""
    def fake_fetch(url, headers):
        return {"data": [], "has_more": False}

    report = pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    assert report.provider == "openai"
    assert report.total_usd == 0.0
    assert report.call_count is None
    assert report.raw.get("missing") is True


def test_payload_to_report_skips_non_numeric_request_counts() -> None:
    """Defensive: if OpenAI ever ships a ``null`` or string in the
    ``num_model_requests`` field, we must not crash. Pinning the
    silent skip so a malformed bucket can't take the whole
    ingestor down."""
    def fake_fetch(url, headers):
        return {
            "data": [
                {
                    "results": [
                        {"num_model_requests": 5},
                        {"num_model_requests": None},  # skipped
                        {"num_model_requests": "10"},  # skipped (string)
                        {"num_model_requests": 3},
                    ],
                },
            ],
        }
    report = pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    assert report.call_count == 8  # 5 + 3


def test_payload_to_report_preserves_envelope_in_raw() -> None:
    """The raw envelope is preserved on the report so the
    administrator can inspect it (e.g. via the diff endpoint's
    debug view) without re-fetching."""
    payload = {
        "data": [
            {"results": [{"num_model_requests": 1}]},
        ],
        "has_more": False,
        "next_cursor": "abc",
    }
    def fake_fetch(url, headers):
        return payload

    report = pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    assert report.raw["envelope"] == payload


def test_payload_to_report_pricing_note_is_explicit() -> None:
    """The pricing note must mention ``call_count`` is authoritative
    so a Finance reader of the raw payload understands why
    ``total_usd`` is 0. Pinning the word so a future copy-edit
    can't accidentally lose the signal."""
    def fake_fetch(url, headers):
        return {
            "data": [{"results": [{"num_model_requests": 1}]}],
        }
    report = pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    note = report.raw["pricing_note"]
    assert "call_count" in note
    assert "authoritative" in note
