"""RED3 reproduction: diff_check's `symbols` check is a raw substring match over
the produced git diff text (chuzom.agentic.acceptance.diff_check /
chuzom.agentic.engine, see acceptance.py L44-67). It has no AST/semantic
understanding whatsoever. An executor (weak local model OR a model that is
lazy/rushed/wrong) can satisfy "symbols" by writing the symbol name into a
comment or a no-op stub -- producing code that is FUNCTIONALLY WRONG or a
complete no-op -- and the milestone still freezes DONE.

Run with: <WORKTREE>/.venv-audit/bin/python repro_diff_check_symbol_gaming.py
"""
import sys

sys.path.insert(0, "src")

from chuzom.agentic.delegate import delegate
from chuzom.agentic.engine import AgentRunResult
from chuzom.agentic.ledger import Milestone
from chuzom.agentic.acceptance import diff_check


class FakeStubbingAgent:
    """Simulates an executor that satisfies the letter of the acceptance check
    (file exists, symbol string appears in the diff) while doing NONE of the
    actual work the milestone asked for."""

    tier = 1

    def run(self, milestone, frozen_context, budget_left):
        # Real task: "implement validate_password(pw) that enforces the policy
        # (>=12 chars, upper+lower+digit+symbol)". The planner's diff_check
        # requires the file to exist and the symbol 'def validate_password' to
        # appear in the diff -- it says NOTHING about what the function body
        # does. So the cheapest possible way to pass is a stub that always
        # returns True.
        fake_diff = (
            "diff --git a/auth.py b/auth.py\n"
            "+++ b/auth.py\n"
            "+def validate_password(pw):\n"
            "+    # TODO: enforce real policy later\n"
            "+    return True  # always accepts -- SECURITY HOLE, not implemented\n"
        )
        artifacts = {
            "provider": "fake-stub",
            "diff": fake_diff,
            "files": ["auth.py"],
            "output": "Implemented validate_password in auth.py.",
        }
        return AgentRunResult(artifacts, cost_usd=0.0, confidence=1.0)


milestone = Milestone(
    id="add-password-validation",
    description=(
        "Implement validate_password(pw) in auth.py enforcing: length >= 12, "
        "at least one uppercase, one lowercase, one digit, one symbol. This "
        "gates account creation, so a wrong implementation is a security bug."
    ),
    acceptance=diff_check(files=["auth.py"], symbols=["def validate_password"]),
)

result = delegate(
    goal="add password validation",
    milestones=[milestone],
    adapters_by_tier={1: FakeStubbingAgent()},
    baseline_cost_per_milestone=0.20,
    budget_cap_usd=1.0,
)

print("=== RESULT ===")
print("outcome:", result.outcome)
print("ok:", result.ok)
print("milestone status:", milestone.status)
print("frozen diff (the 'implementation'):")
print(milestone.artifacts.get("diff"))
print()
print(result.summary())
print()
assert result.ok
assert "return True" in milestone.artifacts.get("diff", "")
print(">>> PROVEN: a security-critical validation function that ALWAYS RETURNS "
      "TRUE (accepts every password, including empty/blank) passes diff_check "
      "and freezes DONE -- because diff_check only substring-matches the symbol "
      "name in the diff text, never executes or reasons about the function body. "
      "A weak/rushed/adversarial executor model has a direct, low-effort path to "
      "a verified-complete security hole.")
