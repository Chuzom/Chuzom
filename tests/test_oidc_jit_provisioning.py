"""JIT provisioning: OIDC claims → a chuzom Identity via IdentityStore."""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom.enterprise.identity import IdentityNotFound, IdentityStore
from chuzom.enterprise.rbac import Role


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    s = IdentityStore(db_path=tmp_path / "identity.db")
    org = s.create_org("acme")
    s.create_team(org.id, "default")
    yield s
    s.close()


def _org_team(store: IdentityStore) -> tuple[str, str]:
    """Return the (org_id, team_id) created by the `store` fixture."""
    org_id = store._conn.execute("SELECT id FROM orgs LIMIT 1").fetchone()[0]
    team_id = store._conn.execute("SELECT id FROM teams LIMIT 1").fetchone()[0]
    return org_id, team_id


def test_jit_creates_user_on_first_login(store):
    org_id, team_id = _org_team(store)
    user = store.get_or_create_by_external_id(
        external_id="okta|abc",
        email="dev@acme.com",
        display_name="Dev",
        role=Role.EMPLOYEE,
        org_id=org_id,
        team_id=team_id,
    )
    assert user.external_id == "okta|abc"
    assert user.email == "dev@acme.com"
    assert user.role == Role.EMPLOYEE
    # Idempotent: a second login returns the same user, not a duplicate.
    again = store.get_or_create_by_external_id(
        external_id="okta|abc",
        email="dev@acme.com",
        display_name="Dev",
        role=Role.EMPLOYEE,
        org_id=org_id,
        team_id=team_id,
    )
    assert again.id == user.id


def test_jit_links_external_id_to_preprovisioned_email(store):
    org_id, team_id = _org_team(store)
    # Admin pre-creates the user (no external_id) before their first SSO login.
    pre = store.create_user(
        org_id=org_id, team_id=team_id, email="lead@acme.com",
        display_name="Lead", role=Role.MANAGER,
    )
    assert pre.external_id == ""
    linked = store.get_or_create_by_external_id(
        external_id="entra|xyz",
        email="lead@acme.com",
        display_name="Lead",
        role=Role.EMPLOYEE,  # IdP role ignored when binding existing user
        org_id=org_id, team_id=team_id,
    )
    assert linked.id == pre.id
    assert linked.external_id == "entra|xyz"
    assert linked.role == Role.MANAGER  # preserved, not downgraded on link


def test_get_user_by_external_id_empty_never_matches(store):
    with pytest.raises(IdentityNotFound):
        store.get_user_by_external_id("")
