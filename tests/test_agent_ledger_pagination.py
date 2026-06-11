"""Refinement #8 — keyset pagination on the central agent ledger.

``GET /v1/admin/agents/status?cursor=<base64>`` pages through the
ledger newest-first using ``(started_at, session_id)`` as the
keyset. The cursor is opaque to clients (urlsafe base64 of a JSON
``[started_at, session_id]`` tuple) so the on-the-wire format can
change without callers caring.

Backward compat: a request with no ``cursor`` returns the first page
exactly as before. Existing callers that don't paginate get zero
behaviour change.

Tests cover:

* SessionStore primitive (``recent(before=...)``).
* Endpoint cursor round-trip across multiple pages.
* Invalid cursor → 400.
* Cursor past the end → empty list.
* Cursor + state filter compose correctly.
* Cursor tie-break for sessions created in the same millisecond.
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
    encode_ledger_cursor,
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


# ── 1. SessionStore primitive ──────────────────────────────────────────────


@pytest.fixture
def sessions(tmp_path: Path) -> SessionStore:
    return SessionStore(
        db_path=tmp_path / "sessions.db", check_same_thread=False
    )


def test_recent_before_pages_through_newest_first(
    sessions: SessionStore,
) -> None:
    """Create 5 sessions; paginate with limit=2 + before=last-seen,
    expect to walk through all of them in newest-first order."""
    [sessions.create(agent_id=f"a{i}", budget_usd=1.0)
               for i in range(5)]
    # Newest-first id sequence: a4, a3, a2, a1, a0.
    page1 = sessions.recent(limit=2)
    assert [s.agent_id for s in page1] == ["a4", "a3"]
    cursor1 = (page1[-1].started_at, page1[-1].session_id)
    page2 = sessions.recent(limit=2, before=cursor1)
    assert [s.agent_id for s in page2] == ["a2", "a1"]
    cursor2 = (page2[-1].started_at, page2[-1].session_id)
    page3 = sessions.recent(limit=2, before=cursor2)
    assert [s.agent_id for s in page3] == ["a0"]
    cursor3 = (page3[-1].started_at, page3[-1].session_id)
    # Past the end → empty.
    assert sessions.recent(limit=2, before=cursor3) == []


def test_recent_before_composes_with_state_filter(
    sessions: SessionStore,
) -> None:
    """Paginate within state='active' — completed sessions stay
    excluded across pages."""
    sessions.create(agent_id="a", budget_usd=1.0)
    b = sessions.create(agent_id="b", budget_usd=1.0)
    sessions.create(agent_id="c", budget_usd=1.0)
    sessions.complete(b.session_id)
    page1 = sessions.recent(limit=1, state="active")
    assert [s.agent_id for s in page1] == ["c"]
    page2 = sessions.recent(
        limit=10, state="active",
        before=(page1[-1].started_at, page1[-1].session_id),
    )
    assert [s.agent_id for s in page2] == ["a"]


def test_recent_before_tie_breaks_on_session_id(
    sessions: SessionStore,
) -> None:
    """Two sessions created in the same millisecond would otherwise
    risk being skipped or duplicated. The session_id tie-break
    forces a strict total order."""
    a = sessions.create(agent_id="a", budget_usd=1.0)
    b = sessions.create(agent_id="b", budget_usd=1.0)
    # Force identical started_at.
    sessions._conn.execute(
        "UPDATE sessions SET started_at = ? WHERE session_id IN (?, ?)",
        (12345.0, a.session_id, b.session_id),
    )
    sessions._conn.commit()

    page1 = sessions.recent(limit=1)
    assert len(page1) == 1
    cursor = (page1[-1].started_at, page1[-1].session_id)
    page2 = sessions.recent(limit=10, before=cursor)
    # The OTHER session shows up on page 2 — not a duplicate of
    # page 1, not skipped.
    page1_ids = {s.session_id for s in page1}
    page2_ids = {s.session_id for s in page2}
    assert page1_ids.isdisjoint(page2_ids)
    assert page1_ids | page2_ids == {a.session_id, b.session_id}


# ── 2. Cursor encode / decode ──────────────────────────────────────────────


def test_encode_decode_round_trip() -> None:
    from chuzom.admin_api import _decode_ledger_cursor

    started_at, session_id = 1234567.89, "sess-abc-123"
    encoded = encode_ledger_cursor(started_at, session_id)
    # urlsafe base64 with no padding → no '=', '+', '/'.
    assert "=" not in encoded
    assert "+" not in encoded
    assert "/" not in encoded
    decoded_ts, decoded_sid = _decode_ledger_cursor(encoded)
    assert decoded_ts == started_at
    assert decoded_sid == session_id


def test_decode_invalid_base64_raises() -> None:
    """Any malformed cursor raises ``ValueError``. The exact stage
    that catches the malformation (base64 / utf-8 / JSON) is an
    implementation detail — what matters is that the endpoint
    response maps to 400 either way. ``not_base64$$$`` happens to
    survive Python's lenient base64 decode but produces non-utf-8
    bytes; that's still a rejected cursor."""
    from chuzom.admin_api import _decode_ledger_cursor

    with pytest.raises(ValueError):
        _decode_ledger_cursor("not_base64$$$")


