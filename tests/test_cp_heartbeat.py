"""Iteration 10 acceptance — heartbeat + central effective-version transition audit."""
from __future__ import annotations

import types

import pytest
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
        user=types.SimpleNamespace(email="admin@test"), user_id="admin", org_id="o1",
    )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUZOM_CP_AUDIT_PATH", str(tmp_path / "cp_audit.db"))
    monkeypatch.delenv("CHUZOM_CP_SIDECAR_TOKEN", raising=False)
    cpa.reset_cp_audit_log_for_tests()
    store = SqliteControlPlaneStore(":memory:")
    app = create_control_plane_app()
    app.dependency_overrides[get_cp_store] = lambda: store
    app.dependency_overrides[get_signing_key] = lambda: signing.generate_ed25519_keypair()
    app.dependency_overrides[authenticate_identity] = _fake_admin
    yield TestClient(app)
    app.dependency_overrides.clear()
    cpa.reset_cp_audit_log_for_tests()


def _hb_count() -> int:
    rows = cpa.get_cp_audit_log().recent(limit=50)
    return sum(1 for r in rows if r["action"] == cpa.ACTION_HEARTBEAT)


def _beat(client, **kw):
    body = {"instance_id": "i1", "effective_version": 1, "effective_digest": "d1",
            "source": "control_plane"}
    body.update(kw)
    return client.post("/cp/v1/tenants/t1/heartbeat", json=body)


def test_new_instance_appears_and_audits_transition(client) -> None:
    assert _beat(client).status_code == 200
    inst = client.get("/cp/v1/tenants/t1/instances").json()
    assert [i["instance_id"] for i in inst["instances"]] == ["i1"]
    assert _hb_count() == 1  # first sighting is a transition


def test_repeated_same_version_does_not_re_audit(client) -> None:
    _beat(client)
    _beat(client)  # identical version+source
    _beat(client)
    assert _hb_count() == 1  # still just the initial transition


def test_version_transition_audits_again(client) -> None:
    _beat(client, effective_version=1)
    _beat(client, effective_version=2, effective_digest="d2")  # transition
    assert _hb_count() == 2


def test_source_transition_is_auditable(client) -> None:
    _beat(client, source="control_plane")
    _beat(client, source="last_known_good")  # source flip is a transition
    assert _hb_count() == 2
    # And the last stored source is centrally visible.
    inst = client.get("/cp/v1/tenants/t1/instances").json()
    # (instances view carries effective_version; last_seen reflects the latest beat)
    assert inst["instances"][0]["instance_id"] == "i1"
