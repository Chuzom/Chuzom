"""Immutable audit log with tamper-evident hash chain.

Every event carries a SHA-256 hash of (prev_hash + canonical_payload).
Any later modification to the row breaks the chain — `verify_chain()`
walks the table and reports the first row whose computed hash diverges
from the stored hash.

SQLite-backed at ~/.tessera/audit.db. The schema is append-only by
contract (the API never exposes UPDATE or DELETE on event rows);
tampering requires direct SQL access AND the discipline to update every
subsequent row's hash, which `verify_chain` detects regardless.

Export formats: CEF (Common Event Format — what SIEMs ingest), JSON,
CSV. Each is a separate function so callers can pipe through their
own filters.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path


# ────────────────────────────────────────────────────────────────────────
# Event model
# ────────────────────────────────────────────────────────────────────────

class AuditEventType:
    """Canonical event type strings — kept as a class of constants rather
    than an Enum so external systems can extend with custom event types
    without forking Tessera."""

    ROUTING_DECISION = "routing.decision"
    QUOTA_BREACH = "quota.breach"
    POLICY_CHANGE = "policy.change"
    SECRET_ACCESS = "secret.access"
    IDENTITY_LOGIN = "identity.login"
    IDENTITY_LOGOUT = "identity.logout"
    IDENTITY_TOKEN_ISSUED = "identity.token.issued"
    IDENTITY_TOKEN_REVOKED = "identity.token.revoked"
    IDENTITY_USER_DEACTIVATED = "identity.user.deactivated"
    REDACTION_APPLIED = "redaction.applied"
    PII_DETECTED = "pii.detected"
    EXPORT_GENERATED = "export.generated"


@dataclass(frozen=True)
class AuditEvent:
    """One row in the audit log.

    `hash_hex` is computed by AuditLog.append; callers don't set it.
    Likewise `prev_hash`. `id` and `timestamp` are auto-filled if absent.
    """

    type: str  # one of AuditEventType.* (or a custom string)
    actor_id: str  # User.id or "system" for automated events
    actor_email: str  # denormalized for SIEM readability
    org_id: str  # required — every event belongs to an org
    resource: str  # the thing acted on: "lineage:abc", "team:eng", etc.
    action: str  # the verb: "created", "viewed", "denied", ...
    detail: dict = field(default_factory=dict)  # JSON-serializable payload
    severity: str = "info"  # info | warn | critical
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    prev_hash: str = ""
    hash_hex: str = ""


# ────────────────────────────────────────────────────────────────────────
# Schema
# ────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    type TEXT NOT NULL,
    severity TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_email TEXT NOT NULL,
    org_id TEXT NOT NULL,
    resource TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash_hex TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(type);
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_events(org_id);
"""


# ────────────────────────────────────────────────────────────────────────
# Hashing
# ────────────────────────────────────────────────────────────────────────

