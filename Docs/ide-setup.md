# IDE Setup & Integration

Chuzom integrates with every major AI-assisted IDE. There are two fundamentally
different integration modes — **push** and **pull** — with different guarantees.

## Push routing — automatic, self-contained prompts (Claude Code)

Claude Code's `UserPromptSubmit` hook fires **before** the LLM sees your prompt.
When a prompt is **self-contained** (no need for your files, repo, or conversation
history), Chuzom routes it to the cheapest capable model and answers directly —
Claude never runs for that turn. Context-dependent turns stay with Claude, with
Chuzom's routing advice attached (no blind drafts, no fabricated context).

```
Self-contained turn  →  hook fires  →  Chuzom routes  →  cheap model answers
Context-dependent    →  hook fires  →  advisory only  →  Claude handles it
```

## Pull routing — model decides (Copilot, Cursor, Windsurf)

These IDEs expose Chuzom as a tool the **model can choose to call**. The model sees
your prompt, then (if rules/instructions say to) calls `llm_code` / `llm_query` /
`llm_analyze` and returns the result.

```
You type  →  LLM sees prompt  →  model calls llm_code  →  cheap model responds
                                        ↑
                              NOT guaranteed every turn
```

The `.cursor/rules/use-chuzom.mdc` rule that Chuzom installs nudges Cursor's agent
to call Chuzom tools first. In practice this fires ~90% of turns in agent mode, but
it is not a hard guarantee like the Claude Code hook.

## IDE support matrix

| Tool | Routing | Status | Setup |
|---|---|---|---|
| 🔵 Claude Code / Claude Desktop | **Push** (automatic) | ✅ Production | `chuzom-install-hooks` |
| 🟠 Codex CLI | **Push** (plugin) | ✅ Production | `chuzom-install-hooks` |
| 🟣 Cursor | **Pull** + rule nudge | ✅ Production | `chuzom-install-hooks ide` |
| 🟤 GitHub Copilot (VS Code) | **Pull** (agent mode) | ✅ Beta | `chuzom-install-hooks ide` |
| 🌊 Windsurf / Cascade | **Pull** (agent mode) | ✅ Beta | `chuzom-install-hooks ide` |
| 🔴 Gemini CLI | **Pull** (tool call) | ✅ Production | `chuzom-install-hooks` |
| 🌙 Kimi Code | **Pull** (MCP tools) | ✅ Beta | Manual MCP config |

> **Recommendation:** Use Claude Code for the most consistent routing on every turn
> (realized savings depend on your workload). Use Cursor/Copilot/Windsurf for
> pull-based routing in agent mode.

## Tool surface (0.10.0) — 11 front doors

Since 0.10.0 the default MCP surface is **11 consolidated front doors** instead of
~73 tools (fewer schema tokens → better routing in long sessions):

| Door | What it does |
|---|---|
| `llm` | text in → out; pick specialization with `task=` (query/analyze/code/research/generate) and cost with `tier=` (fast/balanced/best) |
| `llm_act` | agentic execution — decompose, run on the cheapest capable tier *with tools*, verify, escalate on failure |
| `chuzom_status` | savings / usage / spend / health / providers (`view=`) |
| `chuzom_admin` | profile / cache / policy / budget (`action=`) |
| `chuzom_session` | agent-session lifecycle (`action=`) |
| `llm_route`, `llm_image`, `llm_audio`, `llm_edit`, `chuzom_agent_start_session`, `chuzom_agent_route` | first-class doors |

**Prefer the old surface?** Set `CHUZOM_SLIM=off` in the MCP server env to expose all
legacy tools (`routing` / `core` tiers also remain). No behaviour is removed — the doors
dispatch to the same underlying functions.

## Copilot setup (VS Code ≥ 1.99)

```bash
# In your project root
chuzom-install-hooks ide

# This writes .vscode/mcp.json with the Chuzom MCP server config.
# Then in VS Code:
#   1. Enable Copilot Chat agent mode (VS Code ≥ 1.99 required)
#   2. Open Copilot Chat → switch to "Agent" mode
#   3. Chuzom tools appear automatically in the tool list
```

In Copilot agent mode, you can explicitly invoke Chuzom:

```
@workspace use llm_code to refactor this function
```

Or just work normally — the model will call `llm_code` when it's appropriate.

## Windsurf / Cascade setup

```bash
chuzom-install-hooks ide
# Writes .windsurf/mcp.json — Cascade picks it up automatically
```

## Cursor setup

```bash
chuzom-install-hooks ide
# Writes .cursor/rules/use-chuzom.mdc — instructs Cursor agent to call
# Chuzom tools before generating its own response
```

## Kimi Code setup

Kimi Code uses pull routing via MCP. Add the Chuzom MCP server in Kimi's settings:

```json
{
  "mcpServers": {
    "chuzom": {
      "command": "chuzom",
      "args": []
    }
  }
}
```

Then in Kimi Code, the model will call `llm_code`, `llm_query`, etc. See
[`KIMI.md`](../KIMI.md) for the full routing table.
