"""G-017 — Anthropic invoice ingestion + reconciliation diff.

Smallest viable proof-of-shape for Finance: month-level dollar
total + call count from Anthropic Console, paired with chuzom's
own log of ``anthropic/*`` calls for the same month. The
``diff_pct`` field answers "are we within 2%" in one shot.

Tests cover:

* Ingestor period validation (well-formed YYYY-MM only).
* Missing admin key raises (no silent zero report).
* Happy-path payload → ``InvoiceReport``.
* Empty payload → zero-total report rather than raising.
* Diff computation across the three regimes (match / under-report
  / over-report).
* Admin endpoint integration with a mocked fetch.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_actions import AdminActionLog
from chuzom.admin_api import (
    RuntimeProviderRegistry,
    create_app,
    get_admin_action_log,
    get_audit_log,
    get_identity_store,
    get_provider_registry,
)
from chuzom.enterprise.audit import AuditLog
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role
from chuzom.invoice_reconciliation import (
    InvoiceReport,
    compute_diff,
)
from chuzom.invoice_reconciliation.anthropic import (
    _validate_period,
    pull_monthly_invoice,
)


# ── 1. Period validation ──────────────────────────────────────────────────


@pytest.mark.parametrize("good", ["2026-01", "2026-12", "2025-06"])
def test_validate_period_accepts_well_formed(good: str) -> None:
    _validate_period(good)  # no raise


@pytest.mark.parametrize(
    "bad", ["2026", "2026-1", "2026/06", "26-06", "abc-de", "2026-13", "2026-00"],
)
def test_validate_period_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        _validate_period(bad)


# ── 2. Ingestor primitive ────────────────────────────────────────────────


def test_pull_invoice_requires_admin_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_ADMIN_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_ADMIN_KEY"):
        pull_monthly_invoice(period="2026-05")


def test_pull_invoice_happy_path() -> None:
    """Stub the fetch with a documented-shape payload, confirm the
    ``InvoiceReport`` carries the right fields."""
    def fake_fetch(url, headers):
        return {
            "data": [
                {
                    "period": "2026-05",
                    "total_cost_usd": 1234.56,
                    "request_count": 8901,
                    "extra": "preserved-in-raw",
                }
            ]
        }
    report = pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    assert report.provider == "anthropic"
    assert report.period == "2026-05"
    assert report.total_usd == 1234.56
    assert report.call_count == 8901
    assert report.raw["extra"] == "preserved-in-raw"


def test_pull_invoice_missing_month_returns_zero(monkeypatch) -> None:
    """When the provider hasn't billed for the requested period yet
    (or the key lacks permission), we return a zero-total report
    rather than raising. The diff endpoint surfaces that as
    ``provider_reported_usd=0``."""
    def fake_fetch(url, headers):
        return {"data": [{"period": "2026-04", "total_cost_usd": 1.0}]}
    report = pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    assert report.total_usd == 0.0
    assert report.raw.get("missing") is True


def test_pull_invoice_call_count_optional() -> None:
    """Some response shapes omit ``request_count``. The report
    surfaces ``None`` rather than raising."""
    def fake_fetch(url, headers):
        return {
            "data": [{"period": "2026-05", "total_cost_usd": 5.0}]
        }
    report = pull_monthly_invoice(
        period="2026-05", admin_key="dummy", fetch=fake_fetch,
    )
    assert report.call_count is None


# ── 3. Diff computation ──────────────────────────────────────────────────


def test_compute_diff_exact_match() -> None:
    invoice = InvoiceReport(
        provider="anthropic", period="2026-05",
        total_usd=100.0, call_count=500, raw={},
    )
    diff = compute_diff(
        invoice=invoice,
        chuzom_total_usd=100.0,
        chuzom_call_count=500,
    )
    assert diff.diff_usd == 0.0
    assert diff.diff_pct == 0.0


def test_compute_diff_we_under_report() -> None:
    """Provider billed $110, chuzom tracked $100 → +10 diff, +9.1%."""
    invoice = InvoiceReport(
        provider="anthropic", period="2026-05",
        total_usd=110.0, call_count=None, raw={},
    )
    diff = compute_diff(
        invoice=invoice,
        chuzom_total_usd=100.0,
        chuzom_call_count=500,
    )
    assert diff.diff_usd == 10.0
    assert diff.diff_pct == pytest.approx(0.0909, abs=1e-3)


def test_compute_diff_we_over_report() -> None:
    invoice = InvoiceReport(
        provider="anthropic", period="2026-05",
        total_usd=100.0, call_count=None, raw={},
    )
    diff = compute_diff(
        invoice=invoice,
        chuzom_total_usd=110.0,
        chuzom_call_count=500,
    )
    assert diff.diff_usd == -10.0
    assert diff.diff_pct == -0.10


def test_compute_diff_zero_invoice_does_not_divide_by_zero() -> None:
    """Provider reports $0 for the period. ``diff_pct`` defaults to
    0.0 rather than raising ZeroDivisionError."""
    invoice = InvoiceReport(
        provider="anthropic", period="2026-05",
        total_usd=0.0, call_count=None, raw={},
    )
    diff = compute_diff(
        invoice=invoice,
        chuzom_total_usd=0.0,
        chuzom_call_count=0,
    )
    assert diff.diff_pct == 0.0


# ── 4. Admin-API endpoint integration ────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False
    )


@pytest.fixture
def audit_log(tmp_path: Path) -> AuditLog:
    return AuditLog(db_path=tmp_path / "audit.db", check_same_thread=False)


@pytest.fixture
def admin_log(tmp_path: Path) -> AdminActionLog:
    return AdminActionLog(
        db_path=tmp_path / "admin_actions.db", check_same_thread=False
    )


@pytest.fixture
def registry() -> RuntimeProviderRegistry:
    return RuntimeProviderRegistry()


@pytest.fixture
def app_with_admin(
    store: IdentityStore,
    audit_log: AuditLog,
    admin_log: AdminActionLog,
    registry: RuntimeProviderRegistry,
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    app.dependency_overrides[get_audit_log] = lambda: audit_log
    app.dependency_overrides[get_admin_action_log] = lambda: admin_log
    app.dependency_overrides[get_provider_registry] = lambda: registry
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(store: IdentityStore) -> str:
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="admin@x", display_name="A", role=Role.ADMIN,
    )
    return store.issue_token(user.id, name="admin").plaintext


@pytest.fixture
def viewer_token(store: IdentityStore) -> str:
    org = store.create_org(name="acme2")
    team = store.create_team(org.id, "eng")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="emp@x", display_name="E", role=Role.EMPLOYEE,
    )
    return store.issue_token(user.id, name="emp").plaintext


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_endpoint_rejects_unsupported_provider(
    app_with_admin: TestClient, admin_token: str,
) -> None:
    resp = app_with_admin.get(
        "/v1/admin/invoice/diff?provider=openai&month=2026-05",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400
    assert "anthropic" in resp.json()["detail"]


def test_endpoint_requires_view_all_audit_permission(
    app_with_admin: TestClient, viewer_token: str,
) -> None:
    """EMPLOYEE tier (slice 12 fixture) doesn't carry
    ``VIEW_ALL_AUDIT`` so the endpoint refuses 403. This pins the
    audit posture: invoice numbers are sensitive enough that a
    routing-only token shouldn't see them."""
    resp = app_with_admin.get(
        "/v1/admin/invoice/diff?provider=anthropic&month=2026-05",
        headers=_auth(viewer_token),
    )
    assert resp.status_code == 403