def _canonical_payload(event: AuditEvent) -> str:
    """Build the canonical string fed into SHA-256.

    Sorted JSON keys + fixed field order makes the hash deterministic
    across Python implementations.
    """
    body = {
        "id": event.id,
        "timestamp": event.timestamp,
        "type": event.type,
        "severity": event.severity,
        "actor_id": event.actor_id,
        "actor_email": event.actor_email,
        "org_id": event.org_id,
        "resource": event.resource,
        "action": event.action,
        "detail": event.detail,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _hash(prev_hash: str, payload: str) -> str:
    return hashlib.sha256(
        (prev_hash + payload).encode("utf-8")
    ).hexdigest()


# ────────────────────────────────────────────────────────────────────────
# Log
# ────────────────────────────────────────────────────────────────────────

class TamperDetected(RuntimeError):
    """Raised by verify_chain when a row's stored hash diverges from
    the recomputed hash — indicates the log has been modified outside
    the API."""

    def __init__(self, row_index: int, expected: str, actual: str):
        self.row_index = row_index
        super().__init__(
            f"Audit log tampering detected at row {row_index}: "
            f"expected hash {expected[:16]}… got {actual[:16]}…"
        )


class AuditLog:
    """Append-only SQLite-backed audit log."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path(
            os.environ.get("TESSERA_AUDIT_PATH")
            or (Path.home() / ".tessera" / "audit.db")
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── Append ────────────────────────────────────────────────────────

    def append(self, event: AuditEvent) -> AuditEvent:
        """Append an event. Returns the persisted event with prev_hash
        + hash_hex filled in."""
        prev = self._latest_hash()
        payload = _canonical_payload(event)
        h = _hash(prev, payload)
        filled = AuditEvent(
            type=event.type, actor_id=event.actor_id,
            actor_email=event.actor_email, org_id=event.org_id,
            resource=event.resource, action=event.action,
            detail=dict(event.detail), severity=event.severity,
            id=event.id, timestamp=event.timestamp,
            prev_hash=prev, hash_hex=h,
        )
        self._conn.execute(
            "INSERT INTO audit_events (id, timestamp, type, severity, "
            "actor_id, actor_email, org_id, resource, action, detail, "
            "prev_hash, hash_hex) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (filled.id, filled.timestamp, filled.type, filled.severity,
             filled.actor_id, filled.actor_email, filled.org_id,
             filled.resource, filled.action, json.dumps(filled.detail),
             filled.prev_hash, filled.hash_hex),
        )
        self._conn.commit()
        return filled

    def _latest_hash(self) -> str:
        row = self._conn.execute(
            "SELECT hash_hex FROM audit_events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else ""

    # ── Read ──────────────────────────────────────────────────────────

    def recent(self, limit: int = 100, org_id: str | None = None) -> list[dict]:
        if org_id:
            cursor = self._conn.execute(
                "SELECT * FROM audit_events WHERE org_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (org_id, limit),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def by_actor(self, actor_id: str, limit: int = 100) -> list[dict]:
        cursor = self._conn.execute(
            "SELECT * FROM audit_events WHERE actor_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (actor_id, limit),
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM audit_events"
        ).fetchone()
        return row[0] if row else 0

    # ── Integrity ─────────────────────────────────────────────────────

    def verify_chain(self) -> bool:
        """Walk the log in order and verify the hash chain. Raises
        TamperDetected on the first inconsistency. Returns True when
        the whole chain is intact."""
        cursor = self._conn.execute(
            "SELECT id, timestamp, type, severity, actor_id, actor_email, "
            "org_id, resource, action, detail, prev_hash, hash_hex "
            "FROM audit_events ORDER BY timestamp ASC"
        )
        prev = ""
        for idx, row in enumerate(cursor.fetchall()):
            (
                id_, ts, type_, severity, actor_id, actor_email, org_id,
                resource, action, detail_json, prev_hash, hash_hex,
            ) = row
            event = AuditEvent(
                type=type_, actor_id=actor_id, actor_email=actor_email,
                org_id=org_id, resource=resource, action=action,
                detail=json.loads(detail_json), severity=severity,
                id=id_, timestamp=ts,
            )
            payload = _canonical_payload(event)
            expected = _hash(prev, payload)
            if expected != hash_hex or prev_hash != prev:
                raise TamperDetected(idx, expected, hash_hex)
            prev = hash_hex
        return True

    # ── Export ────────────────────────────────────────────────────────

    def export_cef(self, *, limit: int = 1000) -> str:
        """Render as ArcSight Common Event Format — what most SIEMs ingest.

        Each row becomes a single-line CEF record:
            CEF:0|Tessera|router|0.0.2|<event_type>|<action>|<severity>|...
        """
        sev_map = {"info": 3, "warn": 6, "critical": 9}
        lines = []
        for row in self._iter_oldest_first(limit=limit):
            sev = sev_map.get(row["severity"], 3)
            extension = " ".join([
                f"rt={int(row['timestamp'] * 1000)}",
                f"suser={row['actor_email']}",
                f"suid={row['actor_id']}",
                f"sntdom={row['org_id']}",
                f"act={row['action']}",
                f"cs1Label=resource cs1={row['resource']}",
                f"cs2Label=audit_id cs2={row['id']}",
            ])
            lines.append(
                f"CEF:0|Tessera|router|0.0.2|{row['type']}|"
                f"{row['action']}|{sev}|{extension}"
            )
        return "\n".join(lines)

    def export_json(self, *, limit: int = 1000) -> str:
        return json.dumps(
            list(self._iter_oldest_first(limit=limit)),
            indent=2, default=str,
        )

    def export_csv(self, *, limit: int = 1000) -> str:
        import csv
        import io

        rows = list(self._iter_oldest_first(limit=limit))
        if not rows:
            return ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        return buf.getvalue()

    def _iter_oldest_first(self, *, limit: int):
        cursor = self._conn.execute(
            "SELECT * FROM audit_events ORDER BY timestamp ASC LIMIT ?",
            (limit,),
        )
        cols = [c[0] for c in cursor.description]
        for row in cursor.fetchall():
            yield dict(zip(cols, row))

    def close(self) -> None:
        self._conn.close()
