"""G-029 finisher — ``last_activity_at`` column + "stuck" detection.

Adds a monotonic per-session timestamp that updates on every state
mutation. Powers the new ``stuck_since_seconds`` filter on
``GET /v1/admin/agents/status`` — an operator can ask "show me
ACTIVE sessions that haven't ticked in the last 5 minutes" with a
single query param.

Defaults are designed to be non-flaky:

* New sessions seed ``last_activity_at = started_at`` so a
  just-created session is not immediately stuck.
* Legacy rows from before this column existed surface
  ``last_activity_at = None``; the endpoint falls back to
  ``started_at`` for the idleness derivation.
* Terminal sessions are excluded from ``stuck_since_seconds``
  filtering regardless of idle time — "stuck" only makes sense
  for alive workflows.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_actions import AdminActionLog
from chuzom.admin_api import (
    RuntimeProviderRegistry,
    create_app,
    get_admin_action_log,
    get_audit_log,
    get_identity_store,
    get_provider_registry,
    get_session_store,
)
from chuzom.agents.session import SessionStore
from chuzom.enterprise.audit import AuditLog
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role


@pytest.fixture
def sessions(tmp_path: Path) -> SessionStore:
    return SessionStore(
        db_path=tmp_path / "sessions.db", check_same_thread=False
    )


# ── 1. SessionStore writes / migrates last_activity_at ─────────────────────


def test_create_seeds_last_activity_to_started_at(
    sessions: SessionStore,
) -> None:
    s = sessions.create(agent_id="a", budget_usd=1.0)
    read = sessions.get(s.session_id)
    assert read.last_activity_at == read.started_at


def test_record_step_bumps_last_activity(sessions: SessionStore) -> None:
    s = sessions.create(agent_id="a", budget_usd=1.0)
    original = s.started_at
    time.sleep(0.005)
    sessions.record_step(s.session_id, 0.1)
    new = sessions.get(s.session_id).last_activity_at
    assert new is not None
    assert new > original


def test_record_tool_call_bumps_last_activity(
    sessions: SessionStore,
) -> None:
    s = sessions.create(agent_id="a", budget_usd=1.0)
    original = s.started_at
    time.sleep(0.005)
    sessions.record_tool_call(s.session_id, "fs_read")
    new = sessions.get(s.session_id).last_activity_at
    assert new is not None
    assert new > original


def test_pre_finisher_schema_gets_migrated(tmp_path: Path) -> None:
    """A SessionStore opened against a DB that lacks last_activity_at
    must ALTER TABLE it in. Legacy rows surface with NULL."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            started_at REAL NOT NULL,
            completed_at REAL,
            parent_session_id TEXT,
            budget_cap_usd REAL NOT NULL,
            consumed_usd REAL NOT NULL DEFAULT 0.0,
            step_count INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL,
            framework TEXT,
            max_iterations INTEGER,
            max_recursion_depth INTEGER,
            routing_policy_json TEXT,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            max_tool_calls INTEGER,
            max_children_concurrent INTEGER
        )"""
    )
    conn.execute(
        "INSERT INTO sessions "
        "(session_id, agent_id, started_at, completed_at, "
        "parent_session_id, budget_cap_usd, consumed_usd, step_count, "
        "state, framework, max_iterations, max_recursion_depth, "
        "routing_policy_json, tool_call_count, max_tool_calls, "
        "max_children_concurrent) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("legacy-1", "a", 1.0, None, None, 5.0, 0.0, 0, "active",
         None, None, None, None, 0, None, None),
    )
    conn.commit()
    conn.close()

    store = SessionStore(db_path=db_path, check_same_thread=False)
    cols = {
        row[1]
        for row in store._conn.execute(
            "PRAGMA table_info(sessions)"
        ).fetchall()
    }
    assert "last_activity_at" in cols
    legacy = store.get("legacy-1")
    assert legacy.last_activity_at is None


# ── 2. Admin-API "stuck" filter ─────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False
    )


@pytest.fixture
def audit_log(tmp_path: Path) -> AuditLog:
    return AuditLog(db_path=tmp_path / "audit.db", check_same_thread=False)


@pytest.fixture
def admin_log(tmp_path: Path) -> AdminActionLog:
    return AdminActionLog(
        db_path=tmp_path / "admin_actions.db", check_same_thread=False
    )


@pytest.fixture
def registry() -> RuntimeProviderRegistry:
    return RuntimeProviderRegistry()


@pytest.fixture
def app_with_admin(
    store: IdentityStore,
    audit_log: AuditLog,
    admin_log: AdminActionLog,
    registry: RuntimeProviderRegistry,
    sessions: SessionStore,
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    app.dependency_overrides[get_audit_log] = lambda: audit_log
    app.dependency_overrides[get_admin_action_log] = lambda: admin_log
    app.dependency_overrides[get_provider_registry] = lambda: registry
    app.dependency_overrides[get_session_store] = lambda: sessions
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(store: IdentityStore) -> str:
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="admin@x", display_name="A",
        role=Role.ADMIN,
    )
    return store.issue_token(user.id, name="admin").plaintext


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_endpoint_surfaces_last_activity_and_idle_seconds(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore
) -> None:
    sessions.create(agent_id="a", budget_usd=1.0)
    resp = app_with_admin.get(
        "/v1/admin/agents/status", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["last_activity_at"] is not None
    assert row["idle_seconds"] is not None
    assert row["idle_seconds"] >= 0


def test_stuck_filter_keeps_only_idle_active(
    app_with_admin: TestClient,
    admin_token: str,
    sessions: SessionStore,
    monkeypatch,
) -> None:
    """Two sessions: one busy (activity now), one idle for 1h.
    The 30-min stuck filter keeps the idle one only."""
    sessions.create(agent_id="busy", budget_usd=1.0)
    idle = sessions.create(agent_id="idle", budget_usd=1.0)
    # Manually rewind idle's last_activity_at by 1 hour.
    sessions._conn.execute(
        "UPDATE sessions SET last_activity_at = ? WHERE session_id = ?",
        (time.time() - 3600, idle.session_id),
    )
    sessions._conn.commit()

    resp = app_with_admin.get(
        "/v1/admin/agents/status?stuck_since_seconds=1800",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["agent_id"] for r in rows] == ["idle"]
    assert rows[0]["idle_seconds"] >= 1800


def test_stuck_filter_excludes_terminal_sessions(
    app_with_admin: TestClient,
    admin_token: str,
    sessions: SessionStore,
) -> None:
    """A completed-then-idle session must NOT match — 'stuck' is
    only meaningful for alive workflows."""
    s = sessions.create(agent_id="done", budget_usd=1.0)
    sessions.complete(s.session_id)
    # Rewind to ensure idle time exceeds the filter.
    sessions._conn.execute(
        "UPDATE sessions SET last_activity_at = ? WHERE session_id = ?",
        (time.time() - 3600, s.session_id),
    )
    sessions._conn.commit()

    resp = app_with_admin.get(
        "/v1/admin/agents/status?stuck_since_seconds=60",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert rows == []


def test_stuck_filter_validation(
    app_with_admin: TestClient, admin_token: str
) -> None:
    resp = app_with_admin.get(
        "/v1/admin/agents/status?stuck_since_seconds=-1",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400


def test_stuck_filter_combines_with_state(
    app_with_admin: TestClient,
    admin_token: str,
    sessions: SessionStore,
) -> None:
    """state=active narrows first; stuck_since_seconds filters within
    the narrowed set."""
    idle = sessions.create(agent_id="zombie", budget_usd=1.0)
    sessions._conn.execute(
        "UPDATE sessions SET last_activity_at = ? WHERE session_id = ?",
        (time.time() - 3600, idle.session_id),
    )
    sessions._conn.commit()
    sessions.create(agent_id="fresh", budget_usd=1.0)

    resp = app_with_admin.get(
        "/v1/admin/agents/status?state=active&stuck_since_seconds=60",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["agent_id"] for r in rows] == ["zombie"]
