"""delegate() — the single entry point that ties PLAN → engine → adapters.

Given a caller-provided milestone list, a tier→adapter map, and a premium
baseline cost, it runs the MGEE engine and returns one bundle: the outcome, the
final ledger, the transparency event stream, and honest savings. The auto-planner
(freeform task → milestones) is intentionally NOT here — decomposition is a
design decision handled a layer up; this orchestrator is pure, deterministic glue.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from chuzom.agentic.engine import (
    Agent,
    Event,
    Gate,
    MGEEEngine,
    Outcome,
    ReplanFn,
    Router,
)
from chuzom.agentic.ledger import Milestone, TaskLedger
from chuzom.agentic.savings import Savings, compute_savings


@dataclass
class DelegationResult:
    outcome: Outcome
    ledger: TaskLedger
    events: list[Event]
    savings: Savings
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.COMPLETE

    def summary(self) -> str:
        """Human-readable transparency: the event stream + savings + verdict."""
        lines = [e.render() for e in self.events]
        lines.append(self.savings.render())
        verdict = {
            Outcome.COMPLETE: "✅ complete",
            Outcome.SURFACED: f"⚠ surfaced — {self.reason}",
            Outcome.BUDGET_EXHAUSTED: "⚠ budget exhausted (partial)",
        }[self.outcome]
        lines.append(verdict)
        return "\n".join(lines)


def delegate(
    goal: str,
    milestones: list[Milestone],
    adapters_by_tier: dict[int, Agent],
    *,
    baseline_cost_per_milestone: float,
    budget_cap_usd: float = 1.0,
    max_attempts_per_tier: int = 2,
    router: Router | None = None,
    replan_fn: ReplanFn | None = None,
    gate: Gate | None = None,
    event_sink: Callable[[Event], None] | None = None,
    session_context: str = "",
) -> DelegationResult:
    """Run one milestone-gated escalating delegation and return a result bundle."""
    ledger = TaskLedger(goal=goal, milestones=milestones, budget_cap_usd=budget_cap_usd,
                        session_context=session_context)
    engine = MGEEEngine(
        adapters_by_tier,
        max_attempts_per_tier=max_attempts_per_tier,
        router=router,
        replan_fn=replan_fn,
        gate=gate,
        event_sink=event_sink,
    )
    result = engine.run(ledger)
    savings = compute_savings(ledger, baseline_cost_per_milestone)
    return DelegationResult(
        outcome=result.outcome,
        ledger=result.ledger,
        events=result.events,
        savings=savings,
        reason=result.reason,
    )
