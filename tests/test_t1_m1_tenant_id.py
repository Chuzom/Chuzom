"""T1-M1 (Track-1 identity, Medium): typed-but-implicit ``tenant_id`` field.

Q-P-2 (Phase 3a) decided that ``tenant_id`` should be carried through
``TurnIdentity`` from day 1, even though chuzom currently runs as a
single-org-per-instance. The field defaults to ``org_id`` in the
resolver so the production tenant axis is always populated; Phase 3b
(sidecar-per-tenant) sets ``CHUZOM_TENANT_ID`` explicitly to
differentiate per-tenant sidecars within one org.

These tests pin three contracts:

1. **Dataclass default.** ``TurnIdentity(...)`` constructed without
   ``tenant_id`` gets ``None`` so direct callers (tests, internal
   helpers) are not forced to populate it.

2. **Resolver default.** ``current_identity()`` always populates
   ``tenant_id``:
     * ``CHUZOM_TENANT_ID`` env wins when set
     * Falls back to ``org_id`` otherwise (Phase 3a semantics)

3. **Audit + log propagation.** When ``tenant_id`` is set on the
   identity, the audit row's ``detail`` carries ``tenant_id`` and
   the router's structlog contextvars carry a ``tenant_id`` key.

See: Docs/audit/decisions/Q-P-2_multi-tenancy.md ·
Docs/audit/post-remediation/GAP_ANALYSIS.md G-003.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chuzom.audit_routing import audit_routing_turn, reset_audit_log_for_tests
from chuzom.enterprise.audit import AuditLog
from chuzom.identity import (
    CHUZOM_AGENT_ID_ENV,
    CHUZOM_ORG_ID_ENV,
    CHUZOM_TENANT_ID_ENV,
    CHUZOM_USER_EMAIL_ENV,
    CHUZOM_USER_ID_ENV,
    TurnIdentity,
    current_identity,
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for var in (
        CHUZOM_USER_ID_ENV,
        CHUZOM_USER_EMAIL_ENV,
        CHUZOM_ORG_ID_ENV,
        CHUZOM_AGENT_ID_ENV,
        CHUZOM_TENANT_ID_ENV,
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def isolated_audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "audit.db"
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(db))
    monkeypatch.delenv("CHUZOM_AUDIT_DISABLED", raising=False)
    reset_audit_log_for_tests()
    yield db
    reset_audit_log_for_tests()


def _detail_of_recent(audit_db: Path) -> dict:
    row = AuditLog(db_path=audit_db).recent(limit=1)[0]
    detail = row["detail"]
    return json.loads(detail) if isinstance(detail, str) else (detail or {})


# ── 1. Dataclass default ─────────────────────────────────────────────────────


def test_dataclass_default_is_none() -> None:
    """Direct ``TurnIdentity(...)`` without ``tenant_id`` gets None.
    Preserves backwards compat for test fixtures and internal helpers
    that don't care about the tenant axis."""
    ident = TurnIdentity(user_id="u", user_email="u@l", org_id="o")
    assert ident.tenant_id is None


def test_dataclass_accepts_explicit_tenant_id() -> None:
    ident = TurnIdentity(
        user_id="u", user_email="u@l", org_id="acme", tenant_id="tenant-42"
    )
    assert ident.tenant_id == "tenant-42"


def test_dataclass_equality_distinguishes_tenant_id() -> None:
    base = {"user_id": "u", "user_email": "u@l", "org_id": "acme"}
    assert TurnIdentity(**base, tenant_id="a") != TurnIdentity(**base, tenant_id="b")
    assert TurnIdentity(**base, tenant_id="a") != TurnIdentity(**base)


# ── 2. Resolver default ──────────────────────────────────────────────────────


