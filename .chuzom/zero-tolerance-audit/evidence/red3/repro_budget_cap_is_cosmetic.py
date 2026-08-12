"""RED3 reproduction: `budget_usd` (the parameter every caller of llm_delegate /
llm_act passes to bound financial exposure) does NOT bound anything in the
production default wiring, because BOTH default adapters ship with
`cost_per_call_usd: float = 0.0`:

  chuzom/agentic/adapters.py  : CodexAdapter.cost_per_call_usd  = 0.0 (default)
  chuzom/agentic/react.py     : ReActAgent.cost_per_call_usd    = 0.0 (default)
  chuzom/tools/agentic.py:91  : _default_adapters() constructs BOTH with no override:
                                   return {0: ReActAgent(tier=0), 1: CodexAdapter(tier=1)}

MGEEEngine._run_and_verify() -> ledger.charge(run.cost_usd) -> ledger.spent_usd
+= max(0.0, cost_usd). If cost_usd is always 0.0, ledger.spent_usd NEVER
increases, so `ledger.budget_left() <= 0` (engine.py L184, the ONLY place
budget is checked) can NEVER become true from real execution -- no matter how
low budget_usd is set by the caller.

This proves, with the REAL (unmodified) MGEEEngine/TaskLedger/delegate() code
and only fake agents standing in for subprocess/network calls, that:
  (a) an always-failing milestone with a $0-cost agent burns through its full
      structural retry/escalation ladder (k attempts x tiers) regardless of
      how low budget_usd is set -- "budget exhausted" never fires;
  (b) the IDENTICAL scenario with a nonzero cost_per_call_usd DOES stop early
      on budget, proving budget_cap_usd is only a real brake when an adapter
      opts into honest cost accounting -- which neither shipped default
      adapter does.

Run with: <WORKTREE>/.venv-audit/bin/python repro_budget_cap_is_cosmetic.py
"""
import sys

sys.path.insert(0, "src")

from chuzom.agentic.delegate import delegate
from chuzom.agentic.engine import AgentRunResult
from chuzom.agentic.ledger import Milestone
from chuzom.agentic.acceptance import canary_check


class AlwaysFailingAgent:
    """Mirrors the real shape of CodexAdapter/ReActAgent: an agent whose work
    never satisfies the acceptance check (e.g. a task genuinely beyond the
    model's capability), with a configurable cost_per_call_usd exactly like
    the real adapters expose."""

    def __init__(self, tier: int, cost_per_call_usd: float = 0.0):
        self.tier = tier
        self.cost_per_call_usd = cost_per_call_usd
        self.calls = 0

    def run(self, milestone, frozen_context, budget_left):
        self.calls += 1
        return AgentRunResult(
            {"provider": "fake", "output": "I attempted the task but nothing to show."},
            cost_usd=self.cost_per_call_usd,
            confidence=0.3,
        )


def run_scenario(cost_per_call_usd: float, budget_cap_usd: float):
    milestone = Milestone(
        id="impossible-task",
        description="do something the check never accepts",
        acceptance=canary_check("NEVER_APPEARS_TOKEN", field="output"),
    )
    tier0 = AlwaysFailingAgent(0, cost_per_call_usd)
    tier1 = AlwaysFailingAgent(1, cost_per_call_usd)
    # Exactly the production shape: 2 tiers, max_attempts_per_tier=2 (the
    # hardcoded value tools/agentic.py::llm_delegate uses for the non-bounded
    # path), no gate=, no replan_fn= (both are dead in production, proven
    # separately) -- this IS how chuzom.agentic.service.run_delegation calls
    # delegate() today.
    result = delegate(
        goal="impossible task",
        milestones=[milestone],
        adapters_by_tier={0: tier0, 1: tier1},
        baseline_cost_per_milestone=0.20,
        budget_cap_usd=budget_cap_usd,
        max_attempts_per_tier=2,
    )
    return result, tier0.calls, tier1.calls


print("=== Scenario A: production default cost accounting (cost_per_call_usd=0.0), "
      "budget_usd set VERY low ($0.0001) ===")
result_a, t0_calls_a, t1_calls_a = run_scenario(cost_per_call_usd=0.0, budget_cap_usd=0.0001)
print("outcome:", result_a.outcome, "| ledger.spent_usd:", result_a.ledger.spent_usd)
print(f"tier0 real .run() calls: {t0_calls_a} | tier1 real .run() calls: {t1_calls_a}")
print("total real backend invocations:", t0_calls_a + t1_calls_a)
print()

print("=== Scenario B: SAME task, SAME budget_usd ($0.0001), but with HONEST "
      "cost accounting (cost_per_call_usd=$0.01/call) -- what a caller believes "
      "budget_usd is protecting them against ===")
result_b, t0_calls_b, t1_calls_b = run_scenario(cost_per_call_usd=0.01, budget_cap_usd=0.0001)
print("outcome:", result_b.outcome, "| ledger.spent_usd:", result_b.ledger.spent_usd)
print(f"tier0 real .run() calls: {t0_calls_b} | tier1 real .run() calls: {t1_calls_b}")
print("total real backend invocations:", t0_calls_b + t1_calls_b)
print()

assert result_a.outcome.value != "budget_exhausted", (
    "expected scenario A to NOT stop on budget (cost=0 never trips the check)"
)
assert result_a.ledger.spent_usd == 0.0
assert (t0_calls_a + t1_calls_a) == 4, "expected the full 2-tier x 2-attempt ladder to run"
assert result_b.outcome.value == "budget_exhausted", (
    "expected scenario B to stop almost immediately once real cost accrues"
)
assert (t0_calls_b + t1_calls_b) < (t0_calls_a + t1_calls_a)

print(
    ">>> PROVEN: with the production default adapters (CodexAdapter, ReActAgent -- "
    "both cost_per_call_usd=0.0 by default, and _default_adapters() in "
    "tools/agentic.py never overrides this), `budget_usd` provides ZERO real "
    "protection against retry-storm exposure. An impossible/miscalibrated task "
    "burns through the FULL structural ladder (2 tiers x 2 attempts = 4 real "
    "subprocess/network invocations per milestone here; more with multiple "
    "milestones and the non-deterministic flaky-retry doubling in "
    "engine.py::_run_and_verify) NO MATTER what budget_usd the caller passes -- "
    "'budget exhausted' can never fire from real work. The parameter only does "
    "something if a caller supplies an adapter with honest non-zero cost "
    "accounting, which nothing in the shipped default path does. A user who "
    "passes budget_usd=0.05 believing it caps their exposure is not protected "
    "by that number at all; the actual brake is the hardcoded structural bound "
    "(tier count x max_attempts_per_tier x up to 2x flaky-retry), which is not "
    "user-configurable and not what budget_usd communicates."
)