def test_decode_truly_unparseable_base64_raises() -> None:
    """A leading ``=`` is one of the few strings Python's base64
    actually refuses to decode."""
    from chuzom.admin_api import _decode_ledger_cursor

    with pytest.raises(ValueError):
        _decode_ledger_cursor("=invalid-prefix")


def test_decode_invalid_json_raises() -> None:
    """Valid base64 but the decoded bytes aren't JSON."""
    import base64

    from chuzom.admin_api import _decode_ledger_cursor

    bad = base64.urlsafe_b64encode(b"not json").rstrip(b"=").decode()
    with pytest.raises(ValueError, match="JSON"):
        _decode_ledger_cursor(bad)


def test_decode_wrong_shape_raises() -> None:
    """JSON but wrong shape (not a 2-tuple)."""
    from chuzom.admin_api import _decode_ledger_cursor

    bad = encode_ledger_cursor(1.0, "x")  # valid shape
    encode_ledger_cursor(1.0, "x")
    # Now an explicitly-bad payload via raw encode.
    import base64
    import json
    bad = base64.urlsafe_b64encode(
        json.dumps({"not": "a list"}).encode()
    ).rstrip(b"=").decode()
    with pytest.raises(ValueError, match="list"):
        _decode_ledger_cursor(bad)


def test_decode_empty_cursor_raises() -> None:
    from chuzom.admin_api import _decode_ledger_cursor

    with pytest.raises(ValueError, match="empty"):
        _decode_ledger_cursor("")


# ── 3. Endpoint integration ────────────────────────────────────────────────


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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_endpoint_no_cursor_returns_first_page_unchanged(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore
) -> None:
    """Backward compat: existing callers that don't paginate see
    EXACTLY the same shape (a flat list) and content as before."""
    for i in range(3):
        sessions.create(agent_id=f"a{i}", budget_usd=1.0)
    resp = app_with_admin.get(
        "/v1/admin/agents/status", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 3


def test_endpoint_cursor_round_trip(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore
) -> None:
    """Walk a 5-row ledger in pages of 2 using cursors. Every row
    is seen exactly once."""
    created = [
        sessions.create(agent_id=f"a{i}", budget_usd=1.0).session_id
        for i in range(5)
    ]

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params = {"limit": "2"}
        if cursor is not None:
            params["cursor"] = cursor
        resp = app_with_admin.get(
            "/v1/admin/agents/status",
            headers=_auth(admin_token),
            params=params,
        )
        assert resp.status_code == 200
        rows = resp.json()
        if not rows:
            break
        seen.extend(r["session_id"] for r in rows)
        last = rows[-1]
        cursor = encode_ledger_cursor(
            last["started_at"], last["session_id"]
        )

    # All 5 sessions visited exactly once.
    assert sorted(seen) == sorted(created)


def test_endpoint_invalid_cursor_returns_400(
    app_with_admin: TestClient, admin_token: str
) -> None:
    resp = app_with_admin.get(
        "/v1/admin/agents/status",
        headers=_auth(admin_token),
        params={"cursor": "not_a_real_cursor"},
    )
    assert resp.status_code == 400
    assert "cursor" in resp.json()["detail"].lower()


def test_endpoint_cursor_past_end_returns_empty(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore
) -> None:
    sessions.create(agent_id="only", budget_usd=1.0)
    # A cursor older than any row → empty list.
    cursor = encode_ledger_cursor(0.0, "zzz")
    resp = app_with_admin.get(
        "/v1/admin/agents/status",
        headers=_auth(admin_token),
        params={"cursor": cursor},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_endpoint_cursor_composes_with_state_filter(
    app_with_admin: TestClient, admin_token: str, sessions: SessionStore
) -> None:
    """Pagination must respect filters — completed sessions stay
    excluded across pages."""
    actives = []
    for i in range(3):
        s = sessions.create(agent_id=f"alive{i}", budget_usd=1.0)
        actives.append(s.session_id)
    done = sessions.create(agent_id="done", budget_usd=1.0)
    sessions.complete(done.session_id)

    resp = app_with_admin.get(
        "/v1/admin/agents/status",
        headers=_auth(admin_token),
        params={"limit": "2", "state": "active"},
    )
    assert resp.status_code == 200
    page1 = resp.json()
    assert len(page1) == 2
    assert all(r["state"] == "active" for r in page1)

    cursor = encode_ledger_cursor(
        page1[-1]["started_at"], page1[-1]["session_id"]
    )
    resp2 = app_with_admin.get(
        "/v1/admin/agents/status",
        headers=_auth(admin_token),
        params={"limit": "2", "state": "active", "cursor": cursor},
    )
    page2 = resp2.json()
    assert len(page2) == 1
    assert page2[0]["state"] == "active"
    assert done.session_id not in {r["session_id"] for r in page2}
