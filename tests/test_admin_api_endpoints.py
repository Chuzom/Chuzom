"""G-006-F4 — real implementations of the previously-stubbed endpoints.

Covers:

* ``POST /v1/admin/users`` (create) — 201 happy path, 409 conflict,
  404 missing team, 400 invalid role, 403 on viewer.
* ``POST /v1/admin/users/{user_id}/tokens`` (issue) — 201 happy
  path returning plaintext, 404 missing user, 400 deactivated user.
* ``GET /v1/admin/audit`` — happy path, ``actor_id`` + ``org_id``
  filters, ``limit`` bounds enforcement, 403 on viewer.
* ``POST /v1/admin/policy`` — happy path, 400 on plaintext-secret
  smell, 400 on invalid YAML, 403 on viewer.

Backward compatibility: the existing skeleton tests
(``tests/test_admin_api_skeleton.py``) cover health, auth, RBAC dep,
list-users, revoke-token, provider toggle. Those still pass without
modification.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_api import (
    RuntimeProviderRegistry,
    create_app,
    get_audit_log,
    get_identity_store,
    get_provider_registry,
)
from chuzom.enterprise.audit import AuditEvent, AuditLog
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False
    )


@pytest.fixture
def audit_log(tmp_path: Path) -> AuditLog:
    return AuditLog(
        db_path=tmp_path / "audit.db", check_same_thread=False
    )


@pytest.fixture
def registry() -> RuntimeProviderRegistry:
    return RuntimeProviderRegistry()


@pytest.fixture
def app_with_admin(
    store: IdentityStore,
    audit_log: AuditLog,
    registry: RuntimeProviderRegistry,
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    app.dependency_overrides[get_audit_log] = lambda: audit_log
    app.dependency_overrides[get_provider_registry] = lambda: registry
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def org_and_team(store: IdentityStore) -> tuple[str, str]:
    """Create one org + team; return their ids."""
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    return org.id, team.id


@pytest.fixture
def admin_token(store: IdentityStore, org_and_team) -> str:
    org_id, team_id = org_and_team
    user = store.create_user(
        org_id=org_id, team_id=team_id,
        email="admin@acme.test", display_name="Admin",
        role=Role.ADMIN,
    )
    return store.issue_token(user.id, name="admin-laptop").plaintext


@pytest.fixture
def viewer_token(store: IdentityStore, org_and_team) -> str:
    org_id, team_id = org_and_team
    user = store.create_user(
        org_id=org_id, team_id=team_id,
        email="emp@acme.test", display_name="Employee",
        role=Role.EMPLOYEE,
    )
    return store.issue_token(user.id, name="emp-cli").plaintext


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── POST /v1/admin/users ─────────────────────────────────────────────────────


def test_create_user_happy_path(
    app_with_admin: TestClient, admin_token: str, org_and_team
) -> None:
    org_id, team_id = org_and_team
    resp = app_with_admin.post(
        "/v1/admin/users",
        headers=_auth(admin_token),
        json={
            "org_id": org_id, "team_id": team_id,
            "email": "new@acme.test", "display_name": "New User",
            "role": "employee",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@acme.test"
    assert body["role"] == "employee"
    assert "token_hash" not in body


def test_create_user_role_case_insensitive(
    app_with_admin: TestClient, admin_token: str, org_and_team
) -> None:
    org_id, team_id = org_and_team
    resp = app_with_admin.post(
        "/v1/admin/users",
        headers=_auth(admin_token),
        json={
            "org_id": org_id, "team_id": team_id,
            "email": "mgr@acme.test", "display_name": "M",
            "role": "MANAGER",  # uppercase
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "manager"


def test_create_user_invalid_role_400(
    app_with_admin: TestClient, admin_token: str, org_and_team
) -> None:
    org_id, team_id = org_and_team
    resp = app_with_admin.post(
        "/v1/admin/users",
        headers=_auth(admin_token),
        json={
            "org_id": org_id, "team_id": team_id,
            "email": "x@y.z", "display_name": "X",
            "role": "viewer",  # not a real role
        },
    )
    assert resp.status_code == 400
    assert "viewer" in resp.json()["detail"]
    assert "admin" in resp.json()["detail"]  # lists valid roles


def test_create_user_missing_team_404(
    app_with_admin: TestClient, admin_token: str, org_and_team
) -> None:
    org_id, _ = org_and_team
    resp = app_with_admin.post(
        "/v1/admin/users",
        headers=_auth(admin_token),
        json={
            "org_id": org_id, "team_id": "does-not-exist",
            "email": "x@y.z", "display_name": "X", "role": "employee",
        },
    )
    assert resp.status_code == 404


def test_create_user_duplicate_email_409(
    app_with_admin: TestClient, admin_token: str, org_and_team
) -> None:
    org_id, team_id = org_and_team
    payload = {
        "org_id": org_id, "team_id": team_id,
        "email": "dup@acme.test", "display_name": "D", "role": "employee",
    }
    assert app_with_admin.post(
        "/v1/admin/users", headers=_auth(admin_token), json=payload
    ).status_code == 201
    again = app_with_admin.post(
        "/v1/admin/users", headers=_auth(admin_token), json=payload
    )
    assert again.status_code == 409


def test_create_user_viewer_forbidden(
    app_with_admin: TestClient, viewer_token: str, org_and_team
) -> None:
    org_id, team_id = org_and_team
    resp = app_with_admin.post(
        "/v1/admin/users",
        headers=_auth(viewer_token),
        json={
            "org_id": org_id, "team_id": team_id,
            "email": "x@y.z", "display_name": "X", "role": "employee",
        },
    )
    assert resp.status_code == 403


# ── POST /v1/admin/users/{user_id}/tokens ────────────────────────────────────


def test_issue_token_happy_path(
    app_with_admin: TestClient,
    admin_token: str,
    store: IdentityStore,
    org_and_team,
) -> None:
    org_id, team_id = org_and_team
    target = store.create_user(
        org_id=org_id, team_id=team_id,
        email="target@acme.test", display_name="T",
        role=Role.EMPLOYEE,
    )
    resp = app_with_admin.post(
        f"/v1/admin/users/{target.id}/tokens",
        headers=_auth(admin_token),
        json={"name": "automation-bot"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user_id"] == target.id
    assert body["name"] == "automation-bot"
    assert body["plaintext"].startswith("tsr_")
    # And the plaintext actually authenticates.
    me = app_with_admin.get(
        "/v1/admin/health", headers=_auth(body["plaintext"])
    )
    assert me.status_code == 200


def test_issue_token_missing_user_404(
    app_with_admin: TestClient, admin_token: str
) -> None:
    resp = app_with_admin.post(
        "/v1/admin/users/does-not-exist/tokens",
        headers=_auth(admin_token),
        json={"name": "x"},
    )
    assert resp.status_code == 404


def test_issue_token_for_deactivated_user_400(
    app_with_admin: TestClient,
    admin_token: str,
    store: IdentityStore,
    org_and_team,
) -> None:
    org_id, team_id = org_and_team
    target = store.create_user(
        org_id=org_id, team_id=team_id,
        email="zombie@acme.test", display_name="Z",
        role=Role.EMPLOYEE,
    )
    store.deactivate_user(target.id)
    resp = app_with_admin.post(
        f"/v1/admin/users/{target.id}/tokens",
        headers=_auth(admin_token),
        json={"name": "x"},
    )
    assert resp.status_code == 400


# ── GET /v1/admin/audit ──────────────────────────────────────────────────────


def test_get_audit_returns_recent_events(
    app_with_admin: TestClient, admin_token: str, audit_log: AuditLog
) -> None:
    for i in range(3):
        audit_log.append(
            AuditEvent(
                type="test", actor_id=f"a{i}", actor_email=f"a{i}@x",
                org_id="o", resource="r", action="act",
                detail={"i": i}, severity="info",
            )
        )
    resp = app_with_admin.get(
        "/v1/admin/audit", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 3
    # Default order is newest first.
    actor_ids = [r["actor_id"] for r in rows]
    assert actor_ids == ["a2", "a1", "a0"]


def test_get_audit_filters_by_actor(
    app_with_admin: TestClient, admin_token: str, audit_log: AuditLog
) -> None:
    audit_log.append(AuditEvent(
        type="t", actor_id="alice", actor_email="a@x",
        org_id="o", resource="r", action="x", detail={},
    ))
    audit_log.append(AuditEvent(
        type="t", actor_id="bob", actor_email="b@x",
        org_id="o", resource="r", action="y", detail={},
    ))
    resp = app_with_admin.get(
        "/v1/admin/audit?actor_id=bob", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["actor_id"] == "bob"


def test_get_audit_limit_bounds(
    app_with_admin: TestClient, admin_token: str
) -> None:
    too_big = app_with_admin.get(
        "/v1/admin/audit?limit=99999", headers=_auth(admin_token)
    )
    assert too_big.status_code == 400
    too_small = app_with_admin.get(
        "/v1/admin/audit?limit=0", headers=_auth(admin_token)
    )
    assert too_small.status_code == 400


def test_get_audit_viewer_forbidden(
    app_with_admin: TestClient, viewer_token: str
) -> None:
    resp = app_with_admin.get(
        "/v1/admin/audit", headers=_auth(viewer_token)
    )
    assert resp.status_code == 403


# ── POST /v1/admin/policy ────────────────────────────────────────────────────


def test_push_policy_happy_path(
    app_with_admin: TestClient, admin_token: str
) -> None:
    """G-007: ``POST /v1/admin/policy`` now versions the payload via
    ``PolicyVersionStore`` instead of writing a file. The default
    dependency wires a real store at ``~/.chuzom/policy_versions.db``;
    we just assert the API contract here (version returned, active).
    Detailed version semantics live in
    ``tests/test_policy_versioning.py`` where the store is overridden."""
    yaml_text = (
        "name: pilot\n"
        "providers:\n"
        "  openai:\n"
        "    api_key: ${env:OPENAI_API_KEY}\n"
    )
    resp = app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(admin_token),
        json={"yaml": yaml_text},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert isinstance(body["version"], int)
    assert body["version"] >= 1
    assert body["is_active"] is True


def test_push_policy_refuses_plaintext_secret(
    app_with_admin: TestClient, admin_token: str
) -> None:
    """The OrgPolicy plaintext-secret scanner catches raw API keys
    before they reach the versioned store."""
    bad_yaml = (
        "providers:\n"
        "  openai:\n"
        "    api_key: sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
    )
    resp = app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(admin_token),
        json={"yaml": bad_yaml},
    )
    assert resp.status_code == 400
    assert "plaintext" in resp.json()["detail"].lower()


def test_push_policy_refuses_invalid_yaml(
    app_with_admin: TestClient, admin_token: str, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CHUZOM_POLICY_PATH", str(tmp_path / "policy.yaml"))
    resp = app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(admin_token),
        json={"yaml": "not: yaml: nope:\n  - [unclosed"},
    )
    assert resp.status_code == 400


def test_push_policy_viewer_forbidden(
    app_with_admin: TestClient, viewer_token: str
) -> None:
    resp = app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(viewer_token),
        json={"yaml": "name: x\n"},
    )
    assert resp.status_code == 403
