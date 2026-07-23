"""MGEE engine — the milestone-gated escalating execution loop.

Guarantees (see docs/agentic-router.md §5): monotonic escalation over a finite
tier ladder + bounded attempts per (milestone, tier) ⇒ always terminates as
COMPLETE or a *surfaced* failure — never an infinite loop, never a silent stall.
Passed milestones are frozen into the ledger and never re-executed.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from chuzom.agentic.ledger import (
    AcceptanceResult,
    Attempt,
    Milestone,
    MilestoneStatus,
    TaskLedger,
)


class Outcome(str, Enum):
    COMPLETE = "complete"          # every milestone verified done
    SURFACED = "surfaced"          # honest, specific failure handed to the user
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass
class AgentRunResult:
    artifacts: dict[str, Any]
    cost_usd: float = 0.0
    confidence: float = 1.0


class Agent(Protocol):
    tier: int

    def run(
        self, milestone: Milestone, frozen_context: list[dict[str, Any]], budget_left: float
    ) -> AgentRunResult:
        ...


@dataclass
class Event:
    kind: str          # plan|execute|pass|fail|retry|escalate|replan|surface|complete
    milestone_id: str = ""
    tier: int = -1
    reason: str = ""

    def render(self) -> str:
        icon = {"plan": "🗺", "execute": "⚙", "pass": "✓", "fail": "✗",
                "retry": "↻", "escalate": "↑", "replan": "✎", "surface": "⚠",
                "complete": "✅"}.get(self.kind, "·")
        bits = [icon, self.kind, self.milestone_id]
        if self.tier >= 0:
            bits.append(f"t{self.tier}")
        if self.reason:
            bits.append(f"— {self.reason}")
        return " ".join(str(b) for b in bits if b != "")


@dataclass
class TaskResult:
    outcome: Outcome
    ledger: TaskLedger
    events: list[Event] = field(default_factory=list)
    reason: str = ""


# route(milestone) -> starting tier; replan(ledger) mutates remaining tail once.
Router = Callable[[Milestone], int]
ReplanFn = Callable[[TaskLedger], None]
# gate(milestone, result) -> True if an irreversible action is confirmed/safe to freeze.
Gate = Callable[[Milestone, AgentRunResult], bool]


class MGEEEngine:
    def __init__(
        self,
        agents_by_tier: dict[int, Agent],
        *,
        max_attempts_per_tier: int = 2,
        router: Router | None = None,
        replan_fn: ReplanFn | None = None,
        gate: Gate | None = None,
        event_sink: Callable[[Event], None] | None = None,
    ) -> None:
        if not agents_by_tier:
            raise ValueError("at least one tier agent is required")
        self.agents = dict(agents_by_tier)
        self.top_tier = max(self.agents)
        self.k = max(1, max_attempts_per_tier)
        self.router = router or (lambda _m: min(self.agents))
        self.replan_fn = replan_fn
        self.gate = gate or (lambda _m, _r: True)
        self.event_sink = event_sink
        self.events: list[Event] = []

    def _emit(self, kind: str, m: str = "", tier: int = -1, reason: str = "") -> None:
        ev = Event(kind, m, tier, reason)
        self.events.append(ev)
        if self.event_sink:
            self.event_sink(ev)

    def _start_tier(self, m: Milestone) -> int:
        # clamp the router's choice into the available ladder
        t = self.router(m)
        return min(max(t, min(self.agents)), self.top_tier)

    def _attempts_at(self, m: Milestone, tier: int) -> int:
        return sum(1 for a in m.attempts if a.tier == tier)

    def _verify(self, m: Milestone, artifacts: dict[str, Any]) -> AcceptanceResult:
        try:
            return m.acceptance(artifacts)
        except Exception as exc:  # noqa: BLE001 — a broken check must never hang the flow
            return AcceptanceResult(False, f"acceptance check errored: {exc}", deterministic=True)

    def run(self, ledger: TaskLedger) -> TaskResult:
        """Drive milestones to completion. Stuck milestones are *quarantined*
        (BLOCKED) and the flow continues with ready siblings — so the process
        never stalls; blocked work is surfaced together at the end."""
        self.events = []
        self._emit("plan", reason=f"{len(ledger.milestones)} milestones")
        blocked: list[str] = []

        while True:
            m = ledger.next_pending()
            if m is None:
                break  # nothing ready — either complete, or only blocked/unreachable remain
            tier = self._start_tier(m)
            m.status = MilestoneStatus.IN_PROGRESS
            status, reason = self._work_milestone(ledger, m, tier)
            if status == "budget":
                return self._budget(ledger, m)
            if status == "blocked":
                m.status = MilestoneStatus.BLOCKED
                blocked.append(f"{m.id}: {reason}")
                self._emit("surface", m.id, reason=reason)
            # "done" / "replan" → just continue the outer loop

        if ledger.complete():
            self._emit("complete")
            return TaskResult(Outcome.COMPLETE, ledger, list(self.events))
        reason = "; ".join(blocked) or "unresolved milestones (unreachable dependencies)"
        return TaskResult(Outcome.SURFACED, ledger, list(self.events), reason)

    def _work_milestone(
        self, ledger: TaskLedger, m: Milestone, tier: int
    ) -> tuple[str, str]:
        """Attempt/escalation loop for ONE milestone (bounded ⇒ terminates).

        Returns (status, reason): 'done' | 'blocked' | 'replan' | 'budget'.
        """
        while True:
            if ledger.budget_left() <= 0:
                return "budget", "budget exhausted"
            agent = self.agents[tier]
            self._emit("execute", m.id, tier)
            res, run = self._run_and_verify(agent, m, ledger, tier)
            m.attempts.append(Attempt(tier, res.ok, res.reason, run.cost_usd))

            if res.ok:
                if not m.reversible and not self.gate(m, run):
                    return "blocked", f"irreversible milestone '{m.id}' needs confirmation"
                ledger.freeze(m, tier, run.artifacts)
                self._emit("pass", m.id, tier, res.reason)
                return "done", ""

            self._emit("fail", m.id, tier, res.reason)
            if self._attempts_at(m, tier) < self.k:
                self._emit("retry", m.id, tier)
                continue
            if tier < self.top_tier:
                tier += 1  # monotonic escalation, frozen ledger carried forward
                self._emit("escalate", m.id, tier, res.reason)
                continue
            if self.replan_fn and not ledger.replanned:
                ledger.replanned = True
                self.replan_fn(ledger)
                self._emit("replan", m.id, tier)
                return "replan", ""
            return "blocked", res.reason

    def _run_and_verify(
        self, agent: Agent, m: Milestone, ledger: TaskLedger, tier: int
    ) -> tuple[AcceptanceResult, AgentRunResult]:
        run = agent.run(m, ledger.frozen_context(), ledger.budget_left())
        ledger.charge(run.cost_usd)
        res = self._verify(m, run.artifacts)
        # flaky / non-reproducible failure → re-run once, do NOT escalate on it
        if not res.ok and not res.deterministic and ledger.budget_left() > 0:
            run = agent.run(m, ledger.frozen_context(), ledger.budget_left())
            ledger.charge(run.cost_usd)
            res = self._verify(m, run.artifacts)
        return res, run

    def _budget(self, ledger: TaskLedger, m: Milestone) -> TaskResult:
        self._emit("surface", m.id, reason="budget exhausted — partial progress returned")
        return TaskResult(
            Outcome.BUDGET_EXHAUSTED, ledger, list(self.events), "budget exhausted"
        )
