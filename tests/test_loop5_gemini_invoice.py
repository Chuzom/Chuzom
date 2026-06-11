"""Loop-5 #3 — Gemini billing ingestor.

Mirror of ``test_loop5_openai_invoice.py`` adapted for the Google
Cloud Monitoring API contract.

Key differences from the OpenAI tests:

* **RFC 3339 timestamps, not Unix seconds.** Cloud Monitoring uses
  ISO-8601-with-Z UTC strings (``2026-05-01T00:00:00Z``).
* **Protobuf-JSON int64 encoding.** ``int64Value`` ships as a
  string (``"123"``), not an int. The ingestor must coerce.
* **Two required env vars instead of one.** ``GEMINI_PROJECT_ID``
  scopes the query; ``GEMINI_ACCESS_TOKEN`` authenticates. Both
  must be present or the ingestor refuses to start.
* **Metric-filter URL parameter.** The filter string narrows the
  monitoring query to Gemini specifically — pinning it so a
  refactor can't accidentally widen the scope.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

import pytest

from chuzom.invoice_reconciliation import InvoiceReport
from chuzom.invoice_reconciliation.gemini import (
    _month_to_rfc3339_range,
    _validate_period,
    pull_monthly_invoice,
)


# ── 1. Period validation ──────────────────────────────────────────────────


@pytest.mark.parametrize("good", ["2026-01", "2026-12", "2025-06", "2024-02"])
def test_validate_period_accepts_well_formed(good: str) -> None:
    _validate_period(good)  # no raise


@pytest.mark.parametrize(
    "bad", ["2026", "2026-1", "2026/06", "26-06", "abc-de", "2026-13", "2026-00", ""],
)
def test_validate_period_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        _validate_period(bad)


# ── 2. Auth & project-id resolution ──────────────────────────────────────


def test_pull_invoice_requires_project_id(monkeypatch) -> None:
    """No arg + no env → ValueError. The error must name the env
    var so the operator knows which one to set."""
    monkeypatch.delenv("GEMINI_PROJECT_ID", raising=False)
    monkeypatch.setenv("GEMINI_ACCESS_TOKEN", "dummy")
    with pytest.raises(ValueError, match="GEMINI_PROJECT_ID"):
        pull_monthly_invoice(period="2026-05")


def test_pull_invoice_requires_access_token(monkeypatch) -> None:
    """Same shape: the access token is required and the error
    points at the env var."""
    monkeypatch.setenv("GEMINI_PROJECT_ID", "proj-123")
    monkeypatch.delenv("GEMINI_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="GEMINI_ACCESS_TOKEN"):
        pull_monthly_invoice(period="2026-05")


def test_pull_invoice_error_points_at_gcloud_command(monkeypatch) -> None:
    """The missing-token error should tell the operator how to
    generate one — pinning the helpful copy."""
    monkeypatch.setenv("GEMINI_PROJECT_ID", "proj-123")
    monkeypatch.delenv("GEMINI_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError, match=r"gcloud auth"):
        pull_monthly_invoice(period="2026-05")


def test_pull_invoice_uses_explicit_args_over_env(monkeypatch) -> None:
    """Explicit args win over env. Pinning the precedence so an
    operator passing a one-off project/token isn't silently
    overridden."""
    monkeypatch.setenv("GEMINI_PROJECT_ID", "env-proj")
    monkeypatch.setenv("GEMINI_ACCESS_TOKEN", "env-token")
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return {"timeSeries": []}

    pull_monthly_invoice(
        period="2026-05",
        project_id="arg-proj",
        access_token="arg-token",
        fetch=fake_fetch,
    )
    assert "arg-proj" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer arg-token"


def test_pull_invoice_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_PROJECT_ID", "env-proj")
    monkeypatch.setenv("GEMINI_ACCESS_TOKEN", "env-token")
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return {"timeSeries": []}

    pull_monthly_invoice(period="2026-05", fetch=fake_fetch)
    assert "env-proj" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer env-token"


# ── 3. URL & query construction ──────────────────────────────────────────


def test_pull_invoice_hits_cloud_monitoring_timeseries_endpoint(
    monkeypatch,
) -> None:
    """Pin the exact endpoint. A future migration to a v4 API or
    to a different host should be visible in the diff."""
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["url"] = url
        return {"timeSeries": []}

    pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    parsed = urllib.parse.urlparse(captured["url"])
    assert parsed.scheme == "https"
    assert parsed.netloc == "monitoring.googleapis.com"
    assert parsed.path == "/v3/projects/my-proj/timeSeries"


def test_pull_invoice_filters_to_gemini_service(monkeypatch) -> None:
    """The metric filter must scope to
    ``generativelanguage.googleapis.com`` — pinning so a refactor
    can't accidentally widen the scope and double-count usage
    from other Google APIs in the same project."""
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["url"] = url
        return {"timeSeries": []}

    pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(captured["url"]).query
    )
    metric_filter = query["filter"][0]
    assert "serviceruntime.googleapis.com/api/request_count" in metric_filter
    assert "generativelanguage.googleapis.com" in metric_filter


def test_pull_invoice_passes_rfc3339_interval(monkeypatch) -> None:
    """Cloud Monitoring uses RFC 3339 (``YYYY-MM-DDTHH:MM:SSZ``).
    Pinning the format so a future "use Unix seconds" copy-paste
    from the OpenAI ingestor can't ship — Google's API rejects
    Unix-seconds intervals with a 400."""
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["url"] = url
        return {"timeSeries": []}

    pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(captured["url"]).query
    )
    assert query["interval.startTime"] == ["2026-05-01T00:00:00Z"]
    assert query["interval.endTime"] == ["2026-05-31T23:59:59Z"]


def test_pull_invoice_uses_daily_alignment(monkeypatch) -> None:
    """86400-second aligner gives us per-day SUM rows. Same
    granularity choice as the OpenAI ingestor's bucket_width=1d."""
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["url"] = url
        return {"timeSeries": []}

    pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(captured["url"]).query
    )
    assert query["aggregation.alignmentPeriod"] == ["86400s"]
    assert query["aggregation.perSeriesAligner"] == ["ALIGN_SUM"]


