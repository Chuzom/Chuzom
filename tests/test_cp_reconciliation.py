"""Iteration 13 acceptance — cross-instance reconciliation (#60)."""
from __future__ import annotations

import json
import sqlite3
import types

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_api import authenticate_identity
from chuzom.control_plane import audit as cpa
from chuzom.control_plane import signing
from chuzom.control_plane.api import create_control_plane_app, get_cp_store, get_signing_key
from chuzom.control_plane.reconciliation import (
    STATUS_BEHIND,
    STATUS_LAST_KNOWN_GOOD,
    STATUS_STALE,
    STATUS_UP_TO_DATE,
    reconcile_tenant_effective_policy,
)
from chuzom.control_plane.store import SqliteControlPlaneStore
from chuzom.enterprise.rbac import Permission


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUZOM_CP_AUDIT_PATH", str(tmp_path / "cp_audit.db"))
    cpa.reset_cp_audit_log_for_tests()
    s = SqliteControlPlaneStore(":memory:")
    # Active policy = v1.
    s.append_policy_version("t1", yaml_text="block_providers: []\n", normalized_json="{}", actor="a")
    s.set_active_policy("t1", 1)
    yield s
    s.close()
    cpa.reset_cp_audit_log_for_tests()


def _status_of(summary, instance_id):
    return next(i["status"] for i in summary["instances"] if i["instance_id"] == instance_id)


def test_all_up_to_date_converged(store) -> None:
    store.record_heartbeat(instance_id="i1", tenant_id="t1", effective_version=1,
                           effective_digest="d", source="control_plane")
    r = reconcile_tenant_effective_policy(store, "t1")
    assert r["active_version"] == 1
    assert _status_of(r, "i1") == STATUS_UP_TO_DATE
    assert r["all_converged"] is True
    assert r["audit_chain_status"] == "ok"


def test_behind_instance_flagged(store) -> None:
    store.append_policy_version("t1", yaml_text="block_providers: [openai]\n", normalized_json="{}", actor="a")
    store.set_active_policy("t1", 2)  # active is now v2
    store.record_heartbeat(instance_id="i1", tenant_id="t1", effective_version=1,
                           effective_digest="d", source="control_plane")  # still on v1
    r = reconcile_tenant_effective_policy(store, "t1")
    assert _status_of(r, "i1") == STATUS_BEHIND
    assert r["all_converged"] is False


def test_last_known_good_flagged(store) -> None:
    store.record_heartbeat(instance_id="i1", tenant_id="t1", effective_version=1,
                           effective_digest="d", source="last_known_good")
    r = reconcile_tenant_effective_policy(store, "t1")
    assert _status_of(r, "i1") == STATUS_LAST_KNOWN_GOOD
    assert r["all_converged"] is False


def test_stale_instance_flagged(store) -> None:
    store.record_heartbeat(instance_id="i1", tenant_id="t1", effective_version=1,
                           effective_digest="d", source="control_plane")
    last_seen = store.list_instances("t1")[0].last_seen_at
    # Reconcile "in the future" so the heartbeat is older than the stale window.
    r = reconcile_tenant_effective_policy(store, "t1", stale_after_s=120, now=last_seen + 1000)
    assert _status_of(r, "i1") == STATUS_STALE


def test_reconciliation_audit_row_written(store) -> None:
    reconcile_tenant_effective_policy(store, "t1")
    actions = {row["action"] for row in cpa.get_cp_audit_log().recent(limit=20)}
    assert cpa.ACTION_RECONCILIATION in actions


def test_tampered_chain_surfaces(store, tmp_path) -> None:
    # Write a couple of audit rows, then tamper the CP audit DB directly.
    cpa.audit_policy_created(tenant_id="t1", version=1, digest="d1")
    cpa.audit_policy_activated(tenant_id="t1", version=1, digest="d1")
    cpa.reset_cp_audit_log_for_tests()
    db = tmp_path / "cp_audit.db"
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE audit_events SET detail = ? WHERE seq = (SELECT MIN(seq) FROM audit_events)",
                 (json.dumps({"forged": True}),))
    conn.commit()
    conn.close()
    cpa.reset_cp_audit_log_for_tests()
    r = reconcile_tenant_effective_policy(store, "t1", audit=False)  # don't append (chain is broken)
    assert r["audit_chain_status"] == "tampered"


def test_reconciliation_endpoint(store) -> None:
    def _fake_admin():
        return types.SimpleNamespace(
            permissions=frozenset({Permission.MANAGE_POLICY}),
            user=types.SimpleNamespace(email="a@t"), user_id="a", org_id="o",
        )
    store.record_heartbeat(instance_id="i1", tenant_id="t1", effective_version=1,
                           effective_digest="d", source="control_plane")
    app = create_control_plane_app()
    app.dependency_overrides[get_cp_store] = lambda: store
    app.dependency_overrides[get_signing_key] = lambda: signing.generate_ed25519_keypair()
    app.dependency_overrides[authenticate_identity] = _fake_admin
    c = TestClient(app)
    r = c.get("/cp/v1/tenants/t1/reconciliation")
    assert r.status_code == 200
    assert r.json()["all_converged"] is True
    app.dependency_overrides.clear()
