# Chuzom Automatic Routing Gateway Plan

Date: 2026-07-03

## Objective

Make Chuzom automatic by default where the host technically allows it.

The product rule is:

```text
Gateway-capable hosts -> gateway mode
Hook-capable hosts    -> hooks mode
MCP-only hosts        -> companion mode
Rules-only hosts      -> best-effort mode
No integration point  -> unsupported or wrapper-only
```

MCP remains useful for status, reporting, diagnostics, and manual routing. It
must not be the primary mechanism for "automatic" routing because the host model
has to choose to call an MCP tool.

## Existing Implementation Inventory

The scan found substantial existing work that should be reused.

| Area | Existing code | Current state | Reuse decision |
|---|---|---|---|
| Multi-protocol gateway | `src/chuzom/gateway.py` | Already exposes `/v1/chat/completions`, `/v1/messages`, `/api/chat`, `/api/generate`, `/route`, `/v1/models` | Reuse and harden |
| Gateway routing core | `src/chuzom/route_server.py::route_payload` | Shared by gateway and zero-dep route server; calls `router.route_and_call` | Reuse as single routing core |
| Gateway service files | `src/chuzom/gateway_service.py` | Renders launchd/systemd service files; does not activate service | Reuse from installer |
| Gateway presets | `src/chuzom/presets.py` | Default gateway is `http://127.0.0.1:17900/v1`; env overrides exist | Reuse; align install output |
| CLI gateway command | `src/chuzom/cli.py` | `chuzom gateway` starts the FastAPI gateway | Reuse; add discoverable scripts if needed |
| Local platform discovery | `src/chuzom/local_platforms.py` | Detects Ollama, LM Studio, Jan, vLLM, llama.cpp, LocalAI, MLX, etc. | Reuse; feed install policy |
| Dynamic model discovery | `src/chuzom/discover.py` | Discovers Ollama and provider availability; cloud scanner stubs remain | Extend rather than replace |
| Chain building | `src/chuzom/chain_builder.py` | Scores available models and keeps local/free before paid | Reuse |
| Subscription/local policy | `src/chuzom/subscription_local_routing.py` | Handles free bucket vs subscription provider ordering | Reuse |
| Codex install | `src/chuzom/commands/install.py::_install_codex_files` | Installs MCP + rules + PostToolUse hook; still pull-routing | Upgrade to gateway mode |
| Cursor install | `src/chuzom/commands/install.py::_install_cursor_files` | Installs MCP + rules only | Keep as companion/rules unless custom base URL is supported |
| Host install duplicate path | `src/chuzom/cli.py` | Older host install helpers still exist and are directly tested | Either delegate to `commands.install` or mirror behavior |
| Doctor | `src/chuzom/commands/doctor.py` | Checks Claude/VSC/Cursor config and general health; no live gateway host proof | Extend with host gateway checks |
| Tests | `tests/test_gateway_presets.py`, `tests/test_gateway_service.py`, `tests/test_gateway_metering.py`, install/doctor tests | Good coverage for gateway surface, service rendering, and install basics | Add host-gateway tests and live smoke |

## Integration Modes

| Mode | Automatic? | Trigger point | Best for | Notes |
|---|---:|---|---|---|
| `gateway` | Yes | Host sends model calls to Chuzom OpenAI-compatible endpoint | Codex, OpenCode, SDK apps, CI/headless | Preferred where custom base URL/provider config exists |
| `hooks` | Mostly yes | Host lifecycle hooks | Claude Code, claw-code, Gemini CLI where hooks exist | Keeps host agent UX while routing subcalls/prompt shortcuts |
| `companion` | No | Host may call MCP tools | Claude Desktop, MCP-only IDEs | Status/report/manual routing only |
| `rules` | Best effort | Instructions bias the host model | Cursor/Copilot if no gateway config | Not a guarantee |
| `unsupported` | No | None | Locked-down hosts | Wrapper only if host config can be influenced |

## Host Strategy

