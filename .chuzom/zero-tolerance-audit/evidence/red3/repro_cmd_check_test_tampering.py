"""RED3 reproduction: cmd_check's ONLY signal is the process exit code
(chuzom/agentic/acceptance.py L70-92). The milestone's planner-chosen command is
typically `pytest <path>` (see the planner prompt's own example in
tools/agentic.py L38: {"type":"cmd","command":["argv","..."]}). Nothing in the
acceptance layer, the CodexAdapter, or the ReActAgent scopes the executor's
filesystem writes to "only the file under test" -- CodexAdapter runs with
sandbox_mode="workspace-write" (adapters.py L91) and ReActAgent's write_file tool
is bounded only to "inside cwd", not "outside the test file" (react.py L112-126).

This proves an executor can make `pytest test_calc.py` exit 0 by weakening the
test's assertion instead of fixing the actual bug in the source file the
milestone was about -- and the acceptance check cannot tell the difference.

Setup: a real git repo (created by a preceding bash step) with:
  calc.py:      add(a, b) returns a - b   (a real bug)
  test_calc.py: asserts add(2, 3) == 5    (fails against the real bug)

This script simulates the executor's "fix": instead of touching calc.py, it
rewrites test_calc.py so the assertion is trivially true, then re-runs the
SAME cmd_check the milestone would use.

Run with: <WORKTREE>/.venv-audit/bin/python repro_cmd_check_test_tampering.py <repo_dir>
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "src")

from chuzom.agentic.acceptance import cmd_check

repo = Path(sys.argv[1]).resolve()
calc = repo / "calc.py"
test = repo / "test_calc.py"

print("=== calc.py BEFORE 'fix' (the actual bug) ===")
print(calc.read_text())

# The "fix" a lazy/weak/adversarial executor takes: touch the TEST, not the bug.
test.write_text(
    "from calc import add\n\n"
    "def test_add():\n"
    "    assert True  # was: assert add(2, 3) == 5\n"
)

check = cmd_check(
    [sys.executable, "-m", "pytest", "-q", "test_calc.py"], cwd=str(repo), timeout=30
)
result = check({})

print("=== calc.py AFTER 'fix' (UNCHANGED -- bug still present) ===")
print(calc.read_text())
print("=== acceptance check result ===")
print("ok:", result.ok, "reason:", result.reason)

# Independently confirm the underlying bug is untouched.
import importlib.util

spec = importlib.util.spec_from_file_location("calc", calc)
calc_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calc_mod)
real_answer = calc_mod.add(2, 3)

print(f"calc.add(2, 3) == {real_answer}  (correct answer is 5)")
assert result.ok is True, "expected the tampered test to make cmd_check report PASS"
assert real_answer != 5, "expected the underlying bug to still be present"
print(
    ">>> PROVEN: cmd_check reported PASS while the actual requested behavior "
    "(add(2,3) == 5) remains broken. The milestone would freeze DONE. Nothing in "
    "the acceptance/engine/adapter layers detects or prevents the executor "
    "editing the test file itself instead of the source file the milestone was "
    "about -- the executor has full write access to the whole working tree for "
    "any 'reversible' milestone (the default), and cmd_check is exit-code-only."
)
