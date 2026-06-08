"""Tier-1 audit-on-every-turn: one row per routed turn + chain integrity.

These tests pin three behaviours of :func:`chuzom.audit_routing.audit_routing_turn`:

1. **One row per turn.** Every successful routed turn (cached or cold)
   appends exactly one ``routing.decision`` audit row attributed to the
   resolved identity.
2. **Chain integrity.** After 1000 simulated decisions, ``verify_chain()``
   passes. This is the headline acceptance criterion for the audit
   work-plan: tamper detection only works if the chain is unbroken.
3. **Fail-open.** A misconfigured audit DB (path unwritable, etc.) must
   not break the routed turn — the user is owed an answer.

The tests do not exercise the full ``route_and_call`` (which would
require live providers). Instead they directly drive
``audit_routing_turn`` with synthesised inputs; ``test_router.py`` covers
the wiring side. This separation keeps the audit semantics fast and
deterministic.

See: Tier-1 of the three-tier Phase 2 plan.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom.audit_routing import (
    audit_routing_turn,
    reset_audit_log_for_tests,
)
from chuzom.enterprise.audit import AuditLog
from chuzom.identity import TurnIdentity


@pytest.fixture
def isolated_audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Direct the audit log at a fresh per-test SQLite file."""
    db = tmp_path / "audit.db"
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(db))
    monkeypatch.delenv("CHUZOM_AUDIT_DISABLED", raising=False)
    # Force the module-level singleton to re-init against the test path.
    reset_audit_log_for_tests()
    yield db
    reset_audit_log_for_tests()


@pytest.fixture
def fixed_identity() -> TurnIdentity:
    return TurnIdentity(
        user_id="alice",
        user_email="alice@corp.io",
        org_id="acme",
    )


# ── 1. One row per turn ──────────────────────────────────────────────────────


def test_one_row_per_routed_turn(
    isolated_audit_db: Path, fixed_identity: TurnIdentity
) -> None:
    """Acceptance: N routed turns → exactly N audit rows."""
    for i in range(5):
        audit_routing_turn(
            identity=fixed_identity,
            task_type="query",
            complexity="simple",
            model="gemini/gemini-2.5-flash",
            provider="gemini",
            cost_usd=0.0001 * i,
        )

    rows = AuditLog(db_path=isolated_audit_db).recent(limit=100)
    assert len(rows) == 5


def test_row_attributes_match_identity(
    isolated_audit_db: Path, fixed_identity: TurnIdentity
) -> None:
    audit_routing_turn(
        identity=fixed_identity,
        task_type="code",
        complexity="moderate",
        model="claude-sonnet-4-6",
        provider="anthropic",
        cost_usd=0.015,
    )
    row = AuditLog(db_path=isolated_audit_db).recent(limit=1)[0]
    assert row["actor_id"] == "alice"
    assert row["actor_email"] == "alice@corp.io"
    assert row["org_id"] == "acme"
    assert row["type"] == "routing.decision"
    assert row["action"] == "routed"  # cold-fetched, not cached


def test_cached_path_writes_action_cached(
    isolated_audit_db: Path, fixed_identity: TurnIdentity
) -> None:
    """Cached hits are still audited — the routing decision still happened."""
    audit_routing_turn(
        identity=fixed_identity,
        task_type="query",
        complexity="simple",
        model="ollama/qwen3.5",
        provider="ollama",
        cost_usd=0.0,
        cached=True,
    )
    row = AuditLog(db_path=isolated_audit_db).recent(limit=1)[0]
    assert row["action"] == "cached"


def test_identity_falls_back_to_env_when_none(
    isolated_audit_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passing identity=None resolves from env via current_identity()."""
    monkeypatch.setenv("CHUZOM_USER_ID", "env-resolved-user")
    monkeypatch.setenv("CHUZOM_USER_EMAIL", "env@corp.io")
    monkeypatch.setenv("CHUZOM_ORG_ID", "env-org")

    audit_routing_turn(
        identity=None,
        task_type="query",
        complexity="simple",
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        cost_usd=0.0001,
    )
    row = AuditLog(db_path=isolated_audit_db).recent(limit=1)[0]
    assert row["actor_id"] == "env-resolved-user"
    assert row["org_id"] == "env-org"


# ── 2. Chain integrity over 1000 decisions ───────────────────────────────────


def test_chain_integrity_after_1000_decisions(
    isolated_audit_db: Path, fixed_identity: TurnIdentity
) -> None:
    """Acceptance: 1000 routed turns → verify_chain() returns True.

    This is the headline audit-trail invariant. If hash-chain
    construction is wrong (e.g. prev_hash not threaded through, sort
    order non-deterministic), the chain breaks long before 1000.
    """
    for i in range(1000):
        audit_routing_turn(
            identity=fixed_identity,
            task_type="query" if i % 2 else "code",
            complexity="simple" if i % 3 else "moderate",
            model="gemini/gemini-2.5-flash",
            provider="gemini",
            cost_usd=0.0001 * (i % 10),
            cached=bool(i % 5 == 0),
        )

    log = AuditLog(db_path=isolated_audit_db)
    assert log.verify_chain() is True


# ── 3. Fail-open ─────────────────────────────────────────────────────────────


def test_disabled_env_skips_write(
    isolated_audit_db: Path,
    fixed_identity: TurnIdentity,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CHUZOM_AUDIT_DISABLED=1 short-circuits before any write."""
    monkeypatch.setenv("CHUZOM_AUDIT_DISABLED", "1")
    reset_audit_log_for_tests()

    audit_routing_turn(
        identity=fixed_identity,
        task_type="query",
        complexity="simple",
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        cost_usd=0.0001,
    )

    # The DB exists (created by the fixture's AuditLog call inside the
    # `recent` line below), but the audit_routing_turn must have written
    # zero rows.
    rows = AuditLog(db_path=isolated_audit_db).recent(limit=100)
    assert rows == []


def test_audit_failure_does_not_propagate(
    isolated_audit_db: Path,
    fixed_identity: TurnIdentity,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken audit pipeline must not break the routing turn.

    Simulates the failure by patching ``AuditLog.append`` to raise.
    The call must return cleanly (no exception escapes); a warning is
    expected in the log but is not asserted on (left to the logging
    framework to format).
    """
    from chuzom import audit_routing

    def _boom(_self, _ev):
        raise RuntimeError("simulated disk full")

    monkeypatch.setattr(
        "chuzom.enterprise.audit.AuditLog.append", _boom
    )
    # First call materialises the singleton, then the patched append blows.
    audit_routing.audit_routing_turn(
        identity=fixed_identity,
        task_type="query",
        complexity="simple",
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        cost_usd=0.0001,
    )  # MUST NOT RAISE
