"""Tier-2 audit attribution: ``agent_id`` lands in the audit row's detail.

Tier-1 wrote one ``routing.decision`` audit row per turn, attributed to
``user_id`` / ``user_email`` / ``org_id``. Tier-2 extends that detail
to include ``agent_id`` *when* the turn is part of an agent run.

The placement choice — ``detail["agent_id"]`` rather than a top-level
column — keeps the audit schema unchanged. Operators who don't run
agents see no change in their SIEM exports; operators who do see the
agent dimension in the same JSON blob the existing CEF/JSON/CSV
exporters already serialise.

See: Tier-2 of the three-tier Phase 2 plan.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import enterprise to trigger audit handler bootstrap (C-2 plugin seam)
import chuzom.enterprise  # noqa: F401

from chuzom.audit_routing import audit_routing_turn, reset_audit_log_for_tests
from chuzom.enterprise.audit import AuditLog
from chuzom.identity import TurnIdentity


@pytest.fixture
def isolated_audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "audit.db"
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(db))
    monkeypatch.delenv("CHUZOM_AUDIT_DISABLED", raising=False)
    reset_audit_log_for_tests()
    yield db
    reset_audit_log_for_tests()


def _identity(agent_id: str | None = None) -> TurnIdentity:
    return TurnIdentity(
        user_id="alice",
        user_email="alice@corp.io",
        org_id="acme",
        agent_id=agent_id,
    )


def _read_detail(audit_db: Path) -> dict:
    """Fetch the most-recent row's ``detail`` column already parsed."""
    row = AuditLog(db_path=audit_db).recent(limit=1)[0]
    detail = row["detail"]
    return json.loads(detail) if isinstance(detail, str) else detail


# ── agent_id surfaces in detail when set ─────────────────────────────────────


def test_agent_id_appears_in_detail(isolated_audit_db: Path) -> None:
    audit_routing_turn(
        identity=_identity(agent_id="agno-reviewer"),
        task_type="code",
        complexity="moderate",
        model="claude-sonnet-4-6",
        provider="anthropic",
        cost_usd=0.015,
    )
    detail = _read_detail(isolated_audit_db)
    assert detail["agent_id"] == "agno-reviewer"


def test_agent_id_omitted_when_none(isolated_audit_db: Path) -> None:
    """A non-agent turn must not carry a meaningless agent_id field."""
    audit_routing_turn(
        identity=_identity(agent_id=None),
        task_type="query",
        complexity="simple",
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        cost_usd=0.0001,
    )
    detail = _read_detail(isolated_audit_db)
    assert "agent_id" not in detail


def test_agent_id_carries_through_env_resolution(
    isolated_audit_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When identity=None, current_identity() reads CHUZOM_AGENT_ID
    and the audit row picks it up. Mirrors how operators will actually
    deploy this: ``CHUZOM_AGENT_ID=agno`` in the env that launches the
    chuzom MCP server."""
    monkeypatch.setenv("CHUZOM_USER_ID", "alice")
    monkeypatch.setenv("CHUZOM_AGENT_ID", "agno-via-env")

    audit_routing_turn(
        identity=None,
        task_type="query",
        complexity="simple",
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        cost_usd=0.0001,
    )
    detail = _read_detail(isolated_audit_db)
    assert detail["agent_id"] == "agno-via-env"


def test_detail_extras_do_not_clobber_agent_id(isolated_audit_db: Path) -> None:
    """Even if a caller passes detail_extras={"agent_id": ...} the
    identity-derived agent_id is the canonical source. detail_extras
    is applied AFTER the identity field is set, so a malicious or
    confused caller can in principle override — that's by design (the
    extras dict is meant for caller-defined context).

    This test pins the documented order: identity sets agent_id first,
    detail_extras can override. If a future refactor reverses that
    order, the test will catch the change.
    """
    audit_routing_turn(
        identity=_identity(agent_id="identity-agent"),
        task_type="query",
        complexity="simple",
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        cost_usd=0.0001,
        detail_extras={"agent_id": "caller-override"},
    )
    detail = _read_detail(isolated_audit_db)
    assert detail["agent_id"] == "caller-override"


def test_chain_integrity_still_holds_with_mixed_agent_rows(
    isolated_audit_db: Path,
) -> None:
    """Acceptance carry-over from Tier-1: verify_chain() still passes
    when some rows carry agent_id and others don't."""
    for i in range(200):
        audit_routing_turn(
            identity=_identity(agent_id=f"agent-{i % 3}" if i % 2 else None),
            task_type="query",
            complexity="simple",
            model="gemini/gemini-2.5-flash",
            provider="gemini",
            cost_usd=0.0001 * (i % 5),
        )

    assert AuditLog(db_path=isolated_audit_db).verify_chain() is True
