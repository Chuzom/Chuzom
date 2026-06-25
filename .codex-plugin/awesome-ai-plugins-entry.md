# awesome-ai-plugins submission (issue #103)

Chuzom ships a Codex plugin manifest (`.codex-plugin/plugin.json`) and is an MCP
server, so it qualifies for the curated list. Listed projects also surface in HOL's
plugin directory: https://hol.org/registry/plugins

## Target repository

- **List:** https://github.com/hashgraph-online/awesome-ai-plugins
  ("plugins for AI assistants including Claude Code, OpenAI Codex, Gemini, OpenCode…")
- **Sibling (Codex marketplace → hol.org/registry/plugins):**
  https://github.com/hashgraph-online/awesome-codex-plugins

## Ready-to-submit entry

Format (from that repo's `CONTRIBUTING.md`): `- [Name](url) - Description (max 1 sentence).`
Category: **Codex plugins** (alternatively **MCP servers**).

```markdown
- [Chuzom](https://github.com/Chuzom/Chuzom) - Routes every Codex/Claude task to the cheapest capable model across 20+ providers (Gemini Flash, Haiku, Ollama, Perplexity…), tracking cross-session savings and enforcing routing policy.
```

## Submission steps (per their CONTRIBUTING.md)

1. Fork `hashgraph-online/awesome-ai-plugins`; search existing entries to avoid dupes.
2. Add the line above under the **Codex plugins** (or **MCP servers**) section of `README.md`.
3. Validate: `pipx run plugin-scanner lint .` and `pipx run plugin-scanner verify .`
   — must score ≥ 80/142 with no critical/high findings.
4. Open a PR with: description, repo link, target category, and the scanner verification evidence.

## Note

The PR is to an **external** repository and needs a GitHub account + a fork — it can't be
opened from this workspace. This file makes the submission a copy-paste away.
