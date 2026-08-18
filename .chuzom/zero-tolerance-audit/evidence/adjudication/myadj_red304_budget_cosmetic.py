"""Independent repro for RED3-04: with cost_per_call_usd=0.0 (both shipped
default adapters' default), can BUDGET_EXHAUSTED ever fire from real
default-adapter execution? Contrast with a nonzero-cost agent to prove the
budget mechanism itself works correctly when fed a nonzero cost -- isolating
the defect to the DEFAULT VALUE, not the ledger/engine logic.

Pure in-memory, no DB, no subprocess, no network.
"""
import sys

WORKTREE = sys.argv[1] if len(sys.argv) > 1 else None
if WORKTREE:
    sys.path.insert(0, WORKTREE + "/src")

from chuzom.agentic.service import run_delegation
from chuzom.agentic.engine import AgentRunResult
from chuzom.agentic.ledger import Milestone, AcceptanceResult
from chuzom.agentic.adapters import CodexAdapter
from chuzom.agentic.react import ReActAgent


def never_pass(_artifacts):
    return AcceptanceResult(False, "never satisfied -- forces retries/escalation")


class AlwaysFailingAgent:
    def __init__(self, tier, cost_per_call_usd=0.0):
        self.tier = tier
        self.cost_per_call_usd = cost_per_call_usd

    def run(self, milestone, frozen_context, budget_left):
        return AgentRunResult(artifacts={}, cost_usd=self.cost_per_call_usd)


m1 = Milestone(id="impossible", description="An impossible milestone", acceptance=never_pass)

print("=" * 70)
print("PART 1: confirm both shipped default adapters default to cost_per_call_usd=0.0")
print("=" * 70)
print("CodexAdapter().cost_per_call_usd :", CodexAdapter(tier=1).cost_per_call_usd)
print("ReActAgent().cost_per_call_usd   :", ReActAgent(tier=0).cost_per_call_usd)
print()

print("=" * 70)
print("PART 2: run with cost_per_call_usd=0.0 (matches both default adapters)")
print("=" * 70)
result_zero = run_delegation(
    goal="impossible", milestones=[m1],
    adapters_by_tier={0: AlwaysFailingAgent(0, 0.0), 1: AlwaysFailingAgent(1, 0.0)},
    baseline_cost_per_milestone=0.20,
    budget_cap_usd=0.01,          # tiny budget -- should exhaust almost immediately IF cost > 0
    max_attempts_per_tier=2,
)
print("outcome:", result_zero["outcome"], "  (expect: 'surfaced'/'blocked', NEVER 'budget_exhausted')")
print("milestones:", result_zero["milestones"])
print()

print("=" * 70)
print("PART 3: SAME scenario but with a nonzero cost_per_call_usd -- control group")
print("=" * 70)
m2 = Milestone(id="impossible2", description="An impossible milestone", acceptance=never_pass)
result_nonzero = run_delegation(
    goal="impossible2", milestones=[m2],
    adapters_by_tier={0: AlwaysFailingAgent(0, 0.005), 1: AlwaysFailingAgent(1, 0.005)},
    baseline_cost_per_milestone=0.20,
    budget_cap_usd=0.01,          # same tiny budget
    max_attempts_per_tier=2,
)
print("outcome:", result_nonzero["outcome"], "  (expect: 'budget_exhausted' -- proves ledger/engine")
print("                                          budget mechanism itself IS correct)")
print("milestones:", result_nonzero["milestones"])
print()
print("=== CONCLUSION ===")
print("Same engine, same ledger, same milestone shape. Only the per-call cost differs.")
print("cost=0.0 -> outcome:", result_zero["outcome"])
print("cost>0.0 -> outcome:", result_nonzero["outcome"])
print("This isolates the defect precisely: the BUDGET MECHANISM is not cosmetic")
print("(it correctly halts execution when fed a nonzero cost). What is cosmetic")
print("is that BOTH shipped default adapters hardcode cost_per_call_usd=0.0, so")
print("'budget exhausted' can never be the reason a default-adapter run stops --")
print("it always stops via tier-ladder exhaustion + blocked instead.")
