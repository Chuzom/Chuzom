"""Iteration 8 acceptance — tenant policy sidecar pull + verify + fail-static."""
from __future__ import annotations

import json

import httpx
import pytest

from chuzom.control_plane.client import CPClient
from chuzom.control_plane.policy_bundle import (
    bundle_payload_bytes,
    make_payload,
    normalize_org_policy_yaml,
)
from chuzom.control_plane.signing import generate_ed25519_keypair, public_key_b64, sign_payload
from chuzom.policy import OrgPolicy as RuntimeOrgPolicy
from chuzom.tenant_policy_sidecar import (
    NoUsablePolicyError,
    SignatureVerificationError,
    TenantPolicySidecar,
    TenantPolicySidecarConfig,
)

YAML = "block_providers: [openai]\n"


def _signed_response(key, *, tenant="t1", version=1, created_at=1.0, yaml_text=YAML, pubkey=None):
    payload = make_payload(tenant_id=tenant, version=version, issued_at=created_at, yaml_text=yaml_text)
    sig = sign_payload(key, bundle_payload_bytes(payload))
    return {
        "tenant_id": tenant, "version": version, "yaml_text": yaml_text,
        "normalized_json": json.dumps(normalize_org_policy_yaml(yaml_text)),
        "digest": "x", "created_at": created_at, "signature_algorithm": "ed25519",
        "signature_b64": sig, "public_key_b64": pubkey or public_key_b64(key),
    }


def _sidecar(key, handler, tmp_path, *, trusted=None):
    cfg = TenantPolicySidecarConfig(
        tenant_id="t1", cp_url="http://cp",
        trusted_public_key_b64=trusted or public_key_b64(key), cache_dir=tmp_path,
    )
    client = CPClient("http://cp", transport=httpx.MockTransport(handler))
    return TenantPolicySidecar(cfg, client=client)


def test_valid_bundle_accepted_and_cached(tmp_path) -> None:
    key = generate_ed25519_keypair()
    sc = _sidecar(key, lambda req: httpx.Response(200, json=_signed_response(key)), tmp_path)
    pol = sc.pull_once()
    assert isinstance(pol, RuntimeOrgPolicy)
    assert pol.block_providers == ["openai"] and pol.source == "control_plane"
    # Cached as last-known-good.
    assert (tmp_path / "t1" / "policy-lkg.json").exists()


def test_bad_signature_rejected(tmp_path) -> None:
    key = generate_ed25519_keypair()
    resp = _signed_response(key)
    resp["signature_b64"] = sign_payload(key, b"different bytes")  # wrong sig, valid format
    sc = _sidecar(key, lambda req: httpx.Response(200, json=resp), tmp_path)
    with pytest.raises(SignatureVerificationError):
        sc.pull_once()
    assert not (tmp_path / "t1" / "policy-lkg.json").exists()  # never cached


def test_served_public_key_mismatch_rejected(tmp_path) -> None:
    key = generate_ed25519_keypair()
    other = generate_ed25519_keypair()
    # Response signed by `key` but advertises a DIFFERENT public key; pinned=key's.
    resp = _signed_response(key, pubkey=public_key_b64(other))
    sc = _sidecar(key, lambda req: httpx.Response(200, json=resp), tmp_path)
    with pytest.raises(SignatureVerificationError):
        sc.pull_once()


def test_cp_down_with_valid_lkg_succeeds(tmp_path) -> None:
    key = generate_ed25519_keypair()
    # First: a good pull caches LKG.
    up = _sidecar(key, lambda req: httpx.Response(200, json=_signed_response(key)), tmp_path)
    up.pull_once()
    # Then: CP is down — sidecar serves last-known-good.
    def down(req):
        raise httpx.ConnectError("cp unreachable")
    sc = _sidecar(key, down, tmp_path)
    pol = sc.pull_once()
    assert pol.block_providers == ["openai"]


def test_cp_down_no_lkg_raises(tmp_path) -> None:
    key = generate_ed25519_keypair()
    def down(req):
        raise httpx.ConnectError("cp unreachable")
    sc = _sidecar(key, down, tmp_path)
    with pytest.raises(NoUsablePolicyError):
        sc.pull_once()


def test_tampered_lkg_rejected_on_load(tmp_path) -> None:
    key = generate_ed25519_keypair()
    _sidecar(key, lambda req: httpx.Response(200, json=_signed_response(key)), tmp_path).pull_once()
    # Tamper the cached bundle's policy content (signature no longer matches).
    lkg = tmp_path / "t1" / "policy-lkg.json"
    data = json.loads(lkg.read_text())
    data["yaml_text"] = "block_providers: [anthropic]\n"
    lkg.write_text(json.dumps(data))
    def down(req):
        raise httpx.ConnectError("down")
    sc = _sidecar(key, down, tmp_path)
    with pytest.raises(SignatureVerificationError):
        sc.pull_once()


def test_atomic_save_preserves_prior_on_failure(tmp_path, monkeypatch) -> None:
    key = generate_ed25519_keypair()
    sc = _sidecar(key, lambda req: httpx.Response(200, json=_signed_response(key)), tmp_path)
    sc.pull_once()  # writes v1
    lkg = tmp_path / "t1" / "policy-lkg.json"
    original = lkg.read_text()
    # Next pull returns v2 but os.replace fails mid-save. The sidecar treats a
    # cache-write failure as a fail-static condition (falls back to the old
    # LKG) rather than crashing — and the atomic write leaves the prior cache
    # byte-for-byte intact (os.replace never completed).
    sc2 = _sidecar(key, lambda req: httpx.Response(200, json=_signed_response(key, version=2)), tmp_path)
    monkeypatch.setattr("chuzom.tenant_policy_sidecar.os.replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    pol = sc2.pull_once()  # must not crash
    assert isinstance(pol, RuntimeOrgPolicy)
    assert lkg.read_text() == original  # prior cache unchanged (still v1)
