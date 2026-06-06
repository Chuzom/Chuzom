"""Dual-write lineage storage — JSONL for real-time, SQLite for analytics."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chuzom.lineage.decision_logger import RoutingDecision


class LineageStore:
    """Dual-write storage backend for routing decisions.

    - JSONL file for real-time access and log rotation
    - SQLite for efficient queries and analytics
    """

    def __init__(self, router_dir: Path | str | None = None) -> None:
        """Initialize lineage store.

        Args:
            router_dir: Override default ~/.chuzom directory
        """
        if router_dir is None:
            router_dir = Path.home() / ".chuzom"
        else:
            router_dir = Path(router_dir)

        router_dir.mkdir(parents=True, exist_ok=True)

        self.jsonl_file = router_dir / "routing_lineage.jsonl"
        self.db_file = router_dir / "routing_lineage.db"

        # Initialize SQLite schema
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite schema if not present."""
        conn = sqlite3.connect(self.db_file)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS routing_decisions (
                    decision_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    selected_model TEXT NOT NULL,
                    selection_reason TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    cost_usd REAL,
                    latency_ms REAL,
                    routing_overhead_ms REAL,
                    fallback_chain TEXT,  -- JSON array as string
                    fallback_reason TEXT,
                    request_id TEXT,
                    parent_decision_id TEXT,
                    metadata TEXT,  -- JSON object as string
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create indexes for common queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_operation ON routing_decisions(operation)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_model ON routing_decisions(selected_model)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_classification ON routing_decisions(classification)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON routing_decisions(timestamp)")
            conn.commit()
        finally:
            conn.close()

    def append(self, decision: RoutingDecision) -> None:
        """Append a routing decision to both JSONL and SQLite.

        Args:
            decision: RoutingDecision to log
        """
        # Write to JSONL (append-only)
        with open(self.jsonl_file, "a") as f:
            f.write(json.dumps(decision.to_dict()) + "\n")

        # Write to SQLite
        conn = sqlite3.connect(self.db_file)
        try:
            conn.execute(
                """
                INSERT INTO routing_decisions (
                    decision_id, operation, classification, selected_model,
                    selection_reason, timestamp, input_tokens, output_tokens,
                    total_tokens, cost_usd, latency_ms, routing_overhead_ms,
                    fallback_chain, fallback_reason, request_id, parent_decision_id,
                    metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.operation,
                    decision.classification,
                    decision.selected_model,
                    decision.selection_reason,
                    decision.timestamp,
                    decision.input_tokens,
                    decision.output_tokens,
                    decision.total_tokens,
                    decision.cost_usd,
                    decision.latency_ms,
                    decision.routing_overhead_ms,
                    json.dumps(decision.fallback_chain),
                    decision.fallback_reason,
                    decision.request_id,
                    decision.parent_decision_id,
                    json.dumps(decision.metadata),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def query_jsonl(self, limit: int = 100) -> list[dict]:
        """Read recent decisions from JSONL file.

        Args:
            limit: Max number of recent records to return

        Returns:
            List of decision records (most recent first)
        """
        if not self.jsonl_file.exists():
            return []

        records = []
        with open(self.jsonl_file) as f:
            for line in f:
                records.append(json.loads(line))

        return records[-limit:]  # Last N records

    def query_db(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute SQL query against SQLite backend.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            List of result rows as dicts
        """
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row  # Return rows as dicts
        try:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
