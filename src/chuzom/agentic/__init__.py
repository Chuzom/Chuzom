"""Chuzom Agentic Router — milestone-gated escalating delegation.

See docs/agentic-router.md for the full design. The P1 core here is the
deterministic Milestone-Gated Escalating Execution (MGEE) engine, provable with
fake agents (no real models) so the flow — carry-forward, monotonic escalation,
bounded attempts, never-stuck termination — is verified before real backends.
"""
from chuzom.agentic.engine import MGEEEngine, Outcome, TaskResult
from chuzom.agentic.ledger import (
    AcceptanceResult,
    Milestone,
    MilestoneStatus,
    TaskLedger,
)

__all__ = [
    "AcceptanceResult",
    "MGEEEngine",
    "Milestone",
    "MilestoneStatus",
    "Outcome",
    "TaskLedger",
    "TaskResult",
]
