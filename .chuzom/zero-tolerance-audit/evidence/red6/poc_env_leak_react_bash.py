"""RED-6 PoC (sandboxed, synthetic secret only): does the tier-0 ReAct agent's
`bash` tool executor leak the full parent process environment (incl. provider
API keys) to a model-controlled shell command, and is `env`/`printenv` blocked
by the sandbox denylist?

Safety: no real credentials used. A synthetic fake value is injected into
os.environ under a realistic secret-like variable name and we assert only
that the executor's stdout CONTAINS it (proves the leak) without printing
any real secret material anywhere.
"""
import os
import sys

sys.path.insert(0, "/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882/src")

FAKE_MARKER = "sk-ant-FAKE-REDTEAM-MARKER-1234567890abcdef"
os.environ["ANTHROPIC_API_KEY"] = FAKE_MARKER          # synthetic, not a real key
os.environ["OPENAI_API_KEY"] = "sk-FAKE-OPENAI-0000000000000000"
os.environ["GH_PAT"] = "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE0000"

from chuzom.agentic.react import default_tool_executor, _bash_block_reason  # noqa: E402

workdir = "/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/sandbox-home"
os.makedirs(workdir, exist_ok=True)
executor = default_tool_executor(cwd=workdir)

print("=== _bash_block_reason('env') ===", _bash_block_reason("env"))
print("=== _bash_block_reason('printenv') ===", _bash_block_reason("printenv"))
print("=== _bash_block_reason('env | grep API') ===", _bash_block_reason("env | grep API"))

result = executor("bash", {"command": "env"})
leaked_anthropic = FAKE_MARKER in result
leaked_openai = "sk-FAKE-OPENAI" in result
leaked_ghpat = "ghp_FAKEFAKE" in result

print("=== RESULT LENGTH ===", len(result))
print("=== ANTHROPIC_API_KEY (fake) present in bash('env') output ===", leaked_anthropic)
print("=== OPENAI_API_KEY (fake) present in bash('env') output ===", leaked_openai)
print("=== GH_PAT (fake) present in bash('env') output ===", leaked_ghpat)

# also test the CodexAdapter/adapters.py subprocess_runner path
from chuzom.agentic.adapters import subprocess_runner  # noqa: E402
proc = subprocess_runner(["/bin/sh", "-c", "env"], "", cwd=workdir)
print("=== adapters.subprocess_runner('env') leaks fake ANTHROPIC key ===",
      FAKE_MARKER in proc.stdout)

# compare: does the codebase's OWN safe_subprocess wrapper strip it, proving the
# gap is a code-path omission and not "impossible to fix"?
from chuzom.safe_subprocess import safe_subprocess_run  # noqa: E402
safe_proc = safe_subprocess_run("/bin/sh", "-c", "env", cwd=workdir, capture_output=True, text=True)
print("=== safe_subprocess_run('env') leaks fake ANTHROPIC key (should be False) ===",
      FAKE_MARKER in safe_proc.stdout)
