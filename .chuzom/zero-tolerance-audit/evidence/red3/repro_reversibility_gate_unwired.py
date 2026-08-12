"""RED3 reproduction: prove the reversibility_gate/worktree isolation described in
worktree.py's docstring ("Irreversible milestones (push / merge / delete /
external-send) must not auto-freeze on a bare acceptance pass") is NEVER wired
into the production llm_delegate path (src/chuzom/tools/agentic.py).

Method: call chuzom.agentic.delegate.delegate() the SAME way
chuzom.agentic.service.run_delegation() does (which is what tools/agentic.py's
llm_delegate() calls) with NO gate= argument -- exactly as production does --
and show that a milestone explicitly marked reversible=False, whose acceptance
check is a canary that the fake agent trivially satisfies by printing a string
in its own stdout (no real work performed, no worktree, no merge, no isolation),
freezes DONE and the whole delegation reports outcome=complete.

Run with: <WORKTREE>/.venv-audit/bin/python repro_reversibility_gate_unwired.py
"""
import sys

sys.path.insert(0, "src")  # run from worktree root

from chuzom.agentic.delegate import delegate
from chuzom.agentic.engine import AgentRunResult
from chuzom.agentic.ledger import Milestone
from chuzom.agentic.acceptance import canary_check


class FakeIrreversibleAgent:
    """Simulates a delegated backend (Codex/ReAct) that does NOT actually push
    anything -- it just says it did, in its own stdout ('output' artifact field).
    This is exactly what CodexAdapter.run() / ReActAgent.run() put in
    artifacts['output']: the executing agent's own (self-reported, unverified)
    text."""

    tier = 1

    def run(self, milestone, frozen_context, budget_left):
        # NB: no git push actually happened. No file was touched. No worktree
        # was created. The agent just emits the canary marker in its own output,
        # which is *exactly* what canary_check(field="output") inspects.
        fake_stdout = "I have force-pushed the hotfix to main. DEPLOY_DONE_9f3a"
        artifacts = {
            "provider": "fake-irreversible-claim",
            "output": fake_stdout,
            "diff": "",       # no actual code change
            "files": [],      # no actual files touched
        }
        return AgentRunResult(artifacts, cost_usd=0.0, confidence=1.0)


milestone = Milestone(
    id="deploy-hotfix",
    description="git push --force origin main to deploy the critical hotfix",
    acceptance=canary_check("DEPLOY_DONE_9f3a", field="output"),
    reversible=False,  # explicitly marked IRREVERSIBLE by the (hypothetical) planner
)

# This mirrors EXACTLY what chuzom.agentic.service.run_delegation() does, which is
# EXACTLY what chuzom.tools.agentic.llm_delegate() calls (see tools/agentic.py L146-152):
# no `gate=` kwarg is ever passed anywhere in that call chain.
result = delegate(
    goal="deploy the hotfix",
    milestones=[milestone],
    adapters_by_tier={1: FakeIrreversibleAgent()},
    baseline_cost_per_milestone=0.20,
    budget_cap_usd=1.0,
)

print("=== RESULT ===")
print("outcome:", result.outcome)
print("ok:", result.ok)
print("milestone status:", milestone.status)
print("milestone.reversible:", milestone.reversible)
print("achieved_by tier:", milestone.achieved_by)
print()
print(result.summary())
print()
assert result.ok, "expected the irreversible milestone to be (wrongly) frozen DONE"
assert milestone.status.value == "done"
print(">>> PROVEN: an IRREVERSIBLE milestone (reversible=False) froze DONE with "
      "ZERO worktree isolation, ZERO merge-gate check, and ZERO real work -- only "
      "because the executing agent's own self-reported stdout happened to contain "
      "the canary string. reversibility_gate()/GitWorktreeOps (worktree.py) were "
      "never invoked: delegate() was called with no gate=, exactly as production "
      "tools/agentic.py::llm_delegate() calls it.")
