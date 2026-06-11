"""G-007 — versioned policy store + rollback endpoints.

Replaces the file-based ``POST /v1/admin/policy`` with an
append-only versioned store. Operators can:

* Push a new version (validated against the same plaintext-secret
  + YAML-parse contract as the prior endpoint).
* List the history (newest first, metadata only).
* Fetch the YAML body of a specific version.
* Roll back to any prior version (appends a *new* row copying the
  prior YAML; rollback is itself versioned).

Each mutation emits an admin-action row via G-006-F5 so the
"who pushed v17 last Tuesday" question has a single SQL answer.
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
    get_policy_version_store,
    get_provider_registry,
)
from chuzom.enterprise.audit import AuditLog
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role
from chuzom.policy_versions import (
    PolicyValidationError,
    PolicyVersionNotFound,
    PolicyVersionStore,
)


# ── 1. PolicyVersionStore primitive ─────────────────────────────────────────


@pytest.fixture
def policy_store(tmp_path: Path) -> PolicyVersionStore:
    return PolicyVersionStore(
        db_path=tmp_path / "policy_versions.db", check_same_thread=False
    )


def test_push_creates_active_version(policy_store: PolicyVersionStore) -> None:
    meta = policy_store.push(
        yaml_text="name: v1\n",
        actor_user_id="u",
        actor_email="u@x",
    )
    assert meta["version"] == 1
    assert meta["is_active"] is True
    assert policy_store.active_version() == 1


def test_push_appends_versions_monotonically(
    policy_store: PolicyVersionStore,
) -> None:
    for i in range(1, 6):
        meta = policy_store.push(
            yaml_text=f"name: v{i}\n",
            actor_user_id="u",
            actor_email="u@x",
        )
        assert meta["version"] == i
        assert meta["is_active"] is True
    # The 5th push is the active one.
    assert policy_store.active_version() == 5
    # Old versions are still retrievable.
    v2 = policy_store.get(2)
    assert v2["yaml_text"] == "name: v2\n"


def test_validate_refuses_plaintext_secret(
    policy_store: PolicyVersionStore,
) -> None:
    bad = (
        "providers:\n"
        "  openai:\n"
        "    api_key: sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
    )
    with pytest.raises(PolicyValidationError):
        policy_store.push(
            yaml_text=bad,
            actor_user_id="u", actor_email="u@x",
        )
    # And no row was inserted.
    assert policy_store.list_versions() == []


def test_validate_refuses_unparseable_yaml(
    policy_store: PolicyVersionStore,
) -> None:
    with pytest.raises(PolicyValidationError):
        policy_store.push(
            yaml_text="not: yaml: nope:\n  - [unclosed",
            actor_user_id="u", actor_email="u@x",
        )


def test_rollback_appends_new_active_version(
    policy_store: PolicyVersionStore,
) -> None:
    policy_store.push(yaml_text="name: v1\n", actor_user_id="u", actor_email="u@x")
    policy_store.push(yaml_text="name: v2\n", actor_user_id="u", actor_email="u@x")
    policy_store.push(yaml_text="name: v3\n", actor_user_id="u", actor_email="u@x")
    assert policy_store.active_version() == 3

    rolled = policy_store.rollback(
        target_version=1,
        actor_user_id="ops", actor_email="ops@x",
        note="incident-2026-06-10",
    )
    assert rolled["version"] == 4
    assert policy_store.active_version() == 4
    # The new active row's body matches v1 exactly.
    active_body = policy_store.get_active()
    assert active_body is not None
    assert active_body["yaml_text"] == "name: v1\n"
    assert active_body["parent_version"] == 1
    assert "incident-2026-06-10" in active_body["note"]


def test_rollback_to_missing_version_raises(
    policy_store: PolicyVersionStore,
) -> None:
    policy_store.push(yaml_text="name: v1\n", actor_user_id="u", actor_email="u@x")
    with pytest.raises(PolicyVersionNotFound):
        policy_store.rollback(
            target_version=999,
            actor_user_id="u", actor_email="u@x",
        )


def test_list_versions_newest_first_metadata_only(
    policy_store: PolicyVersionStore,
) -> None:
    for i in range(1, 4):
        policy_store.push(
            yaml_text=f"name: v{i}\n", actor_user_id="u", actor_email="u@x"
        )
    rows = policy_store.list_versions(limit=10)
    assert [r["version"] for r in rows] == [3, 2, 1]
    # Heavy YAML body is omitted from the listing.
    assert "yaml_text" not in rows[0]
    assert rows[0]["yaml_bytes"] == len("name: v3\n")
    assert rows[0]["is_active"] is True
    assert rows[1]["is_active"] is False


# ── 2. Admin-API integration ───────────────────────────────────────────────


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
    policy_store: PolicyVersionStore,
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    app.dependency_overrides[get_audit_log] = lambda: audit_log
    app.dependency_overrides[get_admin_action_log] = lambda: admin_log
    app.dependency_overrides[get_provider_registry] = lambda: registry
    app.dependency_overrides[get_policy_version_store] = lambda: policy_store
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


def test_push_returns_version_metadata(
    app_with_admin: TestClient, admin_token: str
) -> None:
    resp = app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(admin_token),
        json={"yaml": "name: pilot\n", "note": "initial"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 1
    assert body["is_active"] is True
    assert "rollback" in body["note"].lower()


def test_push_refuses_plaintext_secret(
    app_with_admin: TestClient, admin_token: str
) -> None:
    resp = app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(admin_token),
        json={"yaml": (
            "providers:\n"
            "  openai:\n"
            "    api_key: sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
        )},
    )
    assert resp.status_code == 400


def test_list_versions_endpoint(
    app_with_admin: TestClient, admin_token: str
) -> None:
    for i in range(1, 4):
        app_with_admin.post(
            "/v1/admin/policy",
            headers=_auth(admin_token),
            json={"yaml": f"name: v{i}\n"},
        )
    resp = app_with_admin.get(
        "/v1/admin/policy/versions", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["version"] for r in rows] == [3, 2, 1]
    assert rows[0]["is_active"] is True


def test_get_version_body_endpoint(
    app_with_admin: TestClient, admin_token: str
) -> None:
    app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(admin_token),
        json={"yaml": "name: special\n"},
    )
    resp = app_with_admin.get(
        "/v1/admin/policy/versions/1", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["yaml_text"] == "name: special\n"


def test_get_missing_version_404(
    app_with_admin: TestClient, admin_token: str
) -> None:
    resp = app_with_admin.get(
        "/v1/admin/policy/versions/999", headers=_auth(admin_token)
    )
    assert resp.status_code == 404


def test_rollback_endpoint_promotes_prior_version(
    app_with_admin: TestClient, admin_token: str
) -> None:
    for i in range(1, 4):
        app_with_admin.post(
            "/v1/admin/policy",
            headers=_auth(admin_token),
            json={"yaml": f"name: v{i}\n"},
        )
    rb = app_with_admin.post(
        "/v1/admin/policy/rollback",
        headers=_auth(admin_token),
        json={"target_version": 1, "note": "incident"},
    )
    assert rb.status_code == 200
    body = rb.json()
    assert body["rolled_back"] is True
    assert body["new_version"] == 4
    assert body["target_version"] == 1

    # Active body is v1's content.
    active = app_with_admin.get(
        "/v1/admin/policy/versions/4", headers=_auth(admin_token)
    )
    assert active.json()["yaml_text"] == "name: v1\n"


def test_rollback_to_missing_version_404(
    app_with_admin: TestClient, admin_token: str
) -> None:
    resp = app_with_admin.post(
        "/v1/admin/policy/rollback",
        headers=_auth(admin_token),
        json={"target_version": 99, "note": "x"},
    )
    assert resp.status_code == 404


def test_viewer_cannot_push_or_rollback(
    app_with_admin: TestClient, viewer_token: str
) -> None:
    push_resp = app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(viewer_token),
        json={"yaml": "name: x\n"},
    )
    assert push_resp.status_code == 403
    rb_resp = app_with_admin.post(
        "/v1/admin/policy/rollback",
        headers=_auth(viewer_token),
        json={"target_version": 1},
    )
    assert rb_resp.status_code == 403


def test_push_and_rollback_emit_admin_actions(
    app_with_admin: TestClient,
    admin_token: str,
    admin_log: AdminActionLog,
) -> None:
    pre = admin_log.count()
    app_with_admin.post(
        "/v1/admin/policy",
        headers=_auth(admin_token),
        json={"yaml": "name: v1\n"},
    )
    app_with_admin.post(
        "/v1/admin/policy/rollback",
        headers=_auth(admin_token),
        json={"target_version": 1},
    )
    assert admin_log.count() == pre + 2
    rows = admin_log.recent(limit=2)
    actions = {r["action"] for r in rows}
    assert actions == {"policy:push", "policy:rollback"}
