"""Routing decision lineage tracking — audit every model selection and token usage.

Provides observability into which model handled each operation, why it was selected,
how many tokens were used, and whether that selection was optimal.

Key modules:
- decision_logger: Capture routing decisions with full trace
- lineage_store: JSONL + SQLite dual-write backend
- lineage_query: Query and analyze lineage data
- report_generator: Human-readable reports
"""

from __future__ import annotations

from chuzom.lineage.decision_logger import log_routing_decision
from chuzom.lineage.lineage_query import LineageQuery
from chuzom.lineage.report_generator import generate_routing_report

__all__ = [
    "log_routing_decision",
    "LineageQuery",
    "generate_routing_report",
]
