"""Iteration 14 — G-004 END-TO-END green cell (#61).

Proves both G-004 acceptance criteria in-process:
  (a) a control-plane policy change reaches ALL instances within a 5s SLO;
  (b) the effective policy at every instance is centrally auditable.
Plus the point of it all: enforcement actually changes (a blocked model is
dropped through the router's policy seam), and the control-plane audit chain
verifies.

The sidecars use their REAL CPClient HTTP path, bridged to the REAL FastAPI app
via a MockTransport that forwards to a TestClient (httpx ASGITransport is
async-only, so we cannot point the sync CPClient at it directly).
"""
from __future__ import annotations

import time
import types

import httpx
import pytest
from fastapi.testclient import TestClient

from chuzom.admin_api import authenticate_identity
from chuzom.control_plane import audit as cpa
from chuzom.control_plane import signing
from chuzom.control_plane.api import create_control_plane_app, get_cp_store, get_signing_key
from chuzom.control_plane.events import reset_event_bus_for_tests
from chuzom.control_plane.reconciliation import reconcile_tenant_effective_policy
from chuzom.control_plane.store import SqliteControlPlaneStore
from chuzom.control_plane.client import CPClient
from chuzom.tenant_policy_sidecar import (
    TenantPolicySidecar,
    TenantPolicySidecarConfig,
)
from chuzom.policy import apply_policy
from chuzom.policy_runtime import (
    get_effective_org_policy,
    install_effective_org_policy,
    reset_effective_policy_for_tests,
)

TENANT = "t1"
BLOCKED_MODEL = "codex/gpt-5.5"
CANDIDATES = ["ollama/qwen3:32b", BLOCKED_MODEL]
ALLOW_YAML = "block_providers: []\nblock_models: []\n"
BLOCK_YAML = f'block_providers: []\nblock_models: ["{BLOCKED_MODEL}"]\n'


def _forwarding_transport(tc: TestClient) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        r = tc.request(
            request.method,
            request.url.path,
            content=request.content,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
        )
        return httpx.Response(status_code=r.status_code, content=r.content,
                              headers={"content-type": r.headers.get("content-type", "application/json")})
    return httpx.MockTransport(handler)


@pytest.fixture()
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUZOM_CP_AUDIT_PATH", str(tmp_path / "cp_audit.db"))
    monkeypatch.delenv("CHUZOM_CP_SIDECAR_TOKEN", raising=False)
    cpa.reset_cp_audit_log_for_tests()
    reset_event_bus_for_tests()
    reset_effective_policy_for_tests()

    store = SqliteControlPlaneStore(":memory:")
    key = signing.generate_ed25519_keypair()
    pubkey = signing.public_key_b64(key)

    def _admin():
        from chuzom.enterprise.rbac import Permission
        return types.SimpleNamespace(
            permissions=frozenset({Permission.MANAGE_POLICY}),
            user=types.SimpleNamespace(email="admin@t"), user_id="admin", org_id="o",
        )

    app = create_control_plane_app()
    app.dependency_overrides[get_cp_store] = lambda: store
    app.dependency_overrides[get_signing_key] = lambda: key
    app.dependency_overrides[authenticate_identity] = _admin
    tc = TestClient(app)

    sidecars = []
    for n in range(3):
        cfg = TenantPolicySidecarConfig(
            tenant_id=TENANT, cp_url="http://cp", trusted_public_key_b64=pubkey,
            cache_dir=tmp_path / f"inst{n}", instance_id=f"i{n}",
        )
        client = CPClient("http://cp", transport=_forwarding_transport(tc))
        sidecars.append(TenantPolicySidecar(cfg, client=client))

    yield types.SimpleNamespace(tc=tc, store=store, sidecars=sidecars)

    for s in sidecars:
        s.close()
    app.dependency_overrides.clear()
    cpa.reset_cp_audit_log_for_tests()
    reset_effective_policy_for_tests()


def _push(tc, yaml_text) -> dict:
    r = tc.post(f"/cp/v1/tenants/{TENANT}/policy", json={"yaml_text": yaml_text})
    assert r.status_code == 200, r.text
    return r.json()


def test_g004_end_to_end_green_cell(harness) -> None:
    tc, store, sidecars = harness.tc, harness.store, harness.sidecars

    # ── Baseline: push a permissive policy; every sidecar pulls it and the model is ALLOWED.
    _push(tc, ALLOW_YAML)
    for s in sidecars:
        pol = s.pull_once()
        kept, _ = apply_policy(CANDIDATES, "code", pol)
        assert BLOCKED_MODEL in kept  # allowed before the change

    # ── Push the change: block the model. Then drive convergence (sidecars react).
    t0 = time.monotonic()
    pushed = _push(tc, BLOCK_YAML)  # publishes a policy_change event
    new_version, new_digest = pushed["version"], pushed["digest"]

    for s in sidecars:
        pol = s.pull_once()  # fetch + verify the new signed bundle
        # (a) enforcement changed: the blocked model is now dropped.
        kept, blocked = apply_policy(CANDIDATES, "code", pol)
        assert BLOCKED_MODEL not in kept
        assert BLOCKED_MODEL in blocked
        # report the new effective version back to the control plane.
        s.send_heartbeat(effective_version=new_version, effective_digest=new_digest,
                         source="control_plane")
    elapsed = time.monotonic() - t0

    # ── (a) SLO: all instances reached the new version well within 5s.
    assert elapsed < 5.0

    # ── (b) auditable: reconciliation shows every instance converged to the new version.
    recon = reconcile_tenant_effective_policy(store, TENANT)
    assert recon["active_version"] == new_version
    assert recon["all_converged"] is True
    assert recon["instance_count"] == 3
    assert recon["audit_chain_status"] == "ok"

    # ── router enforcement seam: an installed verified policy drops the model.
    installed = sidecars[0].pull_once()
    install_effective_org_policy(installed, source="control_plane", version=new_version, digest=new_digest)
    kept, blocked = apply_policy(CANDIDATES, "code", get_effective_org_policy())
    assert BLOCKED_MODEL not in kept

    # ── the control-plane's own audit chain is intact end-to-end.
    cpa.verify_cp_audit_chain()  # must not raise