def test_pull_invoice_sends_bearer_auth_header(monkeypatch) -> None:
    """OAuth2 bearer token. Pinning the header so a future "switch
    to API key in header" change is visible — Google's APIs accept
    both, but the bearer-token path is the one we documented."""
    captured: dict[str, Any] = {}

    def fake_fetch(url, headers):
        captured["headers"] = headers
        return {"timeSeries": []}

    pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="my-token",
        fetch=fake_fetch,
    )
    assert captured["headers"]["Authorization"] == "Bearer my-token"
    assert captured["headers"]["content-type"] == "application/json"


# ── 4. RFC 3339 helper ─────────────────────────────────────────────────────


def test_month_to_rfc3339_range_normal_month() -> None:
    start, end = _month_to_rfc3339_range("2026-05")
    assert start == "2026-05-01T00:00:00Z"
    assert end == "2026-05-31T23:59:59Z"


def test_month_to_rfc3339_range_february_leap_year() -> None:
    """2024 was a leap year. Pinning the calendar correctness."""
    _, end = _month_to_rfc3339_range("2024-02")
    assert end == "2024-02-29T23:59:59Z"


def test_month_to_rfc3339_range_february_non_leap_year() -> None:
    """2025 is NOT a leap year — Feb has 28 days. Symmetric with
    the leap-year test."""
    _, end = _month_to_rfc3339_range("2025-02")
    assert end == "2025-02-28T23:59:59Z"


def test_month_to_rfc3339_range_december() -> None:
    """December's last day is the 31st — symmetric with the OpenAI
    edge-case coverage."""
    start, end = _month_to_rfc3339_range("2026-12")
    assert start == "2026-12-01T00:00:00Z"
    assert end == "2026-12-31T23:59:59Z"


def test_month_to_rfc3339_range_uses_utc_z_suffix() -> None:
    """The trailing ``Z`` is part of the RFC 3339 contract Cloud
    Monitoring expects. Pinning so a future "let's use +00:00"
    refactor can't ship without an API contract review."""
    start, end = _month_to_rfc3339_range("2026-05")
    assert start.endswith("Z")
    assert end.endswith("Z")


# ── 5. Payload → InvoiceReport ──────────────────────────────────────────


