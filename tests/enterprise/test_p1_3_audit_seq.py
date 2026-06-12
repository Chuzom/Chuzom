"""P1-3 — audit chain ordering is deterministic and truncation-aware.

The chain previously linked/walked by ``timestamp``, so two events in the same
millisecond (or under clock skew) could be ordered differently at append vs
verify time, silently breaking the chain. A monotonic ``seq`` fixes ordering;
contiguity + a checkpoint anchor detect deleted middle rows and tail truncation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom.enterprise.audit import AuditEvent, AuditLog, TamperDetected


def _event(i: int, ts: float = 1000.0) -> AuditEvent:
    return AuditEvent(
        type="routing.decision", actor_id="system", actor_email="s@x",
        org_id="o1", resource=f"r{i}", action="routed",
        detail={"n": i}, timestamp=ts,
    )


@pytest.fixture
def log(tmp_path: Path) -> AuditLog:
    return AuditLog(db_path=tmp_path / "audit.db", check_same_thread=False)


def test_seq_assigned_monotonically(log):
    for i in range(3):
        log.append(_event(i))
    seqs = [r[0] for r in log._conn.execute(
        "SELECT seq FROM audit_events ORDER BY seq ASC"
    ).fetchall()]
    assert seqs == [1, 2, 3]


def test_same_timestamp_events_chain_deterministically(log):
    # Identical timestamps — the old timestamp-order walk was ambiguous here.
    for i in range(4):
        log.append(_event(i, ts=1234.5))
    assert log.verify_chain() is True


def test_intact_chain_verifies(log):
    for i in range(5):
        log.append(_event(i, ts=1000.0 + i))
    assert log.verify_chain() is True


def test_middle_row_deletion_detected(log):
    for i in range(3):
        log.append(_event(i))
    log._conn.execute("DELETE FROM audit_events WHERE seq = 2")
    log._conn.commit()
    with pytest.raises(TamperDetected):
        log.verify_chain()


def test_tail_truncation_detected(log):
    for i in range(3):
        log.append(_event(i))
    # Delete the newest row — 1..2 stays contiguous, so only the checkpoint
    # anchor (which recorded max_seq=3) can catch this.
    log._conn.execute("DELETE FROM audit_events WHERE seq = 3")
    log._conn.commit()
    with pytest.raises(TamperDetected):
        log.verify_chain()


def test_row_mutation_still_detected(log):
    log.append(_event(0))
    log.append(_event(1))
    log._conn.execute(
        "UPDATE audit_events SET detail = ? WHERE seq = 1",
        ('{"n": 999}',),
    )
    log._conn.commit()
    with pytest.raises(TamperDetected):
        log.verify_chain()


def test_migration_backfills_seq_on_legacy_db(tmp_path):
    """A pre-P1-3 DB (rows with NULL seq, no checkpoint) is backfilled on open
    and verifies intact."""
    path = tmp_path / "legacy.db"
    first = AuditLog(db_path=path, check_same_thread=False)
    for i in range(3):
        first.append(_event(i, ts=1000.0 + i))
    # Simulate a legacy DB: blank out seq + drop the checkpoint anchor.
    first._conn.execute("UPDATE audit_events SET seq = NULL")
    first._conn.execute("DELETE FROM audit_checkpoint")
    first._conn.commit()
    first.close()

    # Reopen → _migrate_seq backfills seq in insertion order; chain verifies.
    reopened = AuditLog(db_path=path, check_same_thread=False)
    seqs = [r[0] for r in reopened._conn.execute(
        "SELECT seq FROM audit_events ORDER BY seq ASC"
    ).fetchall()]
    assert seqs == [1, 2, 3]
    assert reopened.verify_chain() is True
