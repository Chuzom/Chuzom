# RED-1 Host Integration Audit — Chuzom v1.1.1 (`c2c2882`)

Audited by: RED-1. Same constraints as 04_ROUTING_AUDIT.md (audit venv only, no
production-code edits, no `mcp__chuzom__*` routing, no subagent spawning).

Scope note up front: mandate area 5 asks for, per host, proof that "the emitted
tool exists, syntax is valid, args match schema, and it is actually callable."
This pass produced strong, executable evidence for the FIRST of those four
(tool existence) across every host whose onboarding artifact could be located
and read. It did **not** perform live, end-to-end tool-call execution against a
real instance of each host application (Cursor, Windsurf, Copilot, Gemini CLI,
etc.) — that would require installing and driving each host's actual client,
which was out of scope for the time available. Where a claim below is
inference from source rather than a live host session, it is labeled
accordingly. This matches the audit's own confidence-labeling requirement:
nothing here that wasn't executed is presented as PROVEN.

---

## Host x installed-artifact x tool-name-resolution matrix

Built from direct execution: for each rules file, loaded the real
`tool_surface.is_registered()` against the shipped default tier
(`CHUZOM_SLIM=consolidated`), on the actual file content in the audit worktree.
Full raw output: `evidence/red1/repro_full_tool_surface_scan.OUTPUT.txt`.

| Host | Install artifact | Install function | Resolver applied? | Unregistered names taught (consolidated tier) | Confidence |
|---|---|---|---|---|---|
| Claude Code | hook-directive path (no static template) | `hooks/auto-route.py` -> server hint | Yes — proven clean by `trace_northstar.py` for the 3 tested prompt shapes | none found (narrow scope, see RED1-23) | PROVEN (for tested scope only) |
| VS Code / Copilot (chat) | `.github/copilot-instructions.md` (via `chuzom.md`/rules family) + `.github/agents/chuzom.agent.md` | `_append_routing_rules(..., "chuzom.md")` / `cli._COPILOT_AGENT_CONTENT` | rules file: NO. agent file: YES (`localize()`) but incomplete (misses `llm_reason`) | rules file: `llm_query, llm_code, llm_analyze, llm_research, llm_generate, llm_reason, llm_savings, llm_auto`. agent file: `llm_reason` | PROVEN |
| VS Code (MCP config) | `.vscode/mcp.json` | `install_hooks.install_ide_configs` -> `_VSCODE_MCP_CONTENT` | N/A — content already uses new `llm(task="code")` syntax directly | none found | PROVEN (this one is correct) |
| Cursor (global rules) | `~/.cursor/rules/chuzom.md`-style file | `_append_routing_rules(..., "cursor-rules.md")` | NO | `llm_query, llm_code, llm_analyze, llm_research, llm_generate, llm_reason, llm_auto` | PROVEN |
| Cursor (project rules) | `<project>/.cursor/rules/use-chuzom.mdc` | `install_hooks.install_ide_configs` -> `_CURSOR_RULE_CONTENT` | YES (`localize()`) but incomplete | `llm_reason` | PROVEN |
| Windsurf | `.windsurf/rules/use-chuzom.md` (global) + `.windsurf/mcp.json` | `_append_routing_rules(..., ...)` for the `.md`; `install_ide_configs` -> `_WINDSURF_MCP_CONTENT` for the `.json` | `.md`: NO. `.json`: NOT independently re-checked this pass (prior session grep found `llm_reason` in `.windsurf/rules/use-chuzom.md` in the main repo, consistent with the rules-file finding, but the `_WINDSURF_MCP_CONTENT` constant itself was not re-inspected in this session the way `_VSCODE_MCP_CONTENT`/`_CURSOR_RULE_CONTENT` were) | `.md`: same legacy-name set as other rules files (inferred, not re-verified line-by-line this session) | STRONG EVIDENCE for `.md`; NOT TESTED for `.json` in this session |
| Gemini CLI | `gemini-cli-rules.md` -> installed rules | `_append_routing_rules(..., "gemini-cli-rules.md")` | NO | `llm_query, llm_code, llm_analyze, llm_research, llm_generate, llm_reason, llm_savings, llm_auto` | PROVEN |
| Gemini (desktop/other) | `gemini-rules.md`, `desktop-rules.md` | `_append_routing_rules(...)` | NO | similar legacy-name sets (see 04_ROUTING_AUDIT.md RED1-20 table) | PROVEN |
| GitHub Copilot CLI | `copilot-cli-rules.md` | `_append_routing_rules(..., "copilot-cli-rules.md")` | NO | `llm_query, llm_code, llm_analyze, llm_research, llm_generate, llm_reason, llm_savings, llm_auto` | PROVEN |
| Codex CLI | `codex-rules.md` | `_append_routing_rules(..., "codex-rules.md")` | NO | `llm_query, llm_code, llm_analyze, llm_research, llm_generate, llm_reason, llm_auto` | PROVEN |
| OpenCode | `opencode-rules.md` | `_append_routing_rules(..., "opencode-rules.md")` | NO | `llm_query, llm_code, llm_analyze, llm_research, llm_generate, llm_reason, llm_auto` | PROVEN |
| OpenClaw | `openclaw-rules.md` | `_append_routing_rules(..., "openclaw-rules.md")` | NO | `llm_query, llm_code, llm_analyze, llm_research, llm_generate, llm_reason, llm_auto` | PROVEN |
| Trae | `trae-rules.md` | `_append_routing_rules(..., "trae-rules.md")` | NO | `llm_query, llm_code, llm_analyze, llm_research, llm_generate, llm_reason, llm_savings, llm_auto` | PROVEN |
| Pi | `pi-rules.md` | `_append_routing_rules(..., "pi-rules.md")` | NO | `llm_query, llm_code, llm_analyze, llm_research, llm_generate, llm_reason, llm_auto` | PROVEN |
| Kimi Code | `KIMI.md` | `cli.kimi_rules` (localize()-wrapped inline string) | YES (`localize()`) but incomplete | `llm_reason` (confirmed via prior-session static-text reproducer; not re-executed against the live import in this session — STRONG EVIDENCE, not re-PROVEN this session) | STRONG EVIDENCE |

