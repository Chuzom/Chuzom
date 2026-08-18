"""Independent PoC extending RED6-02 to CodexAdapter (tier 1) — resolves RED-6's
own flagged 'untested item #1': does `agentic/adapters.py`'s `CodexAdapter`
have the same env-inheritance gap as `react.py`'s bash tool?

Exercises the REAL `subprocess_runner()` from `agentic/adapters.py` (the
function `CodexAdapter.run()` uses by default as `self.runner`) directly,
without going through the actual `codex` CLI binary (which isn't installed /
authenticated in this sandbox) — instead pointing argv at `/usr/bin/env` or
`/bin/sh -c env` to observe what environment the child process itself sees,
which is exactly what `subprocess_runner` would hand to the real `codex`
binary if it were present.

FAKE key only. No network calls. Must run under `<WORKTREE>/.venv-audit/bin/python`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/"
                    "b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882/src")

FAKE_KEY_VALUE = "sk-NOTREAL-000-FAKE-ADJUDICATOR-MARKER-CODEX"
os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY_VALUE

from chuzom.agentic.adapters import subprocess_runner  # noqa: E402

# subprocess_runner(argv, input_text, *, cwd=None, timeout=300.0) -> ProcResult
# Simulate what happens when CodexAdapter.run() invokes self.runner(argv, prompt):
# argv[0] would normally be the resolved `codex` binary path; here we substitute
# a harmless env-dumping command to observe the actual child environment,
# because that's the same subprocess.run(...) call site with no env= override.
result = subprocess_runner(["/bin/sh", "-c", "env"], "fake-prompt-input", timeout=10.0)

leaked = FAKE_KEY_VALUE in result.stdout
print("=== CodexAdapter's subprocess_runner(): env leak check ===")
print(f"returncode={result.returncode}")
print(f"FAKE_KEY_VALUE present in child stdout: {leaked}")
if leaked:
    for line in result.stdout.splitlines():
        if "ANTHROPIC_API_KEY" in line:
            print(f"  matching line (redacted): ANTHROPIC_API_KEY=<FAKE_KEY_REDACTED>")
assert leaked, "PoC FAILED: fake key not found in subprocess_runner's child env"
print("PoC RESULT: REPRODUCED — CodexAdapter's subprocess_runner also inherits the full "
      "parent environment (no env= kwarg at this call site either); resolves RED-6's "
      "untested item #1 in the AFFIRMATIVE (tier-1 escalation has the same gap).")
