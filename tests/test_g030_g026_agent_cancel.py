"""G-026 + G-030 — central agent emergency stop with cascade.

The audit's G-030 row asked for "the workflow can be stopped
immediately." G-026 asked for "explicit cancellation token". This
session pairs them: a single ``SessionStore.cancel(session_id,
reason, cascade=True)`` primitive that walks the descendant tree
and marks every non-terminal child as ``CANCELLED`` in the same
transaction, surfaced via ``POST /v1/admin/agents/{id}:cancel``.

Why cancel != error: the audit + ledger schema previously had no
way to distinguish "operator killed it" from "the framework
crashed". Adding a dedicated ``CANCELLED`` lifecycle state means an
operator can grep the audit for "what did we kill last week" and
get a clean answer.

Tests cover the primitive, the cascade contract, the idempotency
guarantees, and the admin-API integration including admin-action
emission.
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
from chuzom.agents.base import SessionState
from chuzom.agents.session import SessionStore
from chuzom.enterprise.audit import AuditLog
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role


# ── 1. SessionStore.cancel primitive ────────────────────────────────────────


@pytest.fixture
def sessions(tmp_path: Path) -> SessionStore:
    return SessionStore(
        db_path=tmp_path / "sessions.db", check_same_thread=False
    )


def test_cancel_moves_active_to_cancelled(sessions: SessionStore) -> None:
    s = sessions.create(agent_id="a", budget_usd=1.0)
    result = sessions.cancel(s.session_id, reason="operator request")
    assert result.state == SessionState.CANCELLED


def test_cancel_is_idempotent_on_terminal_session(
    sessions: SessionStore,
) -> None:
    s = sessions.create(agent_id="a", budget_usd=1.0)
    sessions.complete(s.session_id)
    # Cancel a COMPLETED session — must NOT rewrite to CANCELLED.
    result = sessions.cancel(s.session_id)
    assert result.state == SessionState.COMPLETED


def test_cancel_cascade_marks_children(sessions: SessionStore) -> None:
    parent = sessions.create(agent_id="p", budget_usd=1.0)
    a = sessions.create(
        agent_id="a", budget_usd=0.5,
        parent_session_id=parent.session_id,
    )
    b = sessions.create(
        agent_id="b", budget_usd=0.5,
        parent_session_id=parent.session_id,
    )
    grandchild = sessions.create(
        agent_id="g", budget_usd=0.1,
        parent_session_id=a.session_id,
    )
    sessions.cancel(parent.session_id, reason="kill workflow")
    for sid in (parent.session_id, a.session_id, b.session_id,
                grandchild.session_id):
        assert sessions.get(sid).state == SessionState.CANCELLED


def test_cancel_cascade_skips_already_terminal_children(
    sessions: SessionStore,
) -> None:
    """Already-completed branches must NOT be rewritten under
    CANCELLED — preserves the real outcome history."""
    parent = sessions.create(agent_id="p", budget_usd=1.0)
    done_child = sessions.create(
        agent_id="done", budget_usd=0.1,
        parent_session_id=parent.session_id,
    )
    sessions.complete(done_child.session_id)
    active_child = sessions.create(
        agent_id="alive", budget_usd=0.1,
        parent_session_id=parent.session_id,
    )
    sessions.cancel(parent.session_id)
    assert sessions.get(done_child.session_id).state == SessionState.COMPLETED
    assert (
        sessions.get(active_child.session_id).state
        == SessionState.CANCELLED
    )


def test_cancel_cascade_false_leaves_descendants(
    sessions: SessionStore,
) -> None:
    parent = sessions.create(agent_id="p", budget_usd=1.0)
    child = sessions.create(
        agent_id="c", budget_usd=0.1,
        parent_session_id=parent.session_id,
    )
    sessions.cancel(parent.session_id, cascade=False)
    assert sessions.get(parent.session_id).state == SessionState.CANCELLED
    assert sessions.get(child.session_id).state == SessionState.ACTIVE


def test_cancelled_session_is_terminal(sessions: SessionStore) -> None:
    """The new CANCELLED state must report ``is_terminal=True`` so all
    the existing terminal-state guards downstream (record_step,
    record_tool_call, complete) refuse to mutate it."""
    s = sessions.create(agent_id="a", budget_usd=1.0)
    sessions.cancel(s.session_id)
    assert sessions.get(s.session_id).state.is_terminal is True


def test_record_step_on_cancelled_session_raises(
    sessions: SessionStore,
) -> None:
    from chuzom.agents.session import TerminalStateViolation

    s = sessions.create(agent_id="a", budget_usd=1.0)
    sessions.cancel(s.session_id)
    with pytest.raises(TerminalStateViolation):
        sessions.record_step(s.session_id, 0.001)


def test_cancel_appears_in_recent_with_state_filter(
    sessions: SessionStore,
) -> None:
    s = sessions.create(agent_id="killed", budget_usd=1.0)
    sessions.cancel(s.session_id)
    rows = sessions.recent(state="cancelled")
    assert [r.session_id for r in rows] == [s.session_id]


def test_cancel_handles_long_chains_without_crash(
    sessions: SessionStore,
) -> None:
    """The cascade walker is cycle-safe up to 1024 hops. A 50-deep
    chain must complete normally."""
    parent = sessions.create(agent_id="root", budget_usd=10.0)
    current_id = parent.session_id
    for _ in range(50):
        child = sessions.create(
            agent_id="c", budget_usd=0.01,
            parent_session_id=current_id,
        )
        current_id = child.session_id
    sessions.cancel(parent.session_id)
    # Walk back and confirm everything's cancelled.
    chain = sessions.recent(limit=100, state="cancelled")
    assert len(chain) == 51  # root + 50 descendants


# ── 2. Admin-API integration ───────────────────────────────────────────────


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
        email="admin@x", display_name="A", role=Role.ADMIN,
    )
    return store.issue_token(user.id, name="admin").plaintext


@pytest.fixture
def viewer_token(store: IdentityStore) -> str:
    org = store.create_org(name="acme2")
    team = store.create_team(org.id, "eng")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="emp@x", display_name="E", role=Role.EMPLOYEE,
    )
    return store.issue_token(user.id, name="emp").plaintext


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_cancel_a_session(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore,
) -> None:
    s = sessions.create(agent_id="alive", budget_usd=1.0)
    resp = app_with_admin.post(
        f"/v1/admin/agents/{s.session_id}:cancel",
        headers=_auth(admin_token),
        json={"reason": "runaway loop suspected"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled"] is True
    assert body["state"] == "cancelled"
    assert body["descendants_cancelled"] == 0
    # Underlying state matches.
    assert sessions.get(s.session_id).state == SessionState.CANCELLED


def test_cancel_response_reports_descendant_count(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore,
) -> None:
    parent = sessions.create(agent_id="p", budget_usd=1.0)
    for i in range(3):
        sessions.create(
            agent_id=f"c{i}", budget_usd=0.1,
            parent_session_id=parent.session_id,
        )
    resp = app_with_admin.post(
        f"/v1/admin/agents/{parent.session_id}:cancel",
        headers=_auth(admin_token),
        json={"reason": "incident"},
    )
    assert resp.json()["descendants_cancelled"] == 3


def test_cancel_unknown_session_returns_404(
    app_with_admin: TestClient, admin_token: str,
) -> None:
    resp = app_with_admin.post(
        "/v1/admin/agents/does-not-exist:cancel",
        headers=_auth(admin_token),
        json={"reason": "x"},
    )
    assert resp.status_code == 404


def test_cancel_already_terminal_returns_noop_response(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore,
) -> None:
    s = sessions.create(agent_id="a", budget_usd=1.0)
    sessions.complete(s.session_id)
    resp = app_with_admin.post(
        f"/v1/admin/agents/{s.session_id}:cancel",
        headers=_auth(admin_token),
        json={"reason": "x"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled"] is False
    assert body["state"] == "completed"
    # State unchanged in the DB.
    assert sessions.get(s.session_id).state == SessionState.COMPLETED


def test_viewer_cannot_cancel_session(
    app_with_admin: TestClient, viewer_token: str, sessions: SessionStore,
) -> None:
    s = sessions.create(agent_id="a", budget_usd=1.0)
    resp = app_with_admin.post(
        f"/v1/admin/agents/{s.session_id}:cancel",
        headers=_auth(viewer_token),
        json={"reason": "x"},
    )
    assert resp.status_code == 403


def test_cancel_emits_admin_action(
    app_with_admin: TestClient,
    admin_token: str,
    sessions: SessionStore,
    admin_log: AdminActionLog,
) -> None:
    s = sessions.create(agent_id="a", budget_usd=1.0)
    pre = admin_log.count()
    app_with_admin.post(
        f"/v1/admin/agents/{s.session_id}:cancel",
        headers=_auth(admin_token),
        json={"reason": "test"},
    )
    assert admin_log.count() == pre + 1
    row = admin_log.recent(limit=1)[0]
    assert row["action"] == "agent:cancel"
    assert row["resource_id"] == s.session_id
    assert row["detail"]["reason"] == "test"


def test_cancel_noop_emits_distinct_admin_action(
    app_with_admin: TestClient,
    admin_token: str,
    sessions: SessionStore,
    admin_log: AdminActionLog,
) -> None:
    """No-op cancels still write an audit row so the forensic trail
    captures attempted-cancel-of-terminal events."""
    s = sessions.create(agent_id="a", budget_usd=1.0)
    sessions.complete(s.session_id)
    app_with_admin.post(
        f"/v1/admin/agents/{s.session_id}:cancel",
        headers=_auth(admin_token),
        json={"reason": "test"},
    )
    actions = {r["action"] for r in admin_log.recent(limit=5)}
    assert "agent:cancel_noop" in actions
