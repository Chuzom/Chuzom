"""G-006 admin API skeleton — auth dep, RBAC dep, representative endpoints.

The admin API is the spine for enterprise control-plane operations
(user management, token revocation, emergency provider/model disable,
policy push). This file covers the skeleton:

* Auth dependency authenticates a bearer token against the
  ``IdentityStore`` and 401s on missing or invalid token.
* Permission dependency factory checks an enum and 403s on missing.
* Three fully-wired endpoints: ``GET /v1/admin/health``,
  ``GET /v1/admin/users``, ``POST /v1/admin/providers/{p}:disable``.
* Provider-disable in-memory ``RuntimeProviderRegistry`` is the
  state holder; the router will consult it in a future slice
  (G-008 follow-up).
* Stubbed endpoints return ``501 Not Implemented`` with a
  structured error body so callers know the surface is the
  contract even when behaviour isn't there yet.

See: ``docs/audit/post-remediation/GAP_ANALYSIS.md`` G-006.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_api import (
    RuntimeProviderRegistry,
    create_app,
    get_identity_store,
    get_provider_registry,
)
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    # check_same_thread=False because the FastAPI TestClient dispatches
    # request handlers onto a worker thread; the fixture creates the
    # connection on the test main thread.
    return IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False
    )


@pytest.fixture
def registry() -> RuntimeProviderRegistry:
    return RuntimeProviderRegistry()


@pytest.fixture
def app_with_admin(
    store: IdentityStore, registry: RuntimeProviderRegistry
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    app.dependency_overrides[get_provider_registry] = lambda: registry
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(store: IdentityStore) -> str:
    """Create an admin user + token; return the plaintext token."""
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="admin@acme.test", display_name="Admin User",
        role=Role.ADMIN,
    )
    issued = store.issue_token(user.id, name="admin-laptop")
    return issued.plaintext


@pytest.fixture
def viewer_token(store: IdentityStore) -> str:
    """Create a low-privilege (employee) user + token. No MANAGE_* perms."""
    org = store.create_org(name="acme2")
    team = store.create_team(org.id, "eng")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="viewer@acme.test", display_name="Viewer User",
        role=Role.EMPLOYEE,
    )
    issued = store.issue_token(user.id, name="viewer-laptop")
    return issued.plaintext


# ── 1. Health endpoint (no auth) ─────────────────────────────────────────────


def test_health_endpoint_requires_no_auth(app_with_admin: TestClient) -> None:
    """Health is the load balancer's friend — never gated by auth."""
    resp = app_with_admin.get("/v1/admin/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


# ── 2. Auth dependency — bearer token resolution ─────────────────────────────


def test_protected_endpoint_rejects_missing_token(
    app_with_admin: TestClient,
) -> None:
    resp = app_with_admin.get("/v1/admin/users")
    assert resp.status_code == 401
    assert "missing" in resp.json()["detail"].lower() or "not authenticated" in resp.json()["detail"].lower()


def test_protected_endpoint_rejects_invalid_token(
    app_with_admin: TestClient,
) -> None:
    resp = app_with_admin.get(
        "/v1/admin/users",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


# ── 3. Permission dependency — RBAC enforcement ──────────────────────────────


def test_viewer_cannot_list_users(
    app_with_admin: TestClient, viewer_token: str
) -> None:
    """VIEWER lacks MANAGE_USERS → 403."""
    resp = app_with_admin.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403
    assert "manage_users" in resp.json()["detail"].lower()


def test_admin_can_list_users(
    app_with_admin: TestClient, admin_token: str, store: IdentityStore
) -> None:
    """ADMIN has MANAGE_USERS → 200, body is JSON list with the admin."""
    resp = app_with_admin.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert any(u["email"] == "admin@acme.test" for u in body)
    # No sensitive fields leaked.
    for u in body:
        assert "token_hash" not in u
        assert "presented_token" not in u


# ── 4. Token revocation ──────────────────────────────────────────────────────


def test_admin_can_revoke_a_token(
    app_with_admin: TestClient, admin_token: str, store: IdentityStore
) -> None:
    """Issue a token for a second user; admin revokes it; auth now fails."""
    org = store.create_org(name="acme-target")
    team = store.create_team(org.id, "ops")
    target = store.create_user(
        org_id=org.id, team_id=team.id,
        email="target@acme.test", display_name="Target",
        role=Role.EMPLOYEE,
    )
    target_token = store.issue_token(target.id, name="target-cli")

    resp = app_with_admin.post(
        f"/v1/admin/users/{target.id}/tokens/{target_token.id}:revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True

    # Subsequent authenticated call with the revoked token now fails 401.
    post = app_with_admin.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {target_token.plaintext}"},
    )
    assert post.status_code == 401


def test_viewer_cannot_revoke_a_token(
    app_with_admin: TestClient,
    viewer_token: str,
    admin_token: str,
    store: IdentityStore,
) -> None:
    """Non-admin attempting revocation → 403, target token unaffected."""
    # First grab any user / token the admin can see.
    list_resp = app_with_admin.get(
        "/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    user_id = list_resp.json()[0]["id"]

    resp = app_with_admin.post(
        f"/v1/admin/users/{user_id}/tokens/some-token-id:revoke",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


# ── 5. Emergency provider disable + list + enable ────────────────────────────


def test_admin_can_disable_provider(
    app_with_admin: TestClient, admin_token: str
) -> None:
    """ADMIN has MANAGE_POLICY → can flip a provider to disabled."""
    resp = app_with_admin.post(
        "/v1/admin/providers/openai:disable",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "credential leak — incident-2026-06-09"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "openai"
    assert body["disabled"] is True
    assert body["reason"] == "credential leak — incident-2026-06-09"


def test_listing_disabled_providers_reflects_state(
    app_with_admin: TestClient, admin_token: str
) -> None:
    app_with_admin.post(
        "/v1/admin/providers/openai:disable",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "test"},
    )
    app_with_admin.post(
        "/v1/admin/providers/anthropic:disable",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "test2"},
    )
    resp = app_with_admin.get(
        "/v1/admin/providers/disabled",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    providers = {p["provider"] for p in resp.json()}
    assert providers == {"openai", "anthropic"}


def test_enable_provider_clears_disabled_flag(
    app_with_admin: TestClient, admin_token: str
) -> None:
    app_with_admin.post(
        "/v1/admin/providers/openai:disable",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "test"},
    )
    resp = app_with_admin.post(
        "/v1/admin/providers/openai:enable",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["disabled"] is False
    # And it's no longer in the disabled list.
    listing = app_with_admin.get(
        "/v1/admin/providers/disabled",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert listing.json() == []


def test_viewer_cannot_disable_provider(
    app_with_admin: TestClient, viewer_token: str
) -> None:
    """Viewer lacks MANAGE_POLICY → 403."""
    resp = app_with_admin.post(
        "/v1/admin/providers/openai:disable",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"reason": "test"},
    )
    assert resp.status_code == 403


# ── 6. Slice 4 (G-006-F4): formerly-stub endpoints are now wired ─────────────
# Tests in tests/test_admin_api_endpoints.py.
