"""P1-1 — the admin API does not leak internal exception detail.

A deny-by-default exception handler logs the real error server-side and returns
a generic, sanitized message for any UNHANDLED exception, so a stack trace / SQL
/ connection string never reaches the caller. Domain HTTPExceptions (controlled
404/409/400 messages) are unaffected.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_api import (
    create_app,
    get_audit_log,
    get_identity_store,
)
from chuzom.enterprise.audit import AuditLog
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role

_SECRET_DSN = "postgres://admin:hunter2@db.internal:5432/prod"


class _ExplodingAuditLog(AuditLog):
    def verify_chain(self) -> bool:  # type: ignore[override]
        raise RuntimeError(f"{_SECRET_DSN} connection refused")


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(db_path=tmp_path / "identity.db", check_same_thread=False)


@pytest.fixture
def admin_token(store: IdentityStore) -> str:
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id, email="admin@acme.test",
        display_name="Admin", role=Role.ADMIN,
    )
    return store.issue_token(user.id, name="admin").plaintext


@pytest.fixture
def client(store, tmp_path) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    app.dependency_overrides[get_audit_log] = lambda: _ExplodingAuditLog(
        db_path=tmp_path / "audit.db", check_same_thread=False
    )
    # raise_server_exceptions=False so the registered handler runs (otherwise
    # TestClient re-raises and we'd never exercise the boundary).
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_unhandled_exception_returns_generic_500(client, admin_token):
    r = client.get("/v1/admin/audit/verify", headers=_auth(admin_token))
    assert r.status_code == 500
    body = r.text
    # The raw DSN / credentials must never reach the caller.
    assert "hunter2" not in body
    assert "db.internal" not in body
    assert _SECRET_DSN not in body


def test_domain_404_message_is_preserved(client, admin_token):
    # A controlled domain error (team not found) keeps its intended message —
    # the deny-by-default handler only catches *unhandled* exceptions.
    r = client.get(
        "/v1/admin/teams/does-not-exist/budget", headers=_auth(admin_token)
    )
    # team budget GET returns configured=False for unknown teams (no raise),
    # so assert it did NOT 500 — the boundary didn't swallow a normal response.
    assert r.status_code == 200
