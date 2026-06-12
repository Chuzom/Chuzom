"""G-006-F5 — admin-action audit: who-changed-what-when.

Every mutating admin endpoint must write exactly one
``admin_actions`` row. Read endpoints (`GET /v1/admin/users`,
`GET /v1/admin/audit`, `GET /v1/admin/admin-actions` itself) write
none. Failed mutations (RBAC denial, validation failure) write none
— the row reflects the *successful* state transition.

The emit is best-effort: a broken admin-action DB must not turn a
successful mutation into a 500. Operators see the gap by reading
the table.
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
def org_and_team(store: IdentityStore) -> tuple[str, str]:
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    return org.id, team.id


@pytest.fixture
def admin(store: IdentityStore, org_and_team) -> tuple[str, str]:
    """Return (admin token plaintext, admin user id)."""
    org_id, team_id = org_and_team
    user = store.create_user(
        org_id=org_id, team_id=team_id,
        email="admin@acme.test", display_name="Admin",
        role=Role.ADMIN,
    )
    tok = store.issue_token(user.id, name="admin")
    return tok.plaintext, user.id


@pytest.fixture
def viewer(store: IdentityStore, org_and_team) -> str:
    org_id, team_id = org_and_team
    user = store.create_user(
        org_id=org_id, team_id=team_id,
        email="emp@acme.test", display_name="Emp",
        role=Role.EMPLOYEE,
    )
    return store.issue_token(user.id, name="emp").plaintext


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── AdminActionLog primitive ─────────────────────────────────────────────────


def test_admin_action_log_append_and_recent(tmp_path: Path) -> None:
    log = AdminActionLog(
        db_path=tmp_path / "a.db", check_same_thread=False
    )
    log.append(
        actor_user_id="u1", actor_email="a@x",
        action="user:create", resource_id="u2",
        detail={"role": "employee"},
    )
    log.append(
        actor_user_id="u1", actor_email="a@x",
        action="provider:disable", resource_id="openai",
        detail={"reason": "leak"},
    )
    rows = log.recent()
    assert len(rows) == 2
    # Newest first.
    assert rows[0]["action"] == "provider:disable"
    assert rows[0]["resource_id"] == "openai"
    assert rows[0]["detail"] == {"reason": "leak"}


def test_admin_action_log_filter_by_action(tmp_path: Path) -> None:
    log = AdminActionLog(
        db_path=tmp_path / "a.db", check_same_thread=False
    )
    log.append(
        actor_user_id="u1", actor_email="a@x",
        action="user:create", resource_id="u2", detail={},
    )
    log.append(
        actor_user_id="u1", actor_email="a@x",
        action="policy:push", resource_id="/p", detail={},
    )
    rows = log.recent(action="policy:push")
    assert len(rows) == 1
    assert rows[0]["action"] == "policy:push"


# ── Endpoint integration: each mutation writes exactly one row ──────────────


def test_create_user_writes_admin_action(
    app_with_admin: TestClient,
    admin: tuple[str, str],
    org_and_team,
    admin_log: AdminActionLog,
) -> None:
    org_id, team_id = org_and_team
    admin_token, admin_user_id = admin
    pre = admin_log.count()
    resp = app_with_admin.post(
        "/v1/admin/users",
        headers=_auth(admin_token),
        json={
            "org_id": org_id, "team_id": team_id,
            "email": "x@y.z", "display_name": "X", "role": "employee",
        },
    )
    assert resp.status_code == 201
    new_user_id = resp.json()["id"]
    assert admin_log.count() == pre + 1
    row = admin_log.recent(limit=1)[0]
    assert row["action"] == "user:create"
    assert row["actor_user_id"] == admin_user_id
    assert row["resource_id"] == new_user_id
    assert row["detail"]["email"] == "x@y.z"


def test_failed_create_does_not_write_admin_action(
    app_with_admin: TestClient,
    admin: tuple[str, str],
    org_and_team,
    admin_log: AdminActionLog,
) -> None:
    """A 400 must NOT show up in admin-actions — the log is for
    successful state transitions only."""
    org_id, team_id = org_and_team
    admin_token, _ = admin
    pre = admin_log.count()
    resp = app_with_admin.post(
        "/v1/admin/users",
        headers=_auth(admin_token),
        json={
            "org_id": org_id, "team_id": team_id,
            "email": "x@y.z", "display_name": "X",
            "role": "viewer",  # invalid → 400
        },
    )
    assert resp.status_code == 400
    assert admin_log.count() == pre


def test_rbac_failure_does_not_write_admin_action(
    app_with_admin: TestClient,
    viewer: str,
    org_and_team,
    admin_log: AdminActionLog,
) -> None:
    """A 403 must NOT show up in admin-actions either."""
    org_id, team_id = org_and_team
    pre = admin_log.count()
    resp = app_with_admin.post(
        "/v1/admin/users",
        headers=_auth(viewer),
        json={
            "org_id": org_id, "team_id": team_id,
            "email": "x@y.z", "display_name": "X", "role": "employee",
        },
    )
    assert resp.status_code == 403
    assert admin_log.count() == pre


def test_issue_token_writes_admin_action(
    app_with_admin: TestClient,
    admin: tuple[str, str],
    store: IdentityStore,
    org_and_team,
    admin_log: AdminActionLog,
) -> None:
    org_id, team_id = org_and_team
    admin_token, _ = admin
    target = store.create_user(
        org_id=org_id, team_id=team_id,
        email="t@x", display_name="T", role=Role.EMPLOYEE,
    )
    pre = admin_log.count()
    resp = app_with_admin.post(
        f"/v1/admin/users/{target.id}/tokens",
        headers=_auth(admin_token),
        json={"name": "bot"},
    )
    assert resp.status_code == 201
    assert admin_log.count() == pre + 1
    row = admin_log.recent(limit=1)[0]
    assert row["action"] == "token:issue"
    assert row["detail"]["target_user_id"] == target.id


def test_revoke_token_writes_admin_action(
    app_with_admin: TestClient,
    admin: tuple[str, str],
    store: IdentityStore,
    org_and_team,
    admin_log: AdminActionLog,
) -> None:
    org_id, team_id = org_and_team
    admin_token, _ = admin
    target = store.create_user(
        org_id=org_id, team_id=team_id,
        email="t2@x", display_name="T", role=Role.EMPLOYEE,
    )
    target_token = store.issue_token(target.id, name="bot")
    pre = admin_log.count()
    resp = app_with_admin.post(
        f"/v1/admin/users/{target.id}/tokens/{target_token.id}:revoke",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert admin_log.count() == pre + 1
    assert admin_log.recent(limit=1)[0]["action"] == "token:revoke"


def test_disable_and_enable_provider_each_write_one_row(
    app_with_admin: TestClient,
    admin: tuple[str, str],
    admin_log: AdminActionLog,
) -> None:
    admin_token, _ = admin
    pre = admin_log.count()
    app_with_admin.post(
        "/v1/admin/providers/openai:disable",
        headers=_auth(admin_token),
        json={"reason": "leak"},
    )
    app_with_admin.post(
        "/v1/admin/providers/openai:enable",
        headers=_auth(admin_token),
    )
    assert admin_log.count() == pre + 2
    rows = admin_log.recent(limit=2)
    assert {r["action"] for r in rows} == {"provider:disable", "provider:enable"}


def test_push_policy_writes_admin_action(
    app_with_admin: TestClient,
    admin: tuple[str, str],
    tmp_path,
    monkeypatch,
    admin_log: AdminActionLog,
) -> None:
    admin_token, _ = admin
    monkeypatch.setenv("CHUZOM_POLICY_PATH", str(tmp_path / "policy.yaml"))
    pre = admin_log.count()
    resp = app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(admin_token),
        json={"yaml": "name: pilot\n"},
    )
    assert resp.status_code == 200
    assert admin_log.count() == pre + 1
    row = admin_log.recent(limit=1)[0]
    assert row["action"] == "policy:push"
    assert row["detail"]["bytes"] > 0


# ── GET /v1/admin/admin-actions ──────────────────────────────────────────────


def test_get_admin_actions_endpoint_returns_recent(
    app_with_admin: TestClient,
    admin: tuple[str, str],
    admin_log: AdminActionLog,
) -> None:
    admin_token, _ = admin
    # Generate 3 mutations.
    app_with_admin.post(
        "/v1/admin/providers/p1:disable",
        headers=_auth(admin_token), json={"reason": "x"},
    )
    app_with_admin.post(
        "/v1/admin/providers/p2:disable",
        headers=_auth(admin_token), json={"reason": "x"},
    )
    app_with_admin.post(
        "/v1/admin/providers/p1:enable", headers=_auth(admin_token),
    )
    resp = app_with_admin.get(
        "/v1/admin/admin-actions?limit=10",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 3
    # Filter works:
    filt = app_with_admin.get(
        "/v1/admin/admin-actions?action=provider:enable",
        headers=_auth(admin_token),
    )
    assert filt.status_code == 200
    actions = [r["action"] for r in filt.json()]
    assert actions == ["provider:enable"]


def test_get_admin_actions_viewer_forbidden(
    app_with_admin: TestClient, viewer: str
) -> None:
    resp = app_with_admin.get(
        "/v1/admin/admin-actions", headers=_auth(viewer)
    )
    assert resp.status_code == 403


# ── Fail-open contract ──────────────────────────────────────────────────────


def test_admin_action_log_failure_does_not_break_mutation(
    app_with_admin: TestClient,
    admin: tuple[str, str],
    monkeypatch,
) -> None:
    """If the AdminActionLog write fails, the underlying mutation still
    succeeds. Operators see the missing row in the log; the API call
    must not 500."""

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    # Force every AdminActionLog.append to raise.
    monkeypatch.setattr(
        "chuzom.admin_actions.AdminActionLog.append", boom
    )
    admin_token, _ = admin
    resp = app_with_admin.post(
        "/v1/admin/providers/openai:disable",
        headers=_auth(admin_token),
        json={"reason": "test"},
    )
    assert resp.status_code == 200
    assert resp.json()["disabled"] is True