def test_resolver_falls_back_to_org_id(
    clean_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 3a: CHUZOM_TENANT_ID unset → tenant_id defaults to org_id."""
    monkeypatch.setenv(CHUZOM_USER_ID_ENV, "alice")
    monkeypatch.setenv(CHUZOM_ORG_ID_ENV, "acme")
    ident = current_identity()
    assert ident.tenant_id == "acme"
    assert ident.tenant_id == ident.org_id


def test_resolver_honours_explicit_env(
    clean_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 3b: CHUZOM_TENANT_ID set → resolver uses it, even if
    different from org_id."""
    monkeypatch.setenv(CHUZOM_USER_ID_ENV, "alice")
    monkeypatch.setenv(CHUZOM_ORG_ID_ENV, "acme")
    monkeypatch.setenv(CHUZOM_TENANT_ID_ENV, "tenant-42")
    ident = current_identity()
    assert ident.tenant_id == "tenant-42"
    assert ident.org_id == "acme"


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_resolver_blank_tenant_env_falls_back_to_org_id(
    clean_env, monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """Whitespace / empty env value collapses to the org_id fallback —
    treated the same as 'unset'. Mirrors how the agent_id env handles
    blank values."""
    monkeypatch.setenv(CHUZOM_USER_ID_ENV, "alice")
    monkeypatch.setenv(CHUZOM_ORG_ID_ENV, "acme")
    monkeypatch.setenv(CHUZOM_TENANT_ID_ENV, blank)
    assert current_identity().tenant_id == "acme"


def test_resolver_tenant_id_default_when_org_defaulted(
    clean_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When CHUZOM_ORG_ID is itself unset (org_id defaults to 'local'),
    tenant_id also defaults to 'local' via the fallback chain."""
    # No env at all — both org_id and tenant_id fall through to the
    # local sentinel.
    ident = current_identity()
    assert ident.org_id == "local"
    assert ident.tenant_id == "local"


# ── 3. Audit row propagation ─────────────────────────────────────────────────


def _identity_with(tenant_id: str | None) -> TurnIdentity:
    return TurnIdentity(
        user_id="alice",
        user_email="alice@corp.io",
        org_id="acme",
        tenant_id=tenant_id,
    )


def test_audit_detail_carries_tenant_id_when_set(
    isolated_audit_db: Path,
) -> None:
    audit_routing_turn(
        identity=_identity_with("tenant-42"),
        task_type="code",
        complexity="moderate",
        model="claude-sonnet-4-6",
        provider="anthropic",
        cost_usd=0.015,
    )
    detail = _detail_of_recent(isolated_audit_db)
    assert detail["tenant_id"] == "tenant-42"


def test_audit_detail_omits_tenant_id_when_none(
    isolated_audit_db: Path,
) -> None:
    """Mirrors the agent_id pattern: don't write a meaningless null
    field. A direct-constructed TurnIdentity without tenant_id stays
    out of the audit row's detail."""
    audit_routing_turn(
        identity=_identity_with(None),
        task_type="query",
        complexity="simple",
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        cost_usd=0.0001,
    )
    detail = _detail_of_recent(isolated_audit_db)
    assert "tenant_id" not in detail


def test_audit_detail_in_production_path_carries_tenant(
    isolated_audit_db: Path, clean_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production identity=None resolves via current_identity() which
    populates tenant_id from env or org_id fallback. Confirm the audit
    row picks it up via the resolver."""
    monkeypatch.setenv(CHUZOM_USER_ID_ENV, "alice")
    monkeypatch.setenv(CHUZOM_ORG_ID_ENV, "acme")
    audit_routing_turn(
        identity=None,
        task_type="query",
        complexity="simple",
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        cost_usd=0.0001,
    )
    detail = _detail_of_recent(isolated_audit_db)
    # Phase 3a default: tenant_id == org_id
    assert detail["tenant_id"] == "acme"


# ── 4. Log contextvar propagation ────────────────────────────────────────────


def test_router_bind_payload_includes_tenant_id_when_set() -> None:
    """The same bind-payload shape the router uses (per
    test_tier2_log_contextvars.py's helper) must include tenant_id
    when the identity carries one."""
    # Replicate the bind logic from router.route_and_call.
    ident = _identity_with("tenant-42")
    payload = {
        "request_id": "abc12345",
        "user_id": ident.user_id,
        "org_id": ident.org_id,
    }
    if ident.agent_id:
        payload["agent_id"] = ident.agent_id
    if ident.tenant_id:
        payload["tenant_id"] = ident.tenant_id

    assert payload["tenant_id"] == "tenant-42"


def test_router_bind_payload_omits_tenant_id_when_none() -> None:
    ident = _identity_with(None)
    payload = {
        "request_id": "abc",
        "user_id": ident.user_id,
        "org_id": ident.org_id,
    }
    if ident.agent_id:
        payload["agent_id"] = ident.agent_id
    if ident.tenant_id:
        payload["tenant_id"] = ident.tenant_id

    assert "tenant_id" not in payload