| Host | Preferred mode | Existing code | Target behavior |
|---|---|---|---|
| Codex | Gateway + MCP companion | MCP/rules/hook install exists | Configure Codex model provider to `chuzom`, model `auto`; keep MCP for reports |
| Claude Code | Hooks + MCP companion | Strong hook install exists | Keep hooks; do not force gateway unless explicitly requested |
| Cursor | Gateway if custom base URL can be configured, else companion/rules | MCP/rules install exists | Detect capability; be honest when automatic is unavailable |
| OpenCode | Gateway + MCP companion | MCP/rules install exists | Add gateway config if host supports OpenAI-compatible base URL |
| Pi | Capability-detected | Rules file exists; CLI helper exists in older path | Gateway if base URL exists, otherwise companion/rules |
| Custom SDK/CI | Gateway | Gateway exists | Print/export `OPENAI_BASE_URL=http://127.0.0.1:17900/v1` and `model=auto` |

## Task Table

| Seq | Task | Effort | Already exists | Tests to run/add | Live/sandbox verification |
|---:|---|---|---|---|---|
| 1 | Normalize gateway model aliases so `auto`, `chuzom-auto`, and empty model all mean automatic routing | S | `route_server.route_payload` already handles `chuzom-auto`/empty | Add gateway test for `model=auto`; run `tests/test_gateway_presets.py` | FastAPI TestClient call to `/v1/chat/completions` with fake router |
| 2 | Add `/v1/responses` support for Codex/OpenAI Responses wire format | M | Gateway already supports chat completions and shared route core | Add `tests/test_gateway_responses.py` | TestClient POST `/v1/responses` returns OpenAI-style response and records chosen model |
| 3 | Add gateway install mode parsing: `chuzom install --host codex --mode gateway` | M | `commands/install.py` host dispatch exists | Add install tests for mode parsing and Codex gateway config | Temp-home install writes expected config only |
| 4 | Update Codex installer to write Chuzom model provider in `~/.codex/config.toml` with backup/idempotency | M | Codex MCP/rules install exists; current config format known | Add `tests/test_codex_gateway_install.py` | Temp-home config round trip; no real `~/.codex` writes |
| 5 | Keep Codex MCP companion install alongside gateway provider | S | Existing MCP config install exists | Extend install tests to assert MCP remains present | Temp-home config contains provider and MCP server |
| 6 | Add `chuzom doctor --host codex` gateway proof checks | M | Doctor host framework exists for claude/vscode/cursor | Add doctor tests for gateway running/not running/config mismatch | Mock localhost gateway; assert "automatic routing: YES/NO" output |
| 7 | Add live gateway smoke command/helper used by doctor and installer | M | Gateway TestClient tests exist; no real host proof | Add unit test with fake `route_payload`; maybe CLI smoke test | Start gateway on sandbox port, POST `/v1/chat/completions`, assert routed response |
| 8 | Add host capability matrix command/data: `chuzom hosts` or internal helper first | M | Host snippets and rules exist; no unified matrix | Add tests for host capability classifications | CLI output in sandbox |
| 9 | Add first-install discovery writer for local models and generated default policy | L | `local_platforms.py`, `discover.py`, `routing.yaml` exist | Add tests with mocked local platforms/env keys | Temp-home writes `discovery.json`, `routing.yaml`, `host-capabilities.json` |
| 10 | Reconcile duplicate host install helpers in `cli.py` vs `commands/install.py` | M | Both paths exist; tests hit `cli.py` helpers | Update tests or delegate helpers | Existing install tests pass |
| 11 | Update docs/README language: gateway is automatic, MCP/rules are companion/best-effort | S | README currently claims Codex push/plugin in places | Documentation review/test not required | Manual grep for stale "Codex push" claims |
| 12 | End-to-end sandbox session: install Codex gateway into temp home, start gateway, send OpenAI-compatible request, inspect savings log | M | Pieces exist | Add scripted smoke where practical | Real local HTTP server on free port with fake backend |

## Initial Implementation Order

Start with the smallest end-to-end Codex gateway path:

1. Alias `model=auto` correctly.
2. Add `/v1/responses`.
3. Add Codex gateway install config in temp-home-safe code.
4. Add doctor/smoke proof.
5. Run a sandbox live gateway request.

This order proves the product claim early: host traffic can enter through the
gateway automatically and route through Chuzom without relying on MCP pull
behavior.

## Acceptance Criteria

Codex gateway install is done when a sandbox run can show:

```text
Automatic routing enabled: YES
Mode: gateway
Host: Codex
Gateway: http://127.0.0.1:<port>/v1
Model requested by host: auto
Selected backend: <provider>/<model>
Smoke test: passed
```

If a host cannot be automatic, installer and doctor must say why:

```text
Automatic routing enabled: NO
Mode: companion
Reason: host only supports MCP/rules; no model endpoint or hook found
```

