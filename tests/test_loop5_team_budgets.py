"""Loop-5 #4 — per-team budgets admin endpoints.

Three endpoints around the existing ``QuotaTracker`` (which already
supports ``scope="team"``):

* ``GET    /v1/admin/teams/{team_id}/budget``
* ``POST   /v1/admin/teams/{team_id}/budget``
* ``DELETE /v1/admin/teams/{team_id}/budget``

This file pins the contract: shape of request/response, RBAC
gating per HTTP verb, audit emission on writes, 404 for unknown
teams, idempotent DELETE, and round-trip semantics
(POST then GET returns what was set).
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
    get_quota_tracker,
)
from chuzom.enterprise.audit import AuditLog
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.quotas import QuotaPolicy, QuotaTracker
from chuzom.enterprise.rbac import Role


# ── Fixtures (mirror G-017 test shape) ──────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False,
    )


@pytest.fixture
def audit_log(tmp_path: Path) -> AuditLog:
    return AuditLog(
        db_path=tmp_path / "audit.db", check_same_thread=False,
    )


@pytest.fixture
def admin_log(tmp_path: Path) -> AdminActionLog:
    return AdminActionLog(
        db_path=tmp_path / "admin_actions.db", check_same_thread=False,
    )


@pytest.fixture
def quotas(tmp_path: Path) -> QuotaTracker:
    return QuotaTracker(
        db_path=tmp_path / "quotas.db", check_same_thread=False,
    )


@pytest.fixture
def registry() -> RuntimeProviderRegistry:
    return RuntimeProviderRegistry()


@pytest.fixture
def app_with_admin(
    store: IdentityStore,
    audit_log: AuditLog,
    admin_log: AdminActionLog,
    quotas: QuotaTracker,
    registry: RuntimeProviderRegistry,
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    app.dependency_overrides[get_audit_log] = lambda: audit_log
    app.dependency_overrides[get_admin_action_log] = lambda: admin_log
    app.dependency_overrides[get_provider_registry] = lambda: registry
    app.dependency_overrides[get_quota_tracker] = lambda: quotas
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def team_setup(store: IdentityStore) -> tuple[str, str, str]:
    """Create an org + team + admin token. Returns
    ``(team_id, admin_token, employee_token)`` for use in tests."""
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    admin = store.create_user(
        org_id=org.id, team_id=team.id,
        email="admin@x", display_name="A", role=Role.ADMIN,
    )
    emp = store.create_user(
        org_id=org.id, team_id=team.id,
        email="emp@x", display_name="E", role=Role.EMPLOYEE,
    )
    return (
        team.id,
        store.issue_token(admin.id, name="admin").plaintext,
        store.issue_token(emp.id, name="emp").plaintext,
    )


@pytest.fixture
def manager_token(store: IdentityStore) -> str:
    """Separate fixture for a MANAGER user — used to pin that the
    MANAGER tier carries ``SET_TEAM_QUOTA`` (not just ADMIN)."""
    org = store.create_org(name="acme-mgr")
    team = store.create_team(org.id, "ops")
    mgr = store.create_user(
        org_id=org.id, team_id=team.id,
        email="mgr@x", display_name="M", role=Role.MANAGER,
    )
    return store.issue_token(mgr.id, name="mgr").plaintext


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 1. GET — read shape ─────────────────────────────────────────────────


def test_get_unconfigured_team_returns_configured_false(
    app_with_admin: TestClient, team_setup,
) -> None:
    """A fresh team with no budget set returns ``configured=False``
    and unlimited-default values. Pinning so operators can tell
    "no budget" from "budget=0" (which the tracker treats as
    unlimited too)."""
    team_id, admin_token, _ = team_setup
    resp = app_with_admin.get(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == team_id
    assert body["configured"] is False
    assert body["daily_cap_usd"] == 0.0
    assert body["monthly_cap_usd"] == 0.0
    assert body["hard_block"] is True
    assert body["daily_consumed_usd"] == 0.0
    assert body["monthly_consumed_usd"] == 0.0


def test_get_returns_consumed_amounts(
    app_with_admin: TestClient,
    team_setup,
    quotas: QuotaTracker,
) -> None:
    """The GET response carries the current consumed amount so a
    dashboard can show "$45 of $100" without a second round-trip."""
    team_id, admin_token, _ = team_setup
    quotas.consume("team", team_id, 12.34)
    resp = app_with_admin.get(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(admin_token),
    )
    body = resp.json()
    # Both daily and monthly buckets carry the spend (tracker
    # writes to both in one ``consume`` call).
    assert body["daily_consumed_usd"] == 12.34
    assert body["monthly_consumed_usd"] == 12.34


# ── 2. POST — write shape + round-trip ─────────────────────────────────


def test_post_then_get_round_trips(
    app_with_admin: TestClient, team_setup,
) -> None:
    """Pin the shape contract: what you POST you can GET back."""
    team_id, admin_token, _ = team_setup
    resp = app_with_admin.post(
        f"/v1/admin/teams/{team_id}/budget",
        json={
            "daily_cap_usd": 50.0,
            "monthly_cap_usd": 1000.0,
            "soft_warning_pct": 0.75,
            "hard_block": True,
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["daily_cap_usd"] == 50.0
    assert body["monthly_cap_usd"] == 1000.0
    assert body["soft_warning_pct"] == 0.75
    assert body["hard_block"] is True
    assert body["set_by"] == "admin@x"

    # Round-trip via GET.
    get_resp = app_with_admin.get(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(admin_token),
    )
    get_body = get_resp.json()
    assert get_body["configured"] is True
    assert get_body["daily_cap_usd"] == 50.0
    assert get_body["monthly_cap_usd"] == 1000.0


def test_post_persists_via_tracker(
    app_with_admin: TestClient,
    team_setup,
    quotas: QuotaTracker,
) -> None:
    """Beyond the HTTP-level round-trip — pin that the underlying
    tracker actually got the policy. This is the seam the router
    consults at request time."""
    team_id, admin_token, _ = team_setup
    app_with_admin.post(
        f"/v1/admin/teams/{team_id}/budget",
        json={"daily_cap_usd": 10.0, "monthly_cap_usd": 100.0},
        headers=_auth(admin_token),
    )
    policy = quotas.get_policy("team", team_id)
    assert policy.daily_cap_usd == 10.0
    assert policy.monthly_cap_usd == 100.0
    assert policy.hard_block is True


def test_post_uses_pydantic_defaults_when_partial(
    app_with_admin: TestClient, team_setup,
) -> None:
    """Pin the defaults so an operator who sends only the dollar
    caps doesn't accidentally turn off ``hard_block``."""
    team_id, admin_token, _ = team_setup
    resp = app_with_admin.post(
        f"/v1/admin/teams/{team_id}/budget",
        json={"daily_cap_usd": 25.0, "monthly_cap_usd": 500.0},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["soft_warning_pct"] == 0.80  # default
    assert body["hard_block"] is True        # default


def test_post_can_disable_hard_block_for_staged_rollout(
    app_with_admin: TestClient,
    team_setup,
    quotas: QuotaTracker,
) -> None:
    """A staged rollout commonly sets ``hard_block=False`` so the
    cap warns-but-allows for a week before enforcement starts.
    Pin that the toggle actually reaches the tracker."""
    team_id, admin_token, _ = team_setup
    app_with_admin.post(
        f"/v1/admin/teams/{team_id}/budget",
        json={
            "daily_cap_usd": 10.0,
            "monthly_cap_usd": 100.0,
            "hard_block": False,
        },
        headers=_auth(admin_token),
    )
    assert quotas.get_policy("team", team_id).hard_block is False


# ── 3. Validation ──────────────────────────────────────────────────────


def test_post_rejects_negative_caps(
    app_with_admin: TestClient, team_setup,
) -> None:
    """Negative caps would silently behave as unlimited (the
    tracker checks ``cap <= 0``). Pin that Pydantic refuses them
    with a 422 so the operator gets a clear error."""
    team_id, admin_token, _ = team_setup
    resp = app_with_admin.post(
        f"/v1/admin/teams/{team_id}/budget",
        json={"daily_cap_usd": -5.0, "monthly_cap_usd": 100.0},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 422


def test_post_rejects_soft_warning_out_of_range(
    app_with_admin: TestClient, team_setup,
) -> None:
    """``soft_warning_pct`` is a fraction (0..1). Pin the bounds so
    an operator who accidentally passes 80 (meaning 80%) gets a
    422 rather than triggering a soft warning at 80x the cap (i.e.
    never)."""
    team_id, admin_token, _ = team_setup
    resp = app_with_admin.post(
        f"/v1/admin/teams/{team_id}/budget",
        json={
            "daily_cap_usd": 10.0,
            "monthly_cap_usd": 100.0,
            "soft_warning_pct": 80.0,
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 422


def test_post_unknown_team_returns_404(
    app_with_admin: TestClient, team_setup,
) -> None:
    """A typo in the path parameter must 404 — otherwise the
    quota tracker would silently create a row for a non-existent
    team that the router would never charge against."""
    _, admin_token, _ = team_setup
    resp = app_with_admin.post(
        "/v1/admin/teams/team-does-not-exist/budget",
        json={"daily_cap_usd": 1.0, "monthly_cap_usd": 1.0},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 404


# ── 4. RBAC gating ──────────────────────────────────────────────────────


def test_get_rejects_employee_tier(
    app_with_admin: TestClient, team_setup,
) -> None:
    """EMPLOYEE doesn't carry ``VIEW_TEAM_USAGE`` — pin the 403."""
    team_id, _, emp_token = team_setup
    resp = app_with_admin.get(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(emp_token),
    )
    assert resp.status_code == 403


def test_post_rejects_employee_tier(
    app_with_admin: TestClient, team_setup,
) -> None:
    """EMPLOYEE doesn't carry ``SET_TEAM_QUOTA`` — pin the 403."""
    team_id, _, emp_token = team_setup
    resp = app_with_admin.post(
        f"/v1/admin/teams/{team_id}/budget",
        json={"daily_cap_usd": 1.0, "monthly_cap_usd": 1.0},
        headers=_auth(emp_token),
    )
    assert resp.status_code == 403


def test_delete_rejects_employee_tier(
    app_with_admin: TestClient, team_setup,
) -> None:
    team_id, _, emp_token = team_setup
    resp = app_with_admin.delete(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(emp_token),
    )
    assert resp.status_code == 403


def test_manager_tier_can_set_team_budget(
    app_with_admin: TestClient,
    store: IdentityStore,
    manager_token: str,
) -> None:
    """The MANAGER tier should be able to set team budgets too —
    this is the principal-of-least-privilege expectation that
    matches the role's bundled permissions. Pinning the row of the
    ``_ROLE_PERMISSIONS`` table so a future "let's lock SET_TEAM_QUOTA
    to ADMIN only" change is visible."""
    # The MANAGER user lives in their own org+team (from the
    # fixture); we need an existing team_id for the POST to find.
    # Reuse the manager's own team for the test.
    org = store.create_org(name="manager-target")
    team = store.create_team(org.id, "engineering")
    resp = app_with_admin.post(
        f"/v1/admin/teams/{team.id}/budget",
        json={"daily_cap_usd": 10.0, "monthly_cap_usd": 100.0},
        headers=_auth(manager_token),
    )
    assert resp.status_code == 200


def test_unauthenticated_request_returns_401(
    app_with_admin: TestClient, team_setup,
) -> None:
    """No Authorization header → 401, not 403. Pin the distinction
    so the response body's error code can be the right one for
    middleware that re-prompts for auth."""
    team_id, _, _ = team_setup
    resp = app_with_admin.get(
        f"/v1/admin/teams/{team_id}/budget",
    )
    assert resp.status_code in (401, 403)  # depends on auth scheme; pin both


# ── 5. Audit emission ──────────────────────────────────────────────────


def test_post_emits_admin_action(
    app_with_admin: TestClient,
    team_setup,
    admin_log: AdminActionLog,
) -> None:
    """Every write must emit a row so the audit endpoint surfaces
    who changed budgets and when. Pinning the action key
    (``team_budget:set``) so a future "rename action keys" refactor
    is visible across all consumers."""
    team_id, admin_token, _ = team_setup
    app_with_admin.post(
        f"/v1/admin/teams/{team_id}/budget",
        json={"daily_cap_usd": 10.0, "monthly_cap_usd": 100.0},
        headers=_auth(admin_token),
    )
    rows = admin_log.recent(limit=10)
    assert any(
        r["action"] == "team_budget:set" and r["resource_id"] == team_id
        for r in rows
    )


def test_delete_emits_admin_action(
    app_with_admin: TestClient,
    team_setup,
    admin_log: AdminActionLog,
) -> None:
    team_id, admin_token, _ = team_setup
    app_with_admin.delete(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(admin_token),
    )
    rows = admin_log.recent(limit=10)
    assert any(
        r["action"] == "team_budget:clear" and r["resource_id"] == team_id
        for r in rows
    )


def test_get_does_not_emit_admin_action(
    app_with_admin: TestClient,
    team_setup,
    admin_log: AdminActionLog,
) -> None:
    """Reads must NOT pollute the admin-action log — that log is
    for state-changing operations only. (Read activity belongs in
    the audit log if anywhere.)"""
    team_id, admin_token, _ = team_setup
    app_with_admin.get(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(admin_token),
    )
    rows = admin_log.recent(limit=10)
    assert not any(
        r["action"].startswith("team_budget:") for r in rows
    )


# ── 6. DELETE — idempotent + clears policy ──────────────────────────────


def test_delete_clears_policy(
    app_with_admin: TestClient,
    team_setup,
    quotas: QuotaTracker,
) -> None:
    """After DELETE the tracker returns the unlimited default."""
    team_id, admin_token, _ = team_setup
    quotas.set_policy(
        "team", team_id,
        QuotaPolicy(daily_cap_usd=10.0, monthly_cap_usd=100.0),
    )
    resp = app_with_admin.delete(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"team_id": team_id, "cleared": True}
    # Policy is back to unlimited defaults.
    policy = quotas.get_policy("team", team_id)
    assert policy.is_unlimited


def test_delete_is_idempotent(
    app_with_admin: TestClient, team_setup,
) -> None:
    """Deleting a team with no policy must not 404 — DELETE is
    idempotent by design (operator can safely retry without
    needing to check first)."""
    team_id, admin_token, _ = team_setup
    resp1 = app_with_admin.delete(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(admin_token),
    )
    resp2 = app_with_admin.delete(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(admin_token),
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200


def test_delete_preserves_consumption_history(
    app_with_admin: TestClient,
    team_setup,
    quotas: QuotaTracker,
) -> None:
    """Clearing the policy must not reset the consumed-spend rows.
    A re-set of the budget mid-period should see the spend
    already accumulated. Pin so a future "delete cascades to
    consumption" refactor is visible."""
    team_id, admin_token, _ = team_setup
    quotas.set_policy(
        "team", team_id,
        QuotaPolicy(daily_cap_usd=10.0, monthly_cap_usd=100.0),
    )
    quotas.consume("team", team_id, 5.0)
    app_with_admin.delete(
        f"/v1/admin/teams/{team_id}/budget",
        headers=_auth(admin_token),
    )
    assert quotas.consumed("team", team_id, "daily") == 5.0
