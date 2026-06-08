"""T1-M2 (Track-1 identity, Medium): Permission.ROUTE_PROMPT gate.

Closes the first slice of G-001 from
``docs/audit/post-remediation/GAP_ANALYSIS.md`` — the 2026-06 audit's
anchor finding that ``enterprise/rbac.py`` shipped fully-formed but
had zero callers from ``router.route_and_call``.

Three modes via ``CHUZOM_RBAC_MODE``:

* **off** (default) — no enforcement; preserves Tier-1 env-trust.
* **warn**          — log + audit denial signal, but allow.
* **strict**        — raise ``PermissionDenied`` before any reservation,
  dispatch, or provider call. Caller pays nothing for the deny.

These tests pin all three modes and the env-value parsing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from chuzom import router as router_mod
from chuzom.audit_routing import reset_audit_log_for_tests
from chuzom.enterprise.audit import AuditLog
from chuzom.enterprise.rbac import Permission, PermissionDenied
from chuzom.identity import TurnIdentity
from chuzom.rbac_routing import _resolve_mode, check_route_prompt
from chuzom.router import route_and_call
from chuzom.types import TaskType


@pytest.fixture
def isolated_audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "audit.db"
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(db))
    monkeypatch.delenv("CHUZOM_AUDIT_DISABLED", raising=False)
    reset_audit_log_for_tests()
    yield db
    reset_audit_log_for_tests()


@pytest.fixture
def clean_rbac_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CHUZOM_RBAC_MODE", raising=False)


def _detail_of_recent(audit_db: Path) -> dict:
    row = AuditLog(db_path=audit_db).recent(limit=1)[0]
    detail = row["detail"]
    return json.loads(detail) if isinstance(detail, str) else (detail or {})


# ── 1. Env-mode resolution ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("strict", "strict"),
        ("STRICT", "strict"),
        ("hard", "strict"),  # historical alias from enforce-mode vocab
        ("warn", "warn"),
        ("WARN", "warn"),
        ("soft", "warn"),  # historical alias
        ("shadow", "warn"),
        ("off", "off"),
        ("", "off"),
        ("   ", "off"),
        ("garbage", "off"),
    ],
)
def test_resolve_mode_truth_table(
    clean_rbac_env, monkeypatch: pytest.MonkeyPatch, value: str, expected: str
) -> None:
    monkeypatch.setenv("CHUZOM_RBAC_MODE", value)
    assert _resolve_mode() == expected


def test_resolve_mode_unset_defaults_to_off(clean_rbac_env) -> None:
    assert _resolve_mode() == "off"


# ── 2. check_route_prompt — pure-policy helper ───────────────────────────────


def _identity_no_perms() -> TurnIdentity:
    """Tier-1 TurnIdentity has no ``permissions`` attribute, so
    ``has_permission`` returns False in non-off modes."""
    return TurnIdentity(
        user_id="alice",
        user_email="alice@corp.io",
        org_id="acme",
        tenant_id="acme",
    )


class _IdentityWithPerms:
    """Mimics the Tier-3 ``enterprise.identity.Identity`` shape:
    carries a ``permissions`` frozenset. Used to test the
    has-permission path without standing up an IdentityStore."""

    def __init__(self, user_id: str, perms: set[Permission]) -> None:
        self.user_id = user_id
        self.user_email = f"{user_id}@local"
        self.org_id = "acme"
        self.tenant_id = "acme"
        self.agent_id = None
        self.permissions = frozenset(perms)


def test_off_mode_short_circuits(clean_rbac_env) -> None:
    """Off mode skips the permission check entirely. The helper
    returns ``(off, True)`` regardless of identity shape — the router
    is expected to treat ``mode='off'`` as 'no enforcement, no audit'."""
    mode, has_perm = check_route_prompt(_identity_no_perms())
    assert mode == "off"
    assert has_perm is True


def test_strict_mode_no_perms_reports_false(
    clean_rbac_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHUZOM_RBAC_MODE", "strict")
    mode, has_perm = check_route_prompt(_identity_no_perms())
    assert mode == "strict"
    assert has_perm is False


def test_strict_mode_with_perms_reports_true(
    clean_rbac_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHUZOM_RBAC_MODE", "strict")
    ident = _IdentityWithPerms("alice", {Permission.ROUTE_PROMPT})
    mode, has_perm = check_route_prompt(ident)
    assert mode == "strict"
    assert has_perm is True


def test_warn_mode_no_perms_returns_has_perm_false(
    clean_rbac_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The helper returns the raw permission check so the router can
    write an audit-breadcrumb. The MODE — not the helper — decides
    whether to actually deny."""
    monkeypatch.setenv("CHUZOM_RBAC_MODE", "warn")
    mode, has_perm = check_route_prompt(_identity_no_perms())
    assert mode == "warn"
    assert has_perm is False


