"""Regression: AuditLog must migrate a DB created before the ``seq`` column
existed, instead of failing every write with 'no such column: seq'."""
from __future__ import annotations

import sqlite3

from chuzom.enterprise import audit as A


def _make_pre_seq_db(path) -> None:
    """Build an audit.db whose audit_events table predates the seq column."""
    schema = A._SCHEMA.replace("    seq INTEGER,\n", "")
    schema = "\n".join(l for l in schema.splitlines() if "idx_audit_seq" not in l)
    # the audit_events seq column + its index are gone (audit_checkpoint.max_seq stays)
    assert "    seq INTEGER," not in schema and "idx_audit_seq" not in schema
    conn = sqlite3.connect(str(path))
    conn.executescript(schema)
    conn.execute(
        "INSERT INTO audit_events (id, timestamp, type, severity, actor_id, "
        "actor_email, org_id, resource, action, detail, prev_hash, hash_hex) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("evt-1", 1.0, "routing_decision", "INFO", "u", "e", "local",
         "router", "route", "{}", "GENESIS", "hash-legacy"))
    conn.commit()
    conn.close()


def test_opens_pre_seq_db_without_error_and_backfills(tmp_path):
    db = tmp_path / "audit.db"
    _make_pre_seq_db(db)

    al = A.AuditLog(db_path=db)                      # must NOT raise "no such column: seq"
    cols = {r[1] for r in al._conn.execute("PRAGMA table_info(audit_events)")}
    assert "seq" in cols                             # column added by the migration
    # the legacy row was backfilled with a contiguous seq
    seqs = [r[0] for r in al._conn.execute("SELECT seq FROM audit_events")]
    assert seqs and all(s is not None for s in seqs)


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "audit.db"
    _make_pre_seq_db(db)
    A.AuditLog(db_path=db)
    al2 = A.AuditLog(db_path=db)                     # reopening must also be clean
    cols = {r[1] for r in al2._conn.execute("PRAGMA table_info(audit_events)")}
    assert "seq" in cols


def test_fresh_db_unaffected(tmp_path):
    al = A.AuditLog(db_path=tmp_path / "fresh.db")   # new DB still gets seq from schema
    cols = {r[1] for r in al._conn.execute("PRAGMA table_info(audit_events)")}
    assert "seq" in cols