def test_payload_to_report_happy_path() -> None:
    """Cloud Monitoring's int64Value ships as a STRING per protobuf
    JSON conventions. Pinning the string-coercion path so a future
    "we received int64s as ints" copy-paste can't drop the cast."""
    def fake_fetch(url, headers):
        return {
            "timeSeries": [
                {
                    "metric": {
                        "type": "serviceruntime.googleapis.com/api/request_count",
                        "labels": {"response_code": "200"},
                    },
                    "resource": {
                        "type": "consumed_api",
                        "labels": {"service": "generativelanguage.googleapis.com"},
                    },
                    "points": [
                        {
                            "interval": {
                                "startTime": "2026-05-01T00:00:00Z",
                                "endTime": "2026-05-02T00:00:00Z",
                            },
                            "value": {"int64Value": "150"},
                        },
                        {
                            "interval": {
                                "startTime": "2026-05-02T00:00:00Z",
                                "endTime": "2026-05-03T00:00:00Z",
                            },
                            "value": {"int64Value": "200"},
                        },
                    ],
                },
            ],
        }
    report = pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    assert isinstance(report, InvoiceReport)
    assert report.provider == "gemini"
    assert report.period == "2026-05"
    assert report.call_count == 350  # 150 + 200
    # Same out-of-scope shape as OpenAI — dollar total stays 0.
    assert report.total_usd == 0.0
    assert "pricing_note" in report.raw


def test_payload_to_report_aggregates_across_multiple_series() -> None:
    """Multiple time series (one per response_code label, typically)
    must all sum into the same call_count. Pinning the symmetry
    with OpenAI's multi-model aggregation test."""
    def fake_fetch(url, headers):
        return {
            "timeSeries": [
                {
                    "metric": {"labels": {"response_code": "200"}},
                    "points": [
                        {"value": {"int64Value": "100"}},
                    ],
                },
                {
                    "metric": {"labels": {"response_code": "429"}},
                    "points": [
                        {"value": {"int64Value": "5"}},
                    ],
                },
                {
                    "metric": {"labels": {"response_code": "500"}},
                    "points": [
                        {"value": {"int64Value": "2"}},
                    ],
                },
            ],
        }
    report = pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    # Every call counts toward the invoice — even 429/500s, since
    # GCP bills for them in many cases. Pin the inclusive count
    # so a future "exclude error responses" change is a visible
    # billing-semantics decision rather than an accidental refactor.
    assert report.call_count == 107  # 100 + 5 + 2


def test_payload_to_report_accepts_int_int64_values_defensively() -> None:
    """If Google ever ships int64Value as an actual int (against
    protobuf-JSON spec but possible), we still aggregate."""
    def fake_fetch(url, headers):
        return {
            "timeSeries": [
                {
                    "points": [
                        {"value": {"int64Value": 50}},  # int, not str
                        {"value": {"int64Value": "25"}},  # str
                    ],
                },
            ],
        }
    report = pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    assert report.call_count == 75


def test_payload_to_report_skips_missing_int64_value() -> None:
    """Defensive: a point without ``int64Value`` is skipped, not
    counted as zero or crashed on."""
    def fake_fetch(url, headers):
        return {
            "timeSeries": [
                {
                    "points": [
                        {"value": {"int64Value": "10"}},
                        {"value": {}},                  # empty value
                        {"value": {"doubleValue": 5.0}},  # wrong type
                        {"value": {"int64Value": "20"}},
                    ],
                },
            ],
        }
    report = pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    assert report.call_count == 30  # 10 + 20


def test_payload_to_report_empty_data_returns_missing_report() -> None:
    """When Cloud Monitoring returns no series for the period
    (project not configured, or no Gemini usage), we return a
    ``missing`` report rather than raising. Symmetric with the
    other ingestors."""
    def fake_fetch(url, headers):
        return {"timeSeries": []}

    report = pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    assert report.provider == "gemini"
    assert report.total_usd == 0.0
    assert report.call_count is None
    assert report.raw.get("missing") is True


def test_payload_to_report_preserves_envelope_in_raw() -> None:
    """Raw envelope preserved for forensics — symmetric with
    OpenAI and Anthropic."""
    payload = {
        "timeSeries": [
            {"points": [{"value": {"int64Value": "1"}}]},
        ],
        "nextPageToken": "abc",
    }
    def fake_fetch(url, headers):
        return payload

    report = pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    assert report.raw["envelope"] == payload


def test_payload_to_report_pricing_note_mentions_bq_export() -> None:
    """The pricing note should point at the documented migration
    path — Cloud Billing BigQuery export. Pinning the word so a
    future copy-edit doesn't drop the operator-facing hint."""
    def fake_fetch(url, headers):
        return {
            "timeSeries": [
                {"points": [{"value": {"int64Value": "1"}}]},
            ],
        }
    report = pull_monthly_invoice(
        period="2026-05",
        project_id="my-proj",
        access_token="dummy",
        fetch=fake_fetch,
    )
    note = report.raw["pricing_note"]
    assert "call_count" in note
    assert "authoritative" in note
    assert "BigQuery" in note  # the documented migration path
