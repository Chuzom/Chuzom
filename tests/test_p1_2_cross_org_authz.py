"""P1-2 — org_id is an authorization boundary in the admin API.

MANAGE_USERS previously granted visibility/control over EVERY org's users:
``list_users`` returned all tenants, and the token/create endpoints accepted any
user_id/org_id. An org-A admin could enumerate, create, and revoke against
org-B. These tests pin the boundary: an admin only ever sees/acts within its
own org, and cross-org access is indistinguishable from "not found" (404).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_api import create_app, get_identity_store
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(db_path=tmp_path / "identity.db", check_same_thread=False)


@pytest.fixture
def two_orgs(store: IdentityStore):
    """org A (with an admin) and org B (with one employee)."""
    org_a = store.create_org(name="org-a")
    team_a = store.create_team(org_a.id, "team-a")
    admin_a = store.create_user(
        org_id=org_a.id, team_id=team_a.id, email="admin@a.test",
        display_name="A Admin", role=Role.ADMIN,
    )
    token_a = store.issue_token(admin_a.id, name="a-admin").plaintext

    org_b = store.create_org(name="org-b")
    team_b = store.create_team(org_b.id, "team-b")
    user_b = store.create_user(
        org_id=org_b.id, team_id=team_b.id, email="emp@b.test",
        display_name="B Emp", role=Role.EMPLOYEE,
    )
    return {
        "org_a": org_a.id, "team_a": team_a.id, "token_a": token_a,
        "org_b": org_b.id, "team_b": team_b.id, "user_b": user_b.id,
    }


@pytest.fixture
def client(store) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_list_users_is_scoped_to_caller_org(client, two_orgs):
    r = client.get("/v1/admin/users", headers=_auth(two_orgs["token_a"]))
    assert r.status_code == 200
    orgs_seen = {u["org_id"] for u in r.json()}
    assert orgs_seen == {two_orgs["org_a"]}  # never org-b
    assert two_orgs["user_b"] not in {u["id"] for u in r.json()}


def test_cannot_create_user_in_another_org(client, two_orgs):
    r = client.post(
        "/v1/admin/users",
        headers=_auth(two_orgs["token_a"]),
        json={
            "org_id": two_orgs["org_b"], "team_id": two_orgs["team_b"],
            "email": "intruder@b.test", "display_name": "Intruder",
            "role": "employee",
        },
    )
    assert r.status_code == 403


def test_cannot_issue_token_for_cross_org_user(client, two_orgs):
    r = client.post(
        f"/v1/admin/users/{two_orgs['user_b']}/tokens",
        headers=_auth(two_orgs["token_a"]),
        json={"name": "stolen"},
    )
    assert r.status_code == 404  # existence not disclosed


def test_cannot_revoke_token_for_cross_org_user(client, two_orgs):
    r = client.post(
        f"/v1/admin/users/{two_orgs['user_b']}/tokens/whatever:revoke",
        headers=_auth(two_orgs["token_a"]),
    )
    assert r.status_code == 404


def test_same_org_create_still_works(client, two_orgs):
    r = client.post(
        "/v1/admin/users",
        headers=_auth(two_orgs["token_a"]),
        json={
            "org_id": two_orgs["org_a"], "team_id": two_orgs["team_a"],
            "email": "new@a.test", "display_name": "New A", "role": "employee",
        },
    )
    assert r.status_code == 201, r.text
