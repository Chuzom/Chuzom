"""G-029 — central agent ledger.

``GET /v1/admin/agents/status`` exposes a newest-first view of agent
sessions for the ops team. Each row carries the derived
``budget_pressure_pct`` (consumed / cap) so an operator can answer
"who's close to budget?" with a single filter.

Filters covered:

* ``state`` — pin to a lifecycle (``active`` / terminal).
* ``near_budget_pct`` — keep only sessions over a pressure floor.
* ``limit`` — bounded [1, 1000].

Authorisation: ``Permission.VIEW_ALL_AUDIT`` (same gate as the
hash-chained audit endpoint).

"Stuck" detection (last-activity timeout) is intentionally not
implemented in this slice — the session schema does not carry a
``last_activity_at`` column. A follow-up adds it.
"""
from __future__ import annotations

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
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False
    )


@pytest.fixture
def audit_log(tmp_path: Path) -> AuditLog:
    return AuditLog(
        db_path=tmp_path / "audit.db", check_same_thread=False
    )


@pytest.fixture
def admin_log(tmp_path: Path) -> AdminActionLog:
    return AdminActionLog(
        db_path=tmp_path / "admin_actions.db", check_same_thread=False
    )


@pytest.fixture
def registry() -> RuntimeProviderRegistry:
    return RuntimeProviderRegistry()


@pytest.fixture
def sessions(tmp_path: Path) -> SessionStore:
    return SessionStore(
        db_path=tmp_path / "sessions.db", check_same_thread=False
    )


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
def org_and_team(store: IdentityStore) -> tuple[str, str]:
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    return org.id, team.id


@pytest.fixture
def admin_token(store: IdentityStore, org_and_team) -> str:
    org_id, team_id = org_and_team
    user = store.create_user(
        org_id=org_id, team_id=team_id,
        email="admin@acme.test", display_name="Admin",
        role=Role.ADMIN,
    )
    return store.issue_token(user.id, name="admin").plaintext


@pytest.fixture
def viewer_token(store: IdentityStore, org_and_team) -> str:
    org_id, team_id = org_and_team
    user = store.create_user(
        org_id=org_id, team_id=team_id,
        email="emp@acme.test", display_name="Emp",
        role=Role.EMPLOYEE,
    )
    return store.issue_token(user.id, name="emp").plaintext


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 1. SessionStore.recent() — the underlying query ─────────────────────────


def test_sessions_recent_newest_first(sessions: SessionStore) -> None:
    sessions.create(agent_id="a1", budget_usd=1.0)
    sessions.create(agent_id="a2", budget_usd=1.0)
    sessions.create(agent_id="a3", budget_usd=1.0)
    recent = sessions.recent(limit=10)
    assert [s.agent_id for s in recent] == ["a3", "a2", "a1"]


def test_sessions_recent_filter_by_state(sessions: SessionStore) -> None:
    a = sessions.create(agent_id="a1", budget_usd=1.0)
    b = sessions.create(agent_id="a2", budget_usd=1.0)
    sessions.complete(a.session_id)
    active = sessions.recent(state="active")
    assert {s.session_id for s in active} == {b.session_id}
    completed = sessions.recent(state="completed")
    assert {s.session_id for s in completed} == {a.session_id}


# ── 2. Endpoint happy path + RBAC ───────────────────────────────────────────


def test_endpoint_lists_sessions(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore
) -> None:
    a = sessions.create(agent_id="planner", budget_usd=1.0, max_iterations=5)
    sessions.record_step(a.session_id, 0.10)
    sessions.create(agent_id="executor", budget_usd=0.5)

    resp = app_with_admin.get(
        "/v1/admin/agents/status", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    # Newest first: executor before planner.
    assert [r["agent_id"] for r in rows] == ["executor", "planner"]
    # The planner shows the recorded step + pressure.
    planner = next(r for r in rows if r["agent_id"] == "planner")
    assert planner["step_count"] == 1
    assert planner["consumed_usd"] == pytest.approx(0.10)
    assert planner["budget_pressure_pct"] == pytest.approx(0.10)
    assert planner["limits"]["max_iterations"] == 5


def test_endpoint_pressure_for_zero_cap_session(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore
) -> None:
    """Defensive: a zero-cap session must not divide-by-zero. (The
    create-path refuses zero caps today; the JSON projection still
    has to handle it for any imported legacy rows.)"""
    # Sneak a row in past validation via raw conn — simulates a legacy
    # import we can't refuse retroactively.
    sessions._conn.execute(
        "INSERT INTO sessions (session_id, agent_id, started_at, "
        "completed_at, parent_session_id, budget_cap_usd, "
        "consumed_usd, step_count, state) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("legacy", "a", 1.0, None, None, 0.0, 0.0, 0, "active"),
    )
    sessions._conn.commit()
    resp = app_with_admin.get(
        "/v1/admin/agents/status", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    rows = resp.json()
    legacy = next(r for r in rows if r["session_id"] == "legacy")
    assert legacy["budget_pressure_pct"] == 0.0


# ── 3. Filters: state, near_budget_pct, limit ────────────────────────────────


def test_endpoint_filters_by_state(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore
) -> None:
    a = sessions.create(agent_id="x", budget_usd=1.0)
    sessions.create(agent_id="y", budget_usd=1.0)
    sessions.complete(a.session_id)
    resp = app_with_admin.get(
        "/v1/admin/agents/status?state=active", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["agent_id"] == "y"


def test_endpoint_filters_by_near_budget_pct(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore
) -> None:
    """Sessions over the pressure threshold are kept; the rest drop."""
    a = sessions.create(agent_id="cool", budget_usd=1.0)
    sessions.record_step(a.session_id, 0.10)  # 10 %
    b = sessions.create(agent_id="hot", budget_usd=1.0)
    sessions.record_step(b.session_id, 0.85)  # 85 %

    resp = app_with_admin.get(
        "/v1/admin/agents/status?near_budget_pct=0.75",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["agent_id"] for r in rows] == ["hot"]


def test_endpoint_limit_bounds(
    app_with_admin: TestClient, admin_token: str
) -> None:
    too_big = app_with_admin.get(
        "/v1/admin/agents/status?limit=99999",
        headers=_auth(admin_token),
    )
    assert too_big.status_code == 400
    too_small = app_with_admin.get(
        "/v1/admin/agents/status?limit=0",
        headers=_auth(admin_token),
    )
    assert too_small.status_code == 400


def test_endpoint_near_budget_pct_validation(
    app_with_admin: TestClient, admin_token: str
) -> None:
    resp = app_with_admin.get(
        "/v1/admin/agents/status?near_budget_pct=1.5",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400


# ── 4. RBAC ─────────────────────────────────────────────────────────────────


def test_endpoint_viewer_forbidden(
    app_with_admin: TestClient, viewer_token: str
) -> None:
    resp = app_with_admin.get(
        "/v1/admin/agents/status", headers=_auth(viewer_token)
    )
    assert resp.status_code == 403


# ── 5. Read-only — endpoint does NOT write admin-action rows ────────────────


def test_endpoint_does_not_emit_admin_action(
    app_with_admin: TestClient,
    admin_token: str,
    admin_log: AdminActionLog,
) -> None:
    pre = admin_log.count()
    app_with_admin.get(
        "/v1/admin/agents/status", headers=_auth(admin_token)
    )
    assert admin_log.count() == pre
