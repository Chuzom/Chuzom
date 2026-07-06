"""Iteration 7 acceptance — signed current-policy endpoint (closes #41)."""
from __future__ import annotations

import types

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_api import authenticate_identity
from chuzom.control_plane import audit as cpa
from chuzom.control_plane import signing
from chuzom.control_plane.api import create_control_plane_app, get_cp_store, get_signing_key
from chuzom.control_plane.policy_bundle import bundle_payload_bytes, make_payload
from chuzom.control_plane.store import SqliteControlPlaneStore
from chuzom.enterprise.rbac import Permission


def _fake_admin():
    return types.SimpleNamespace(
        permissions=frozenset({Permission.MANAGE_POLICY}),
        user=types.SimpleNamespace(email="admin@test"),
        user_id="admin", org_id="o1",
    )


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUZOM_CP_AUDIT_PATH", str(tmp_path / "cp_audit.db"))
    monkeypatch.delenv("CHUZOM_CP_SIDECAR_TOKEN", raising=False)
    cpa.reset_cp_audit_log_for_tests()
    store = SqliteControlPlaneStore(":memory:")
    key = signing.generate_ed25519_keypair()
    app = create_control_plane_app()
    app.dependency_overrides[get_cp_store] = lambda: store
    app.dependency_overrides[get_signing_key] = lambda: key
    app.dependency_overrides[authenticate_identity] = _fake_admin
    client = TestClient(app)
    yield client, key
    app.dependency_overrides.clear()
    cpa.reset_cp_audit_log_for_tests()


def test_signed_bundle_verifies_with_public_key(ctx) -> None:
    client, key = ctx
    client.post("/cp/v1/tenants/t1/policy", json={"yaml_text": "block_providers: [openai]\n"})
    r = client.get("/cp/v1/tenants/t1/policy/current")
    assert r.status_code == 200
    body = r.json()
    assert body["signature_algorithm"] == "ed25519"
    assert body["signature_b64"] and body["public_key_b64"]

    # A sidecar re-derives the canonical payload from the response and verifies.
    payload = make_payload(
        tenant_id=body["tenant_id"], version=body["version"],
        issued_at=body["created_at"], yaml_text=body["yaml_text"],
    )
    ok = signing.verify_payload(body["public_key_b64"], bundle_payload_bytes(payload), body["signature_b64"])
    assert ok is True


def test_tampered_policy_fails_verification(ctx) -> None:
    client, key = ctx
    client.post("/cp/v1/tenants/t1/policy", json={"yaml_text": "block_providers: [openai]\n"})
    body = client.get("/cp/v1/tenants/t1/policy/current").json()
    # Forge a different policy but keep the real signature -> must NOT verify.
    forged = make_payload(tenant_id=body["tenant_id"], version=body["version"],
                          issued_at=body["created_at"], yaml_text="block_providers: [anthropic]\n")
    assert signing.verify_payload(body["public_key_b64"], bundle_payload_bytes(forged), body["signature_b64"]) is False


def test_public_key_endpoint(ctx) -> None:
    client, key = ctx
    r = client.get("/cp/v1/public-key")
    assert r.status_code == 200
    assert r.json()["public_key_b64"] == signing.public_key_b64(key)


def test_404_when_no_active_policy(ctx) -> None:
    client, _ = ctx
    assert client.get("/cp/v1/tenants/none/policy/current").status_code == 404


def test_bundle_served_audit_written(ctx) -> None:
    client, _ = ctx
    client.post("/cp/v1/tenants/t1/policy", json={"yaml_text": "block_providers: []\n"})
    client.get("/cp/v1/tenants/t1/policy/current")
    actions = {row["action"] for row in cpa.get_cp_audit_log().recent(limit=10)}
    assert cpa.ACTION_BUNDLE_SERVED in actions


def test_no_private_key_in_response(ctx) -> None:
    client, key = ctx
    client.post("/cp/v1/tenants/t1/policy", json={"yaml_text": "block_providers: []\n"})
    raw = client.get("/cp/v1/tenants/t1/policy/current").text
    assert signing.private_key_b64(key) not in raw
