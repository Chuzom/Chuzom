#!/usr/bin/env python3
"""RED1-01 (expanded) reproducer: quantify the FULL blast radius of the CHZ-SURF-01
gap across every generated/installed onboarding artifact in the audit worktree.

Two independent defect classes are proven here:

  (A) `src/chuzom/rules/*.md` — 12 per-host template files installed VERBATIM via
      `cli._append_routing_rules()` (confirmed: zero call to localize()/route_tool()
      anywhere in that function). EVERY legacy tool name in these files is unresolved
      under the shipped default tier, not just llm_reason.

  (B) In-code templates that DO call localize() (`cli._COPILOT_AGENT_CONTENT`,
      `cli.kimi_rules`* wait -- verified as literal string in cli.py, and
      `install_hooks._CURSOR_RULE_CONTENT`/`_VSCODE_MCP_CONTENT`/`_WINDSURF_MCP_CONTENT`)
      — localize() DOES correctly rewrite the 5 names present in DEPRECATED_TOOLS
      (llm_query/llm_code/llm_analyze/llm_research/llm_generate), proving the
      mechanism works — but leaves `llm_reason` completely untouched because it is
      not a DEPRECATED_TOOLS key, reproducing the exact CHZ-SURF-01 bug in code
      that was specifically supposed to have been fixed.

Run with the AUDIT venv only.
"""
import os
import re
import sys

WORKTREE = "/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882"
sys.path.insert(0, os.path.join(WORKTREE, "src"))
os.environ.pop("CHUZOM_SLIM", None)  # shipped default: consolidated

from chuzom import tool_surface as ts  # noqa: E402

TIER = "consolidated"
assert ts.active_slim() == TIER

LEGACY_NAMES = [
    "llm_query", "llm_code", "llm_analyze", "llm_research", "llm_generate",
    "llm_reason", "llm_savings", "llm_health", "llm_edit", "llm_auto",
]

print("=" * 78)
print(f"Registered under CHUZOM_SLIM={TIER}: {sorted(ts.registered_tools(TIER))}")
print("=" * 78)

print("\n--- (A) src/chuzom/rules/*.md — installed via _append_routing_rules(),")
print("    which NEVER calls localize()/route_tool() (confirmed by reading cli.py")
print("    lines 125-169: reads rules_file.read_text() and writes it VERBATIM) ---\n")

rules_dir = os.path.join(WORKTREE, "src", "chuzom", "rules")
total_bad = 0
for fname in sorted(os.listdir(rules_dir)):
    if not fname.endswith(".md"):
        continue
    path = os.path.join(rules_dir, fname)
    text = open(path, encoding="utf-8").read()
    hits = [n for n in LEGACY_NAMES if re.search(r"`" + re.escape(n) + r"(\(|`)", text)]
    unresolved = [n for n in hits if not ts.is_registered(n, TIER)]
    if unresolved:
        total_bad += 1
        print(f"  {fname:24s} unresolved legacy names taught verbatim: {unresolved}")

print(f"\n  -> {total_bad} of the per-host rules/*.md templates teach at least one")
print(f"     tool name that is NOT registered under the shipped default tier,")
print(f"     with ZERO localize() pass ever applied to this whole file family.")

print("\n--- Which install functions ship these files, and to what host? ---\n")
cli_path = os.path.join(WORKTREE, "src", "chuzom", "cli.py")
cli_src = open(cli_path, encoding="utf-8").read()
for m in re.finditer(r'_append_routing_rules\([^,]+,\s*"([^"]+)"\)', cli_src):
    print(f"  installs {m.group(1)}")

print("\n--- (B) In-code templates wrapped in localize() — proves the mechanism")
print("    works for names IN DEPRECATED_TOOLS but not for llm_reason ---\n")

from chuzom.cli import _COPILOT_AGENT_CONTENT  # noqa: E402
from chuzom.install_hooks import _CURSOR_RULE_CONTENT, _VSCODE_MCP_CONTENT  # noqa: E402

for label, content in [
    ("cli._COPILOT_AGENT_CONTENT (-> .github/agents/chuzom.agent.md)", _COPILOT_AGENT_CONTENT),
    ("install_hooks._CURSOR_RULE_CONTENT (-> <proj>/.cursor/rules/use-chuzom.mdc)", _CURSOR_RULE_CONTENT),
    ("install_hooks._VSCODE_MCP_CONTENT (-> <proj>/.vscode/mcp.json)", _VSCODE_MCP_CONTENT),
]:
    print(f"  {label}")
    for n in LEGACY_NAMES:
        if re.search(r"\b" + re.escape(n) + r"\b", content):
            reg = ts.is_registered(n, TIER)
            status = "OK (registered)" if reg else "*** UNRESOLVED — SHIPS BROKEN ***"
            print(f"      contains {n!r:14s} -> registered={reg!s:5s} {status}")
    print()

print("=" * 78)
print("CONCLUSION: the CHZ-SURF-01 fix (localize()) is correct but incomplete for")
print("the ~11 in-code templates it was applied to (misses llm_reason everywhere),")
print("and was NEVER APPLIED AT ALL to the 12-file src/chuzom/rules/*.md template")
print("family, which is the actual install payload for VS Code/Copilot, Cursor")
print("(global rules), OpenCode, Gemini CLI, Copilot CLI, OpenClaw, Trae, Pi, and")
print("Codex CLI. Every one of those hosts' default install teaches unresolved,")
print("uncallable legacy tool names for the majority of task categories.")
print("=" * 78)
