"""Iteration 6 acceptance — control-plane FastAPI contract (#43)."""
from __future__ import annotations

import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from chuzom.admin_api import authenticate_identity
from chuzom.control_plane import audit as cpa
from chuzom.control_plane import signing
from chuzom.control_plane.api import create_control_plane_app, get_cp_store, get_signing_key
from chuzom.control_plane.store import SqliteControlPlaneStore
from chuzom.enterprise.rbac import Permission


def _fake_admin():
    return types.SimpleNamespace(
        permissions=frozenset({Permission.MANAGE_POLICY}),
        user=types.SimpleNamespace(email="admin@test"),
        user_id="admin", org_id="o1",
    )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUZOM_CP_AUDIT_PATH", str(tmp_path / "cp_audit.db"))
    monkeypatch.delenv("CHUZOM_CP_SIDECAR_TOKEN", raising=False)  # dev-open sidecar
    cpa.reset_cp_audit_log_for_tests()
    store = SqliteControlPlaneStore(":memory:")
    app = create_control_plane_app()
    app.dependency_overrides[get_cp_store] = lambda: store
    app.dependency_overrides[get_signing_key] = lambda: signing.generate_ed25519_keypair()
    app.dependency_overrides[authenticate_identity] = _fake_admin
    yield TestClient(app)
    app.dependency_overrides.clear()
    cpa.reset_cp_audit_log_for_tests()


def test_health_no_auth(client) -> None:
    r = client.get("/cp/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_current_policy_404_before_push(client) -> None:
    assert client.get("/cp/v1/tenants/t1/policy/current").status_code == 404


def test_admin_push_then_sidecar_fetches_current(client) -> None:
    push = client.post("/cp/v1/tenants/t1/policy", json={"yaml_text": "block_providers: [openai]\n"})
    assert push.status_code == 200, push.text
    body = push.json()
    assert body["version"] == 1 and len(body["digest"]) == 64

    cur = client.get("/cp/v1/tenants/t1/policy/current")
    assert cur.status_code == 200
    assert cur.json()["version"] == 1
    assert cur.json()["digest"] == body["digest"]  # same canonical digest


def test_sidecar_heartbeat_then_admin_sees_instance(client) -> None:
    client.post("/cp/v1/tenants/t1/policy", json={"yaml_text": "block_providers: []\n"})
    hb = client.post("/cp/v1/tenants/t1/heartbeat", json={
        "instance_id": "i1", "effective_version": 1, "effective_digest": "d",
        "source": "control_plane",
    })
    assert hb.status_code == 200 and hb.json()["ok"] is True

    inst = client.get("/cp/v1/tenants/t1/instances")
    assert inst.status_code == 200
    data = inst.json()
    assert data["active_version"] == 1
    assert [i["instance_id"] for i in data["instances"]] == ["i1"]


def test_admin_route_rejects_unauthenticated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHUZOM_CP_AUDIT_PATH", str(tmp_path / "a.db"))
    cpa.reset_cp_audit_log_for_tests()
    app = create_control_plane_app()
    app.dependency_overrides[get_cp_store] = lambda: SqliteControlPlaneStore(":memory:")

    def _deny():
        raise HTTPException(status_code=401, detail="no creds")

    app.dependency_overrides[authenticate_identity] = _deny
    c = TestClient(app)
    assert c.post("/cp/v1/tenants/t1/policy", json={"yaml_text": "block_providers: []\n"}).status_code == 401
    app.dependency_overrides.clear()


def test_openapi_includes_models(client) -> None:
    schema = client.get("/openapi.json").json()
    names = set(schema.get("components", {}).get("schemas", {}))
    assert {"PolicyPushRequest", "CurrentPolicyResponse", "HeartbeatRequest", "TenantAuditStatus"} <= names
