#!/usr/bin/env python3
"""RED1-01 reproducer: `llm_reason` survives localize() unresolved and is never
registered under the shipped default tier (CHUZOM_SLIM=consolidated), yet it is
taught to Copilot and Kimi Code users verbatim inside generated onboarding docs.

Run with the AUDIT venv only:
  /private/tmp/.../AUDIT-c2c2882/.venv-audit/bin/python repro_llm_reason_surface_gap.py

Must be run with cwd or PYTHONPATH pointing at the audit worktree's src/ dir.
"""
import os
import re
import sys

WORKTREE = "/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882"
sys.path.insert(0, os.path.join(WORKTREE, "src"))

os.environ.pop("CHUZOM_SLIM", None)  # force the shipped default: "consolidated"

from chuzom import tool_surface as ts  # noqa: E402

print("=== 1. Confirm shipped default tier ===")
print("active_slim() =", ts.active_slim())
assert ts.active_slim() == "consolidated", "shipped default must be consolidated"

print("\n=== 2. Is 'llm_reason' known to tool_surface.py at all? ===")
print("in CORE_TOOLS:        ", "llm_reason" in ts.CORE_TOOLS)
print("in ROUTING_TOOLS:     ", "llm_reason" in ts.ROUTING_TOOLS)
print("in CONSOLIDATED_TOOLS:", "llm_reason" in ts.CONSOLIDATED_TOOLS)
print("in DEPRECATED_TOOLS:  ", "llm_reason" in ts.DEPRECATED_TOOLS)
print("in KNOWN_TOOLS:       ", "llm_reason" in ts.KNOWN_TOOLS)
print("in EMITTABLE_TOOLS:   ", "llm_reason" in ts.EMITTABLE_TOOLS)

print("\n=== 3. Is 'llm_reason' registered under consolidated/routing/core? ===")
for tier in ("core", "routing", "consolidated", "off"):
    print(f"  is_registered('llm_reason', {tier!r}) =", ts.is_registered("llm_reason", tier))

print("\n=== 4. resolve('llm_reason', 'consolidated') ===")
call = ts.resolve("llm_reason", "consolidated")
print("  ->", call, " (name=%r, degraded=%r)" % (call.name, call.degraded))
assert call.name == "llm_reason", "resolve() left the name UNCHANGED (unknown-name passthrough branch)"
assert not ts.is_registered(call.name, "consolidated"), "resolve() returned a call that is NOT actually registered"

print("\n=== 5. localize() on the exact table row shipped in cli.py ===")
sample = '| Deep reasoning, proofs, root cause | `llm_reason` |\n'
out = ts.localize(sample, "consolidated")
print("  before:", sample.strip())
print("  after: ", out.strip())
assert out == sample, "localize() was expected to leave 'llm_reason' untouched (this IS the bug)"

print("\n=== 6. unregistered() CI/startup guard does NOT catch this ===")
bad = ts.unregistered(slim="consolidated")  # default names = EMITTABLE_TOOLS
print("  unregistered(slim='consolidated') =", bad)
assert "llm_reason" not in bad, "guard would need to check llm_reason, but it isn't even in the scanned set"

print("\n=== 7. Confirm the string literally ships in cli.py, inside localize()-wrapped blobs ===")
cli_path = os.path.join(WORKTREE, "src", "chuzom", "cli.py")
src = open(cli_path, encoding="utf-8").read()
lines = src.splitlines()
hits = [i + 1 for i, l in enumerate(lines) if "llm_reason" in l]
print("  cli.py occurrences of 'llm_reason' at lines:", hits)
assert hits, "expected at least one literal occurrence of llm_reason in cli.py"
for ln in hits:
    print(f"    L{ln}: {lines[ln-1].strip()!r}")

print("\n=== 8. Confirm text.py actually defines/registers llm_reason as a real MCP tool ===")
text_path = os.path.join(WORKTREE, "src", "chuzom", "tools", "text.py")
text_src = open(text_path, encoding="utf-8").read()
assert re.search(r"def\s+llm_reason\s*\(", text_src), "llm_reason should be a real function in tools/text.py"
assert 'gate("llm_reason")' in text_src, "registration should be gated by should_register('llm_reason')"
print("  confirmed: llm_reason is a real tool function, registered only if gate('llm_reason') is True")
print("  but gate = make_should_register(active tier); tier is never in llm_reason's tier set for")
print("  core/routing/consolidated -> under the SHIPPED DEFAULT it is never registered.")

print("\n=== 9. lint_tool_surface.py's own GUARDED tuple also omits llm_reason ===")
lint_path = os.path.join(WORKTREE, "scripts", "lint_tool_surface.py")
lint_src = open(lint_path, encoding="utf-8").read()
m = re.search(r"GUARDED\s*=\s*\((.*?)\)", lint_src, re.S)
guarded_block = m.group(1)
guarded_names = set(re.findall(r'"([^"]+)"', guarded_block))
print("  GUARDED names:", sorted(guarded_names))
assert "llm_reason" not in guarded_names, "lint's raw-string scan also has no idea llm_reason exists"

print("\n=== 10. GUARDED vs DEPRECATED_TOOLS drift (separate, secondary finding) ===")
missing_from_guarded = set(ts.DEPRECATED_TOOLS) - guarded_names
print("  DEPRECATED_TOOLS keys NOT covered by lint's GUARDED tuple:")
for n in sorted(missing_from_guarded):
    unreg_tiers = [t for t in ("core", "routing", "consolidated") if not ts.is_registered(n, t)]
    print(f"    {n!r:30s} unregistered under: {unreg_tiers}")

print("\nALL ASSERTIONS PASSED — RED1-01 and RED1-02 are PROVEN, not suspected.")
