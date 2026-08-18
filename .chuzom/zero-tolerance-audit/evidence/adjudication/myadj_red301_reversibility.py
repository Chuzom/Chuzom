"""Independent repro for RED3-01: is the reversibility gate wired into the
production delegation path?

Method: call chuzom.agentic.service.run_delegation() -- the exact function
tools/agentic.py::llm_delegate() calls -- with ONE milestone marked
reversible=False, an acceptance check that always passes, and NO gate= kwarg
(because run_delegation() has no gate parameter to pass one through). If the
milestone freezes DONE with no worktree ever created and no gate ever
consulted, the finding is confirmed at the exact call boundary the product
actually uses by default.

No DB, no filesystem writes outside this venv's import machinery, no network.
Pure in-memory dataclasses.
"""
import sys

WORKTREE = sys.argv[1] if len(sys.argv) > 1 else None
if WORKTREE:
    sys.path.insert(0, WORKTREE + "/src")

from chuzom.agentic.service import run_delegation
from chuzom.agentic.engine import AgentRunResult
from chuzom.agentic.ledger import Milestone, AcceptanceResult

GATE_CALLS = []


class FakeIrreversibleAgent:
    tier = 0

    def run(self, milestone, frozen_context, budget_left):
        # Simulates an executor that just claims success -- e.g. "I deleted the
        # production table" -- with NO worktree artifact at all.
        return AgentRunResult(artifacts={"claim": "irreversible action performed"}, cost_usd=0.0)


def always_pass(artifacts):
    return AcceptanceResult(True, "trust the executor's claim")


m = Milestone(
    id="drop-prod-table",
    description="Drop the legacy_users table in production",
    acceptance=always_pass,
    reversible=False,  # <-- irreversible, must require gate/worktree confirmation per README
)

result = run_delegation(
    goal="Drop the legacy_users table in production",
    milestones=[m],
    adapters_by_tier={0: FakeIrreversibleAgent()},
    baseline_cost_per_milestone=0.20,
    budget_cap_usd=1.0,
)

print("=== RED3-01 repro (via service.run_delegation, the exact fn llm_delegate() calls) ===")
print("outcome:", result.get("outcome"))
print("milestones:", result.get("milestones"))
print("summary:\n" + result.get("summary", ""))
print()
print("run_delegation() signature accepts no `gate` kwarg -- confirmed by TypeError test below:")
try:
    run_delegation(
        goal="x", milestones=[m], adapters_by_tier={0: FakeIrreversibleAgent()},
        baseline_cost_per_milestone=0.20, gate=lambda m, r: False,
    )
    print("UNEXPECTED: gate kwarg was accepted")
except TypeError as e:
    print("CONFIRMED TypeError (no gate param on run_delegation):", e)
