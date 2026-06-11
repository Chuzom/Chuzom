"""P1-6 — SCIM provisioning maps an IdP role/title to a chuzom Role.

SCIM create previously hardcoded ``Role.EMPLOYEE``, so an IdP could never
provision a manager or admin via SCIM (OIDC could, via CHUZOM_OIDC_ROLE_MAP).
This mirrors that idiom with CHUZOM_SCIM_ROLE_MAP over the SCIM ``roles``/``title``
attributes; unmapped users still default to least-privilege EMPLOYEE.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role
from chuzom.enterprise.scim import extract_role, parse_role_map
from chuzom.scim_api import create_scim_app


# ── unit: parse_role_map ─────────────────────────────────────────────────────

def test_parse_role_map_skips_unknown_roles():
    m = parse_role_map("admins=admin,mgrs=manager,x=not-a-role")
    assert m == {"admins": Role.ADMIN, "mgrs": Role.MANAGER}


def test_parse_role_map_empty():
    assert parse_role_map("") == {}


# ── unit: extract_role ───────────────────────────────────────────────────────

def test_extract_role_prefers_primary_role_value():
    rm = {"admin-grp": Role.ADMIN, "eng": Role.EMPLOYEE}
    payload = {"roles": [{"value": "eng"}, {"value": "admin-grp", "primary": True}]}
    assert extract_role(payload, rm) == Role.ADMIN


def test_extract_role_falls_back_to_title():
    rm = {"Engineering Manager": Role.MANAGER}
    assert extract_role({"title": "Engineering Manager"}, rm) == Role.MANAGER


def test_extract_role_defaults_to_employee_when_unmapped():
    assert extract_role({"title": "Random Title"}, {"x": Role.ADMIN}) == Role.EMPLOYEE


def test_extract_role_handles_string_roles():
    rm = {"superuser": Role.ADMIN}
    assert extract_role({"roles": ["superuser"]}, rm) == Role.ADMIN


# ── e2e through the SCIM router ──────────────────────────────────────────────

def _client(store) -> TestClient:
    return TestClient(create_scim_app(store=store, scim_token="scim-secret"))


def test_scim_create_maps_role(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CHUZOM_SCIM_ROLE_MAP", "platform-admins=admin")
    store = IdentityStore(db_path=tmp_path / "id.db", check_same_thread=False)
    r = _client(store).post(
        "/scim/v2/Users",
        headers={"Authorization": "Bearer scim-secret"},
        json={
            "userName": "boss@corp.io",
            "roles": [{"value": "platform-admins", "primary": True}],
        },
    )
    assert r.status_code == 201, r.text
    assert store.get_user_by_email("boss@corp.io").role == Role.ADMIN


def test_scim_create_defaults_employee_without_map(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CHUZOM_SCIM_ROLE_MAP", raising=False)
    store = IdentityStore(db_path=tmp_path / "id.db", check_same_thread=False)
    r = _client(store).post(
        "/scim/v2/Users",
        headers={"Authorization": "Bearer scim-secret"},
        json={"userName": "emp@corp.io", "roles": [{"value": "whatever"}]},
    )
    assert r.status_code == 201, r.text
    assert store.get_user_by_email("emp@corp.io").role == Role.EMPLOYEE
