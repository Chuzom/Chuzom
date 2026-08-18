"""Independent PoC for RED6-02 (adjudicator's OWN fixture, not RED-6's).

Claim under test: `agentic/react.py`'s `default_tool_executor()`'s `bash` tool
calls `subprocess.run(["/bin/sh", "-c", command], ...)` with NO `env=` kwarg,
so the child process inherits the FULL parent environment, including any API
keys. This test uses a FAKE, clearly-non-real credential value only.

Also probes `_bash_block_reason()` for bypass variants (env / printenv / set /
export -p / obfuscated forms) to attack the "defense-in-depth blocklist"
claim directly (attack axis #4).

Must be run under `<WORKTREE>/.venv-audit/bin/python`. No real network calls.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, "/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/"
                    "b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882/src")

FAKE_KEY_VALUE = "sk-NOTREAL-000-FAKE-ADJUDICATOR-MARKER"
os.environ["OPENAI_API_KEY"] = FAKE_KEY_VALUE  # realistic-shaped var name, FAKE value only

from chuzom.agentic.react import default_tool_executor, _bash_block_reason  # noqa: E402

# --- Part A: does the bash tool leak the (fake) env var? ---
with tempfile.TemporaryDirectory() as td:
    execute = default_tool_executor(cwd=td)
    result = execute("bash", {"command": "env"})

leaked = FAKE_KEY_VALUE in result
print("=== Part A: env leak via bash tool ===")
print(f"FAKE_KEY_VALUE present in `env` tool output: {leaked}")
if leaked:
    redacted = result.replace(FAKE_KEY_VALUE, "<FAKE_KEY_REDACTED>")
    # show only the matching line, redacted
    for line in redacted.splitlines():
        if "OPENAI_API_KEY" in line:
            print(f"  matching line (redacted): {line}")
assert leaked, "PoC FAILED to reproduce: fake env var not found in bash tool output"
print("PoC RESULT: REPRODUCED — full parent environment (incl. API-key-shaped vars) is inherited.")

# --- Part B: blocklist bypass probe against _bash_block_reason ---
print()
print("=== Part B: _bash_block_reason() bypass probe ===")
candidates = [
    "env",
    "printenv",
    "printenv OPENAI_API_KEY",
    "set",
    "export -p",
    "env | grep KEY",
    "cat /proc/self/environ",
    "python3 -c \"import os;print(os.environ)\"",
    "e''nv",              # trivial quoting obfuscation
    "$(echo env)",        # command substitution obfuscation
    "/usr/bin/env",       # absolute-path variant
]
for cmd in candidates:
    reason = _bash_block_reason(cmd)
    status = "BLOCKED" if reason else "ALLOWED"
    print(f"  {status:8s}  {cmd!r}  (reason={reason!r})")