# ── 3. End-to-end: route_and_call enforces strict mode ───────────────────────


@pytest.mark.asyncio
async def test_strict_mode_raises_permission_denied(
    clean_rbac_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    monkeypatch.setenv("CHUZOM_RBAC_MODE", "strict")

    async def _should_never_run(**kwargs: Any):
        raise AssertionError("dispatch must not be reached when RBAC denies")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _should_never_run)

    with pytest.raises(PermissionDenied):
        await route_and_call(task_type=TaskType.QUERY, prompt="hi")

    # An audit row should record the denial with outcome=rbac_denied.
    detail = _detail_of_recent(isolated_audit_db)
    assert detail.get("outcome") == "rbac_denied"
    assert detail.get("permission") == "route_prompt"
    assert detail.get("rbac_mode") == "strict"


@pytest.mark.asyncio
async def test_strict_mode_allows_when_identity_has_permission(
    clean_rbac_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    """An identity object that carries ``Permission.ROUTE_PROMPT`` must
    pass the gate even in strict mode."""
    monkeypatch.setenv("CHUZOM_RBAC_MODE", "strict")

    from chuzom.types import LLMResponse

    async def _ok_dispatch(**kwargs: Any):
        return LLMResponse(
            content="ok",
            model="m",
            provider="p",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_ms=1.0,
        )

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _ok_dispatch)

    ident = _IdentityWithPerms("alice", {Permission.ROUTE_PROMPT})
    resp = await route_and_call(
        task_type=TaskType.QUERY, prompt="hi", identity=ident
    )
    assert resp.content == "ok"


@pytest.mark.asyncio
async def test_warn_mode_writes_warn_audit_row_and_allows(
    clean_rbac_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    """Warn mode lets the turn proceed AND writes a breadcrumb so
    operators can find which call sites need real identities."""
    monkeypatch.setenv("CHUZOM_RBAC_MODE", "warn")

    from chuzom.types import LLMResponse

    async def _ok_dispatch(**kwargs: Any):
        return LLMResponse(
            content="ok",
            model="m",
            provider="p",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_ms=1.0,
        )

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _ok_dispatch)

    # Turn succeeds (no exception).
    resp = await route_and_call(task_type=TaskType.QUERY, prompt="hi")
    assert resp.content == "ok"

    # Two audit rows: the warn breadcrumb AND the normal routed row.
    # The breadcrumb is written first; recent(1) returns the routed
    # one. We grab two and look for the breadcrumb explicitly.
    rows = AuditLog(db_path=isolated_audit_db).recent(limit=5)
    outcomes = [
        json.loads(r["detail"]).get("outcome") if isinstance(r["detail"], str) else None
        for r in rows
    ]
    assert "rbac_warn_missing_route_prompt" in outcomes


@pytest.mark.asyncio
async def test_off_mode_does_not_emit_rbac_audit(
    clean_rbac_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    """Off mode is a no-op — no warn / deny audit rows written."""
    # Explicit off (also: no env set should behave the same).
    monkeypatch.setenv("CHUZOM_RBAC_MODE", "off")

    from chuzom.types import LLMResponse

    async def _ok_dispatch(**kwargs: Any):
        return LLMResponse(
            content="ok",
            model="m",
            provider="p",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_ms=1.0,
        )

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _ok_dispatch)

    await route_and_call(task_type=TaskType.QUERY, prompt="hi")

    rows = AuditLog(db_path=isolated_audit_db).recent(limit=5)
    outcomes = [
        json.loads(r["detail"]).get("outcome") if isinstance(r["detail"], str) else None
        for r in rows
    ]
    # Off mode: no rbac_* outcomes. Only the regular routed row (no
    # outcome key) survives.
    assert not any(o and "rbac" in o for o in outcomes)
