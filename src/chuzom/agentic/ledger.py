"""TaskLedger + Milestone data model for the MGEE engine.

The ledger is the durable checkpoint: passed milestones are *frozen* into the
done-frontier and never re-executed. Escalation resumes at the first pending
milestone, handing the stronger tier the frozen artifacts as read-only context.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MilestoneStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AcceptanceResult:
    """Outcome of an objective acceptance check.

    ``deterministic`` distinguishes a real failure (escalate) from a flaky /
    non-reproducible one (re-run once, do not count against attempts).
    """

    ok: bool
    reason: str = ""
    deterministic: bool = True


# An acceptance check is an objective predicate over a milestone's artifacts.
AcceptanceCheck = Callable[[dict[str, Any]], AcceptanceResult]


@dataclass
class Attempt:
    tier: int
    ok: bool
    reason: str
    cost_usd: float = 0.0


@dataclass
class Milestone:
    id: str
    description: str
    acceptance: AcceptanceCheck
    deps: tuple[str, ...] = ()
    reversible: bool = True  # False → irreversible action, must pass the gate before DONE
    status: MilestoneStatus = MilestoneStatus.PENDING
    artifacts: dict[str, Any] = field(default_factory=dict)
    achieved_by: int | None = None  # tier that cleared it
    attempts: list[Attempt] = field(default_factory=list)


@dataclass
class TaskLedger:
    """Ordered milestones + the frozen done-frontier + budget/tier cursor."""

    goal: str
    milestones: list[Milestone]
    current_tier: int = 0
    budget_cap_usd: float = 1.0
    spent_usd: float = 0.0
    replanned: bool = False
    # P1-S2 (Known Limit A): conversation context from the calling session, handed
    # to every delegated agent via frozen_context() so a routed model isn't blind
    # to what was discussed (not just its own milestones).
    session_context: str = ""

    # ── frontier ────────────────────────────────────────────────────────────
    @property
    def done_ids(self) -> set[str]:
        return {m.id for m in self.milestones if m.status is MilestoneStatus.DONE}

    def complete(self) -> bool:
        return all(m.status is MilestoneStatus.DONE for m in self.milestones)

    def next_pending(self) -> Milestone | None:
        """Earliest *ready* PENDING milestone (all deps done).

        DAG-aware: BLOCKED nodes and their unreachable dependents are skipped, so
        a stuck milestone never stalls ready independent siblings.
        """
        done = self.done_ids
        for m in self.milestones:
            if m.status is MilestoneStatus.PENDING and all(d in done for d in m.deps):
                return m
        return None

    def freeze(self, m: Milestone, tier: int, artifacts: dict[str, Any]) -> None:
        """Mark a verified milestone DONE — it is never executed again."""
        m.status = MilestoneStatus.DONE
        m.achieved_by = tier
        m.artifacts = dict(artifacts)

    def frozen_context(self) -> list[dict[str, Any]]:
        """Read-only view of achieved milestones handed to an escalated tier so
        it resumes at the frontier instead of redoing completed work."""
        frozen = [
            {"id": m.id, "description": m.description,
             "achieved_by": m.achieved_by, "artifacts": m.artifacts}
            for m in self.milestones
            if m.status is MilestoneStatus.DONE
        ]
        if self.session_context:
            # Prepended, distinct id — pack_prompt renders it as conversation
            # context, NOT as a completed milestone.
            frozen.insert(0, {"id": "SESSION_CONTEXT", "description": self.session_context,
                              "achieved_by": None, "artifacts": {}})
        return frozen

    def remaining(self) -> list[Milestone]:
        return [m for m in self.milestones if m.status is not MilestoneStatus.DONE]

    def charge(self, cost_usd: float) -> None:
        self.spent_usd += max(0.0, cost_usd)

    def budget_left(self) -> float:
        return max(0.0, self.budget_cap_usd - self.spent_usd)
