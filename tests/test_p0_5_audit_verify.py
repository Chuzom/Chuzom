"""P0-5 — surface the tamper-evident audit hash-chain verification.

``AuditLog.verify_chain()`` (and the CEF/JSON/CSV exporters) existed but were
unreachable from the CLI or HTTP, so an operator or SIEM could not actually
*check* integrity or pull the log. This wires three surfaces over the existing
primitives:

* ``GET /v1/admin/audit/verify`` — JSON {verified, rows_checked, tamper_row?}
* ``chuzom audit verify [--json]`` / ``chuzom audit export`` CLI
* a ``audit_chain_intact`` check in ``chuzom verify-enterprise``
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_api import (
    create_app,
    get_audit_log,
    get_identity_store,
    get_provider_registry,
)
from chuzom.enterprise.audit import AuditEvent, AuditLog
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role
from chuzom.provider_registry import RuntimeProviderRegistry


# ── shared fixtures (mirror tests/test_admin_api_endpoints.py) ──────────────

@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(db_path=tmp_path / "identity.db", check_same_thread=False)


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    return tmp_path / "audit.db"


@pytest.fixture
def audit_log(audit_path: Path) -> AuditLog:
    log = AuditLog(db_path=audit_path, check_same_thread=False)
    for i in range(3):
        log.append(
            AuditEvent(
                type="routing.decision", actor_id="system",
                actor_email="system@acme.test", org_id="org1",
                resource=f"lineage:{i}", action="routed",
                detail={"model": "ollama", "n": i},
            )
        )
    return log


@pytest.fixture
def app_with_admin(store, audit_log) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    app.dependency_overrides[get_audit_log] = lambda: audit_log
    app.dependency_overrides[get_provider_registry] = lambda: RuntimeProviderRegistry()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def org_and_team(store: IdentityStore) -> tuple[str, str]:
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    return org.id, team.id


@pytest.fixture
def admin_token(store: IdentityStore, org_and_team) -> str:
    org_id, team_id = org_and_team
    user = store.create_user(
        org_id=org_id, team_id=team_id, email="admin@acme.test",
        display_name="Admin", role=Role.ADMIN,
    )
    return store.issue_token(user.id, name="admin-laptop").plaintext


@pytest.fixture
def viewer_token(store: IdentityStore, org_and_team) -> str:
    org_id, team_id = org_and_team
    user = store.create_user(
        org_id=org_id, team_id=team_id, email="emp@acme.test",
        display_name="Employee", role=Role.EMPLOYEE,
    )
    return store.issue_token(user.id, name="emp-cli").plaintext


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _tamper(audit_path: Path) -> None:
    """Mutate a row directly in SQLite — the exact attack the chain detects."""
    conn = sqlite3.connect(str(audit_path))
    conn.execute(
        "UPDATE audit_events SET detail = ? "
        "WHERE id = (SELECT id FROM audit_events ORDER BY timestamp ASC LIMIT 1)",
        (json.dumps({"model": "TAMPERED", "n": 0}),),
    )
    conn.commit()
    conn.close()


# ── admin endpoint ──────────────────────────────────────────────────────────

def test_verify_endpoint_reports_intact_chain(app_with_admin, admin_token):
    r = app_with_admin.get("/v1/admin/audit/verify", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is True
    assert body["rows_checked"] == 3
    assert "tamper_row" not in body or body["tamper_row"] is None


def test_verify_endpoint_detects_tampering(app_with_admin, admin_token, audit_path):
    _tamper(audit_path)
    r = app_with_admin.get("/v1/admin/audit/verify", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is False
    assert body["tamper_row"] == 0


def test_verify_endpoint_requires_audit_permission(app_with_admin, viewer_token):
    r = app_with_admin.get("/v1/admin/audit/verify", headers=_auth(viewer_token))
    assert r.status_code == 403, r.text


def test_verify_endpoint_rejects_anonymous(app_with_admin):
    assert app_with_admin.get("/v1/admin/audit/verify").status_code == 401


# ── CLI: chuzom audit verify / export ───────────────────────────────────────

def test_cli_audit_verify_intact(audit_log, audit_path, monkeypatch, capsys):
    from chuzom.commands.audit import main

    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(audit_path))
    assert main(["verify"]) == 0
    assert "verified" in capsys.readouterr().out.lower()


def test_cli_audit_verify_tampered_exit1(audit_log, audit_path, monkeypatch):
    from chuzom.commands.audit import main

    _tamper(audit_path)
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(audit_path))
    assert main(["verify"]) == 1


def test_cli_audit_verify_json(audit_log, audit_path, monkeypatch, capsys):
    from chuzom.commands.audit import main

    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(audit_path))
    rc = main(["verify", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["verified"] is True
    assert payload["rows_checked"] == 3


def test_cli_audit_export_json(audit_log, audit_path, monkeypatch, capsys):
    from chuzom.commands.audit import main

    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(audit_path))
    rc = main(["export", "--format", "json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert len(json.loads(out)) == 3


# ── verify-enterprise check ─────────────────────────────────────────────────

def test_enterprise_check_passes_on_intact(audit_log, audit_path, monkeypatch):
    from chuzom.commands.verify_enterprise import _check_audit_chain_intact

    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(audit_path))
    result = _check_audit_chain_intact()
    assert result.passed is True
    assert result.name == "audit_chain_intact"


def test_enterprise_check_fails_on_tamper(audit_log, audit_path, monkeypatch):
    from chuzom.commands.verify_enterprise import _check_audit_chain_intact

    _tamper(audit_path)
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(audit_path))
    result = _check_audit_chain_intact()
    assert result.passed is False
    assert result.remediation
