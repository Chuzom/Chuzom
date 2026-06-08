# Developer Rollout Assessment

**Question being answered.** Could a large engineering organisation deploy chuzom to all of its developers (Claude Code, Cursor, Codex CLI, Gemini CLI, GitHub Copilot integrations, internal coding agents, CI jobs), and would the rollout improve outcomes?

**Verdict:** **Not for broad rollout. Suitable for a controlled, opt-in pilot.** Mandatory deployment is not viable until central enforcement + reconciliation + quality measurement exist.

---

## 1. Developer onboarding

| Question | Evidence | Verdict |
|---|---|---|
| How does a developer install? | `pip install chuzom-router` + `chuzom-onboard` (interactive wizard at `src/chuzom/onboard.py`) + `chuzom-install-hooks` to wire Claude Code hooks. | Works for a self-driven dev. |
| Central configuration management | Configuration is per-instance `.env` + `~/.chuzom/profile.yaml`. No central server pushes config. `grep -rln "central_config\|policy_server\|control_plane" src/chuzom/` returns no application-code match. | **Missing.** Each developer maintains their own env. |
| Provider keys | Developer must supply their own provider keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) in env or `.env`. | **Incompatible with the "company credentials hidden from users" requirement.** |
| Authentication | None at the chuzom layer beyond `CHUZOM_USER_ID` env trust. No SSO/SCIM/OIDC. | **Missing.** |
| Per-user identity retained | Yes — `TurnIdentity.user_id` (`src/chuzom/identity.py:48`) is the env value or `getpass.getuser()`. | Local only. |
| Bypass-resistance | A developer with their own provider key can hit the provider directly with `curl` and ignore chuzom entirely. No proxy enforcement, no DNS pinning, no MITM. | **Bypass is trivial.** |
| Configuration drift detection | `chuzom doctor` is local; no central config-drift reporter. | **Missing for fleet operations.** |
| Cross-OS support | Designed for macOS / Linux. `pyproject.toml` declares 3.10+ generic. Windows not explicitly excluded but install scripts use POSIX paths in many places. | Plausible, not validated at scale. |
| Cert / proxy / VPN scenarios | LiteLLM is the HTTP layer; cert / proxy passthrough inherits from LiteLLM. No documentation of corporate-CA / NTLM-proxy support. | **Not validated.** |
| Reversibility | Removing the MCP server registration unwires chuzom from a host; provider keys remain in the env. Trivial to remove per dev. | OK. |

**Manual steps that do not scale to 2,000 developers:**

1. Each developer must manage their own provider keys.
2. Each developer must run `chuzom-onboard` and answer interactive prompts.
3. There is no equivalent of an MDM-pushed config, IDE template, or zero-touch enrolment.
4. Setting `CHUZOM_USER_ID` / `CHUZOM_ORG_ID` per developer requires either shell-rc edits or wrapper scripts that the platform team must distribute.
5. Audit-DB location (`~/.chuzom/audit.db`) is per-user-per-host; collecting audit data centrally is the operator's problem.

---

## 2. Developer compatibility

For each representative workload below: does it work, is behaviour preserved, is the developer's experience comparable to direct-provider use?

| Workload | State | Evidence | Verdict |
|---|---|---|---|
| Simple chat completion | Works | text.py tools route to provider via LiteLLM. | OK. |
| Large code context | Works in principle; depends on routed model's context window. `complexity_hint` only loosely informs window selection. | Per-task context-window awareness in routing decisions is partial (`router.py::_resolve_profile` uses complexity, not requested-tokens). | **Risk of silent context truncation when routing downgrades to a smaller-window model.** |
| Repository-wide analysis | Works for the MCP-tool path (`llm_fs_*` when opted in). | SEC-002 sandbox limits to project_root. | Works in opt-in mode. |
| Streaming output | Underlying `_call_text` uses LiteLLM streaming. Routing path does not abort/restart on partial output. | Behaviour preserved for the cold path. | OK. |
| Tool calling | Tool-call protocol passthrough relies on LiteLLM's normalisation. **PRO-002 (LiteLLM normalisation-loss matrix) is unaddressed.** | Risk of feature loss not measured. | **Not validated.** |
| Parallel tool calling | Same as above; not separately validated. | | **Not validated.** |
| Structured output / JSON schema | Same. PRO-001 (tools return strings) keeps structured-output handling at the LiteLLM layer; chuzom does not surface JSON-schema mode explicitly. | | **Risk.** |
| Prompt caching | Provider-side prompt caching is a model-specific feature (Anthropic, OpenAI). chuzom routing may move the call to a different model and silently lose the cache hit. | Cost impact not measured. | **Hidden risk.** |
| Long-running coding session | Works for hook-based hosts; classification side channel is now per-session (INV-007 ok). | | OK. |
| Reasoning controls (Anthropic thinking, OpenAI o-series) | Not explicitly modelled. Routing may downgrade away from reasoning models. | | **Risk.** |
| Multimodal | Media tools exist (`tools/media.py`). Specific provider feature parity not validated. | | **Not validated.** |
| Error handling | LiteLLM exceptions are caught, fallback chain advances. `_pending_spend` released. | | OK. |
| Cancellation | **Not handled.** No `asyncio.CancelledError` handling in `route_and_call`. | A cancelled tool call may still incur provider cost. | **Risk.** |
| Reconnection | Provider client reconnects are LiteLLM-side. | | OK. |
| Request replay | No idempotency keys generated by chuzom; replay would re-bill. | | **Risk for non-idempotent code-modifying tools.** |
| Rate-limit handling | REL-001 — Retry-After honoured. | | OK. |
| Provider fallback | Works; chain in `router.py::_resolve_provider_chain`. | | OK. |

