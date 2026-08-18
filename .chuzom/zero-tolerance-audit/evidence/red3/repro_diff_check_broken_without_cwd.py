"""RED3 reproduction: the production default adapter factory
(chuzom/tools/agentic.py::_default_adapters, called by llm_delegate() with no
overrides) constructs `CodexAdapter(tier=1)` with NO `cwd=` argument:

    def _default_adapters() -> dict[int, Any]:
        from chuzom.agentic.react import ReActAgent
        return {0: ReActAgent(tier=0), 1: CodexAdapter(tier=1)}

CodexAdapter.run() only captures `diff`/`files` artifacts `if self.capture_diff
and self.cwd:` (adapters.py L127). With cwd=None that condition is always
False, so `diff` and `files` are unconditionally "" and [] for EVERY delegated
run through the shipped default wiring -- regardless of what the underlying
`codex` CLI actually did on disk.

Consequence: `diff_check` -- the acceptance type in the planner's own prompt
template that is supposed to verify "produced files/symbols present" by
inspecting the actual diff -- can NEVER pass in the default production path.
Every milestone plan that uses it is unconditionally, silently unsatisfiable.

This is proven WITHOUT touching a live `codex` binary: we inject a fake
`runner` (exactly the sanctioned test seam adapters.py documents) that
simulates codex reporting a real, successful git diff -- and show the
resulting artifacts are still empty because `self.cwd` is None.

Run with: <WORKTREE>/.venv-audit/bin/python repro_diff_check_broken_without_cwd.py
"""
import sys

sys.path.insert(0, "src")

from chuzom.agentic.adapters import CodexAdapter, ProcResult
from chuzom.agentic.ledger import Milestone
from chuzom.agentic.acceptance import canary_check


def fake_runner(argv, input_text):
    """Simulate: codex ran successfully AND made a real change on disk, and a
    `git diff HEAD` would show it -- IF the adapter ever asked in the right
    directory. We never even get asked, because `cwd` is None (see below)."""
    if argv[0].endswith("codex") or "codex" in argv[0]:
        return ProcResult(0, stdout="Applied patch to auth.py successfully.", stderr="")
    if "git" in argv[0] or (len(argv) > 1 and argv[1] == "-C"):
        # Simulates a real, non-empty diff that DOES exist on disk.
        return ProcResult(
            0,
            stdout="diff --git a/auth.py b/auth.py\n+++ b/auth.py\n+def real_fix(): ...\n",
            stderr="",
        )
    return ProcResult(1, "", "unexpected command")


# This is EXACTLY what chuzom.tools.agentic._default_adapters() constructs in
# production (no cwd= override anywhere in that call chain -- verified by grep):
#   return {0: ReActAgent(tier=0), 1: CodexAdapter(tier=1)}
adapter = CodexAdapter(tier=1, runner=fake_runner)  # cwd left at its default: None

milestone = Milestone(
    id="fix-auth",
    description="fix the auth bug",
    acceptance=canary_check("noop", field="output"),  # unused; we inspect artifacts directly
)

result = adapter.run(milestone, frozen_context=[], budget_left=1.0)

print("adapter.cwd:", adapter.cwd)
print("artifacts['diff']  :", repr(result.artifacts["diff"]))
print("artifacts['files'] :", repr(result.artifacts["files"]))
print("artifacts['output']:", repr(result.artifacts["output"]))

assert adapter.cwd is None
assert result.artifacts["diff"] == ""
assert result.artifacts["files"] == []
print()
print(
    ">>> PROVEN: with the production default wiring, artifacts['diff'] and "
    "artifacts['files'] are ALWAYS empty regardless of what codex actually did "
    "on disk, because CodexAdapter.run() only shells out to `git diff` "
    "`if self.capture_diff and self.cwd:` and cwd is never set anywhere in the "
    "llm_delegate() call chain. Any milestone plan using {'type':'diff',...} "
    "acceptance -- documented in the planner's own prompt template as a valid, "
    "objective check type -- is UNCONDITIONALLY UNSATISFIABLE in production. "
    "This silently forces all real delegated work through canary/cmd checks "
    "only, and (separately) means nothing pins the executor's actual working "
    "directory to the user's repository at all -- it inherits whatever cwd the "
    "MCP server process happens to have."
)