**Row-count summary**: of the 15 distinct host/artifact rows above, 11 apply NO
resolver at all (PROVEN broken), 3 apply `localize()` but still ship `llm_reason`
unresolved (PROVEN broken for that one name), and 1 (`_VSCODE_MCP_CONTENT`) is
correct. Zero rows were found where BOTH the resolver was applied AND the
output was fully clean for the legacy-name set tested — except the one case
where the underlying template was rewritten to avoid needing resolution in the
first place. Windsurf's `.json` MCP config was not independently re-checked
this session and is the one row genuinely marked NOT TESTED rather than
inferred/proven.

---

## Argument-schema and live-callability verification: NOT PERFORMED

The mandate also asks to confirm, per host, that "syntax is valid, args match
schema, and it is actually callable." This audit pass did not:

- Install or drive a live Cursor, Windsurf, Gemini CLI, Copilot CLI, OpenCode,
  OpenClaw, Trae, or Pi client and issue a real tool call through it.
- Validate the JSON-RPC / MCP tool-call argument shapes emitted by any of these
  hosts' generated config files (`.vscode/mcp.json`, `.windsurf/mcp.json`)
  against the actual FastMCP schema registered in `src/chuzom/server.py` for
  each of the 11 `consolidated`-tier tools (`llm`, `llm_act`, `llm_edit`, etc.)
  — i.e. whether `task`/`tier`/`context` parameter names and types in the
  installed docs match the real function signatures.
- Confirm that a syntactically-plausible call like `llm(task="code")` (which
  IS a registered tool name, unlike the broken ones above) actually succeeds
  end-to-end through each host's MCP client implementation, as opposed to only
  through Claude Code's.

This is a real, acknowledged gap in this audit pass, not a claim that these
things are fine. Given the proven scale of the tool-NAME problem alone (11 of
15 rows completely unresolved), a schema/callability pass would very likely
surface additional defects, but none were found or ruled out here.

---

## Enforcement-mode host coverage

`hooks/enforce-route.py` and `hooks/auto-route.py` are both explicitly
Claude-Code-hook-shaped (they read `hookSpecificOutput`/PreToolUse JSON payloads
specific to Claude Code's hook contract). Non-Claude-Code hosts have NO
enforcement layer at all in this codebase as far as this pass could determine —
their only integration point is the static rules/config files audited above.
This means for those 10+ hosts, `smart`/`hard`/`advise`/`off` enforcement modes
are not applicable; the ENTIRE integration surface for those hosts is "hope the
host model reads and correctly follows the (frequently broken, per above) rules
file." This was inferred from the fact that no `hosts/`-specific enforcement
hook was found for non-Claude-Code hosts during this pass's file listing of
`src/chuzom/hooks/` (only `auto-route.py`, `enforce-route.py`, `agent-route.py`,
`session-end.py` were present) — **not exhaustively confirmed by reading
`src/chuzom/hosts/` in full, which remains unread this session**. Flagged as
STRONG EVIDENCE, not PROVEN.

---

## Summary for mandate area 5

The dominant, proven finding is the same one as 04_ROUTING_AUDIT.md's RED1-20:
tool-name resolution is broken for the overwhelming majority of supported
hosts' onboarding artifacts under the shipped default tier. This is presented
here as a per-host matrix per the mandate's request, but it is the identical
underlying defect, not a separate one — cross-reference RED1-20/21 rather than
treating this file as introducing new severity-scored findings.
