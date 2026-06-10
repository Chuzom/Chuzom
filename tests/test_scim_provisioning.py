"""SCIM 2.0 provisioning — mapping units + HTTP CRUD with bearer auth."""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom.enterprise import scim
from chuzom.enterprise.identity import IdentityStore, User
from chuzom.enterprise.rbac import Role

SCIM_TOKEN = "scim-secret-token"


# ── Mapping-layer units (pure, no server) ─────────────────────────────────────

def test_extract_user_fields_from_username():
    f = scim.extract_user_fields({"userName": "a@acme.com", "active": True})
    assert f["email"] == "a@acme.com"
    assert f["active"] is True


def test_extract_user_fields_from_emails_when_no_username():
    f = scim.extract_user_fields(
        {"emails": [{"value": "x@acme.com", "primary": True}], "displayName": "X"}
    )
    assert f["email"] == "x@acme.com"
    assert f["display_name"] == "X"


def test_patch_sets_inactive_path_form():
    assert scim.patch_sets_inactive(
        {"Operations": [{"op": "replace", "path": "active", "value": False}]}
    )


def test_patch_sets_inactive_value_object_form():
    assert scim.patch_sets_inactive(
        {"Operations": [{"op": "replace", "value": {"active": False}}]}
    )


def test_patch_active_true_is_not_deactivation():
    assert not scim.patch_sets_inactive(
        {"Operations": [{"op": "replace", "path": "active", "value": True}]}
    )


def test_user_to_scim_shape():
    u = User(id="u1", org_id="o1", team_id="t1", email="a@acme.com",
             display_name="A", role=Role.EMPLOYEE, external_id="okta|1")
    doc = scim.user_to_scim(u)
    assert doc["userName"] == "a@acme.com"
    assert doc["externalId"] == "okta|1"
    assert doc["active"] is True
    assert scim.USER_SCHEMA in doc["schemas"]


# ── HTTP CRUD (FastAPI TestClient) ────────────────────────────────────────────

@pytest.fixture
def client(tmp_path: Path):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from chuzom.scim_api import create_scim_app

    # TestClient dispatches handlers on a worker thread, so the SQLite
    # connection must allow cross-thread use (production does the same).
    store = IdentityStore(db_path=tmp_path / "identity.db", check_same_thread=False)
    app = create_scim_app(store=store, scim_token=SCIM_TOKEN)
    with TestClient(app) as c:
        yield c, store
    store.close()


def _auth(tok: str = SCIM_TOKEN) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def test_scim_requires_auth(client):
    c, _ = client
    r = c.post("/scim/v2/Users", json={"userName": "z@acme.com"})
    assert r.status_code == 401


def test_scim_rejects_wrong_token(client):
    c, _ = client
    r = c.get("/scim/v2/Users/anything", headers=_auth("wrong"))
    assert r.status_code == 401


def test_scim_create_user(client):
    c, store = client
    r = c.post(
        "/scim/v2/Users",
        headers=_auth(),
        json={"userName": "new@acme.com", "externalId": "entra|7", "active": True},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["userName"] == "new@acme.com"
    assert body["externalId"] == "entra|7"
    # It really landed in the store.
    assert store.get_user_by_email("new@acme.com").external_id == "entra|7"


def test_scim_get_and_filter(client):
    c, _ = client
    created = c.post("/scim/v2/Users", headers=_auth(),
                     json={"userName": "find@acme.com"}).json()
    got = c.get(f"/scim/v2/Users/{created['id']}", headers=_auth())
    assert got.status_code == 200 and got.json()["userName"] == "find@acme.com"

    listed = c.get('/scim/v2/Users?filter=userName eq "find@acme.com"', headers=_auth())
    assert listed.json()["totalResults"] == 1


def test_scim_deprovision_via_patch_revokes_access(client):
    c, store = client
    created = c.post("/scim/v2/Users", headers=_auth(),
                     json={"userName": "gone@acme.com"}).json()
    user_id = created["id"]
    # Give the user a live token, then deprovision.
    token = store.issue_token(user_id, name="laptop")
    assert token.is_active

    r = c.patch(
        f"/scim/v2/Users/{user_id}",
        headers=_auth(),
        json={"schemas": [scim.PATCH_SCHEMA],
              "Operations": [{"op": "replace", "path": "active", "value": False}]},
    )
    assert r.status_code == 200
    assert r.json()["active"] is False
    # Deactivated AND tokens revoked → authenticate now fails.
    from chuzom.enterprise.identity import InvalidToken
    assert not store.get_user(user_id).active
    with pytest.raises(InvalidToken):
        store.authenticate(token.plaintext)


def test_scim_delete_is_soft(client):
    c, store = client
    created = c.post("/scim/v2/Users", headers=_auth(),
                     json={"userName": "del@acme.com"}).json()
    r = c.delete(f"/scim/v2/Users/{created['id']}", headers=_auth())
    assert r.status_code == 204
    assert not store.get_user(created["id"]).active  # soft delete, row preserved


def test_scim_get_missing_user_404(client):
    c, _ = client
    assert c.get("/scim/v2/Users/nope", headers=_auth()).status_code == 404
