"""Independent repro resolving the RED3-02 (diff_check gameable) vs RED3-08
(diff_check structurally unusable / always-empty under default wiring) tension.

Three scenarios, ALL using a FAKE runner (no subprocess, no network, no cost,
no real Codex CLI call):

  A) CodexAdapter as constructed by tools/agentic.py::_default_adapters()
     (cwd=None, the literal production default) -- does diff_check ever see
     non-empty diff/files?
  B) CodexAdapter with an explicit cwd= (a realistic, SUPPORTED, but
     NON-default configuration a user could pass) with a runner that returns a
     git-diff-shaped stub containing a target symbol -- does diff_check's
     substring/membership match accept it as DONE?
  C) ReActAgent tier-0, the actual default tier-0 adapter from
     _default_adapters() -- does its artifacts dict even have diff/files keys?

Uses chuzom.agentic.acceptance.diff_check exactly as shipped -- no modified
copy, no trusting RED-3's own reproducer.
"""
import sys

WORKTREE = sys.argv[1] if len(sys.argv) > 1 else None
if WORKTREE:
    sys.path.insert(0, WORKTREE + "/src")

from chuzom.agentic.adapters import CodexAdapter, ProcResult
from chuzom.agentic.acceptance import diff_check
from chuzom.agentic.ledger import Milestone
from chuzom.agentic.react import ReActAgent

TARGET_SYMBOL = "def validate_password"

check = diff_check(files=["auth.py"], symbols=[TARGET_SYMBOL])

m = Milestone(
    id="fix-auth",
    description="Fix the password validation bug in auth.py",
    acceptance=check,
)

print("=" * 70)
print("SCENARIO A: CodexAdapter exactly as _default_adapters() builds it (cwd=None)")
print("=" * 70)


def fake_runner_A(argv, input_text):
    # Simulate codex CLI "succeeding" AND simulate that, if git diff were ever
    # invoked, it WOULD return a real diff containing the target symbol -- i.e.
    # give the adapter every chance to capture something.
    if argv[:1] == ["codex"] or (argv and "codex" in argv[0]):
        return ProcResult(0, stdout="codex claims success", stderr="")
    if argv[:2] == ["git", "-C"]:
        return ProcResult(0, stdout=f"+++ b/auth.py\n+{TARGET_SYMBOL}(pw): return True\n", stderr="")
    return ProcResult(1, "", "unexpected call")


default_adapter = CodexAdapter(tier=1, runner=fake_runner_A)  # cwd left at dataclass default: None
run = default_adapter.run(m, [], budget_left=1.0)
print("artifacts.diff  :", repr(run.artifacts["diff"]))
print("artifacts.files :", repr(run.artifacts["files"]))
result = check(run.artifacts)
print("diff_check(...).ok :", result.ok, "--", result.reason)
print("-> capture_diff branch requires `self.cwd` truthy; cwd=None means git diff")
print("   is NEVER invoked by the adapter, regardless of what the runner would")
print("   have returned. diff/files are unconditionally '' / [] here.")
print()

print("=" * 70)
print("SCENARIO B: CodexAdapter with an explicit cwd= (realistic non-default config)")
print("=" * 70)


def fake_runner_B(argv, input_text):
    if argv and ("codex" in argv[0]):
        return ProcResult(0, stdout="codex claims success", stderr="")
    if argv[:2] == ["git", "-C"]:
        # Fabricated stub: a symbol-substring match with NO real fix -- classic
        # "return True" security hole, but it satisfies diff_check() because
        # diff_check only checks substring/membership, never semantics.
        stub_diff = f"+++ b/auth.py\n+{TARGET_SYMBOL}(pw):\n+    return True  # TODO: real check\n"
        return ProcResult(0, stdout=stub_diff, stderr="")
    return ProcResult(1, "", "unexpected call")


configured_adapter = CodexAdapter(tier=1, runner=fake_runner_B, cwd="/some/real/repo")
run_b = configured_adapter.run(m, [], budget_left=1.0)
print("artifacts.diff  :", repr(run_b.artifacts["diff"]))
print("artifacts.files :", repr(run_b.artifacts["files"]))
result_b = check(run_b.artifacts)
print("diff_check(...).ok :", result_b.ok, "--", result_b.reason)
print("-> CONFIRMED: the moment diff/files are non-empty (any adapter/config that")
print("   populates them), diff_check's substring match accepts a security-hole")
print("   stub as satisfying the milestone. This is a real, independently")
print("   reproduced defect in diff_check() ITSELF -- not dependent on RED-3's")
print("   own FakeStubbingAgent.")
print()

print("=" * 70)
print("SCENARIO C: ReActAgent tier-0, the actual default tier-0 adapter")
print("=" * 70)
react = ReActAgent(tier=0)
print("Does ReActAgent.run()'s artifacts dict ever contain 'diff' or 'files' keys?")
import inspect
src = inspect.getsource(ReActAgent.run)
has_diff_key = ('"diff"' in src or "'diff'" in src)
has_files_key = ('"files"' in src or "'files'" in src)
print("  'diff' key present in artifacts construction:", has_diff_key)
print("  'files' key present in artifacts construction:", has_files_key)
print("-> If False/False: diff_check(files=[...]) against ReActAgent's artifacts")
print("   ALSO always fails (produced files always empty set), for a completely")
print("   different structural reason (missing keys, not cwd-gating).")
