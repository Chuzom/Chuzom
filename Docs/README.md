# Chuzom Documentation

Start at the [project README](../README.md) for the overview and 60-second install.
This folder holds the reference guides linked from there.

## User guides

| Guide | What's in it |
|---|---|
| [ide-setup.md](ide-setup.md) | Per-IDE setup, push vs. pull routing, the 11-door MCP tool surface |
| [routing.md](routing.md) | Routing chains, subagent routing, the REASONING profile, policies, model pinning |
| [local-inference.md](local-inference.md) | 13+ auto-detected local LLM servers + port overrides |
| [configuration.md](configuration.md) | Full env-var matrix, enforcement modes, advanced config, CLI reference |
| [session-dashboard.md](session-dashboard.md) | Session summary dashboard panels + live streaming progress |
| [okf.md](okf.md) | Open Knowledge Format — the self-building local knowledge bundle |
| [agentic-router.md](agentic-router.md) | Milestone-Gated Escalating Execution (the `llm_act` agentic path) |
| [subagent-routing.md](subagent-routing.md) | Routing savings inside Claude Code's `Agent` tool |
| [troubleshooting.md](troubleshooting.md) | Command-not-found, hooks, Ollama, Windows setup |

## Release & audit

| Doc | What's in it |
|---|---|
| [correctness-reset/](correctness-reset/) | The v1.0.0 correctness audit: release gates, control-group benchmark, two-consecutive-audit runbook, mutation-equivalent registry |
| [../CHANGELOG.md](../CHANGELOG.md) | Version history |
| [../RELEASE.md](../RELEASE.md) | Release process |
| [../NORTH_STAR.md](../NORTH_STAR.md) | The routing North Star (capability = live leaderboard) |

## Internal & historical

[archive/](archive/) holds superseded planning documents and one-off analyses kept for
the historical record — not user-facing guidance. See [archive/README.md](archive/README.md).