**Net.** Basic workloads work. Feature-preservation across model and provider switches is **not measured**. PRO-002 specifically calls this out.

---

## 3. Developer experience acceptance criteria

| Criterion | Met? | Notes |
|---|---|---|
| Installation < 15 minutes | Yes for a self-driven dev | Wizard-based; quickstart docs present. |
| Central config requires no per-user editing | **No** | Per-user `.env` + `~/.chuzom/profile.yaml`. |
| Authentication understandable | **N/A — no real auth** | Env trust only. |
| Error messages actionable | Mixed | `BudgetExceededError` carries spend / cap; LiteLLM errors propagate raw. |
| User can identify the selected model | Yes | Route indicator surfaces in many tools; chuzom dashboard. |
| User can understand why a request was routed | Partially | `tools/dashboard.py` shows recent routes + tier breakdown. Per-decision rationale string exists in `routing_hints`. |
| User can report a failed request with a trace ID | **Partial** | `request_id` (= correlation_id) now binds into log contextvars (`router.py:1380`) but not surfaced to the developer in tool responses; the dev would have to grep their logs. |
| System does not corrupt streaming | OK | LiteLLM passthrough. |
| System does not silently drop model features | **Unknown** | PRO-002 unaddressed. |
| System does not unexpectedly downgrade quality | **Unmeasured** | No controlled comparison exists. This is the largest evidence gap. |
| System does not significantly slow interactive coding | Likely | Routing overhead is one classification + one chain walk; not benchmarked at p95. |
| Users cannot accidentally spend against the wrong team/project | **NO** | Budgets are global, not team-scoped. INV-011 unaddressed. |
| Users cannot access unauthorised providers/models | **NO** | Per-team/user provider allow-lists do not exist as enforced policies. |

---

## 4. Pilot plan summary

(Full plan in `PILOT_PLAN.md`.)

- **Scope:** 20 developers across 2 teams. Voluntary participation. Opt-in via repo allowlist.
- **Workloads:** non-critical development. Production code is allowed for read/explain workflows; **excluded** for any tool that writes to disk via `llm_fs_*` unless project_root is pre-pinned in a wrapper.
- **Duration:** 6 weeks. Two-week baseline (direct provider) + four-week chuzom.
- **Success metrics:** (a) gross cost / dev / week, (b) p50/p95 time-to-first-token, (c) controlled-corpus completion rate (50 fixed tasks per developer), (d) developer NPS via weekly survey, (e) bypass rate (developers reverting to direct provider).
- **Failure metrics:** completion-rate drop > 5%, p95 TTFT regression > 30%, any data-residency event, any audit row gap, > 30% pilot opt-out rate at week 4.
- **Rollback:** uninstall command + restore baseline `.env`. Both must complete in < 10 minutes per developer.

## 5. Rollout gates (developer)

| # | Gate | Status |
|---|---|---|
| D-1 | No critical security findings open | ✅ SEC-001/002/003 closed |
| D-2 | Per-user budgets enforced | ❌ INV-011 open |
| D-3 | Provider-invoice reconciliation tolerance defined and met | ❌ Reconciliation pipeline absent |
| D-4 | Routing overhead p95 ≤ defined target | ❌ Not measured |
| D-5 | Net-savings demonstrated on representative corpus | ❌ No corpus, no controlled comparison |
| D-6 | Quality regression bound: completion-rate delta within ±2 pp | ❌ Not measured |
| D-7 | Central config push for ≥ 1 setting (e.g. provider allowlist) | ❌ No control plane |
| D-8 | Central enforcement against bypass (provider keys not in dev env) | ❌ Not designed |
| D-9 | Operational runbook covers install / upgrade / rollback / rotate-secret / debug-routing | ❌ Not produced |
| D-10 | Audit chain export to SIEM | ⚠️ CEF/JSON exporters exist (`enterprise/audit.py`); not connected end-to-end |

**3 / 10 gates green.** Pilot can run today; broad rollout cannot.