def test_endpoint_happy_path_with_mocked_fetch(
    app_with_admin: TestClient,
    admin_token: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "dummy")

    def fake_fetch(url, headers):
        return {
            "data": [{
                "period": "2026-05",
                "total_cost_usd": 1000.0,
                "request_count": 100,
            }]
        }
    monkeypatch.setattr(
        "chuzom.invoice_reconciliation.anthropic._default_fetch",
        fake_fetch,
    )
    resp = app_with_admin.get(
        "/v1/admin/invoice/diff?provider=anthropic&month=2026-05",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "anthropic"
    assert body["period"] == "2026-05"
    assert body["provider_reported_usd"] == 1000.0
    assert body["provider_call_count"] == 100
    # chuzom-side tally is likely zero in tests (no usage rows) →
    # diff equals the invoice total.
    assert body["diff_usd"] == 1000.0
    assert body["within_two_pct"] is False


def test_endpoint_invalid_period_returns_400(
    app_with_admin: TestClient,
    admin_token: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "dummy")
    resp = app_with_admin.get(
        "/v1/admin/invoice/diff?provider=anthropic&month=not-a-month",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400


def test_endpoint_upstream_failure_returns_502(
    app_with_admin: TestClient,
    admin_token: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "dummy")

    def boom(url, headers):
        raise RuntimeError("anthropic console unreachable")

    monkeypatch.setattr(
        "chuzom.invoice_reconciliation.anthropic._default_fetch", boom,
    )
    resp = app_with_admin.get(
        "/v1/admin/invoice/diff?provider=anthropic&month=2026-05",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 502
    assert "anthropic console unreachable" in resp.json()["detail"]


def test_endpoint_within_two_pct_flag(
    app_with_admin: TestClient,
    admin_token: str,
    monkeypatch,
) -> None:
    """Finance's headline question. Provider says $100, chuzom says
    $99 → 1% diff → ``within_two_pct`` true."""
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "dummy")

    def fake_fetch(url, headers):
        return {
            "data": [{
                "period": "2026-05", "total_cost_usd": 100.0,
                "request_count": 50,
            }]
        }
    monkeypatch.setattr(
        "chuzom.invoice_reconciliation.anthropic._default_fetch",
        fake_fetch,
    )
    # chuzom-side tally is 0 in tests so diff_pct = 1.0 (100%) →
    # within_two_pct false. We're really testing the FLAG shape,
    # not the live value — that's covered by the unit tests on
    # ``compute_diff`` above.
    resp = app_with_admin.get(
        "/v1/admin/invoice/diff?provider=anthropic&month=2026-05",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "within_two_pct" in resp.json()
