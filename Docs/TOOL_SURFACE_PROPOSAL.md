# Chuzom MCP Tool Surface Proposal (1.0 Direction)

> Design-only document. No production code changes. Authored post-0.9.1 audit.

---

## 1. Complete Current Inventory

### 1.1 Enumerated Tools by Module (63 total)

| # | Tool Name | Module | Category |
|---|-----------|--------|----------|
| 1 | `llm_query` | text.py | Completion |
| 2 | `llm_research` | text.py | Completion |
| 3 | `llm_generate` | text.py | Completion |
| 4 | `llm_analyze` | text.py | Completion |
| 5 | `llm_reason` | text.py | Completion |
| 6 | `llm_code` | text.py | Completion |
| 7 | `llm_edit` | text.py | Completion / FS hybrid |
| 8 | `llm_classify` | routing.py | Routing-meta |
| 9 | `llm_track_usage` | routing.py | Routing-meta (internal) |
| 10 | `llm_route` | routing.py | Routing-meta |
| 11 | `llm_auto` | routing.py | Routing-meta |
| 12 | `llm_stream` | routing.py | Routing-meta / streaming |
| 13 | `llm_select_agent` | routing.py | Routing-meta |
| 14 | `llm_reroute` | routing.py | Routing-meta |
| 15 | `llm_delegate` | agentic.py | Agentic tool-loop |
| 16 | `llm_orchestrate` | pipeline.py | Agentic pipeline |
| 17 | `llm_pipeline_templates` | pipeline.py | Config read |
| 18 | `llm_image` | media.py | Media |
| 19 | `llm_video` | media.py | Media |
| 20 | `llm_audio` | media.py | Media |
| 21 | `llm_codex` | codex.py | Provider-specific CLI |
| 22 | `llm_gemini` | gemini_cli.py | Provider-specific CLI |
| 23 | `llm_fs_find` | fs.py | File-ops |
| 24 | `llm_fs_rename` | fs.py | File-ops |
| 25 | `llm_fs_edit_many` | fs.py | File-ops |
| 26 | `llm_fs_analyze_context` | fs.py | File-ops / analysis |
| 27 | `llm_save_session` | admin.py | Session / housekeeping |
| 28 | `llm_set_profile` | admin.py | Config |
| 29 | `llm_usage` | admin.py | Observability |
| 30 | `llm_cache_stats` | admin.py | Observability |
| 31 | `llm_cache_clear` | admin.py | Admin action |
| 32 | `llm_quality_report` | admin.py | Observability |
| 33 | `llm_health` | admin.py | Health |
| 34 | `llm_hook_health` | admin.py | Health |
| 35 | `llm_providers` | admin.py | Config read |
| 36 | `llm_dashboard` | admin.py | Observability / UI |
| 37 | `llm_savings` | admin.py | Observability |
| 38 | `llm_team_report` | admin.py | Observability |
| 39 | `llm_team_push` | admin.py | Admin action |
| 40 | `llm_policy` | admin.py | Config read |
| 41 | `llm_digest` | admin.py | Observability |
| 42 | `llm_benchmark` | admin.py | Observability |
| 43 | `llm_session_dashboard` | admin.py | Observability |
| 44 | `llm_session_spend` | admin.py | Observability |
| 45 | `llm_session_savings` | admin.py | Observability |
| 46 | `llm_approve_route` | admin.py | Routing-meta |
| 47 | `llm_quota_status` | admin.py | Observability |
| 48 | `llm_budget` | admin.py | Config / observability |
| 49 | `llm_share_profile` | admin.py | Config action |
| 50 | `llm_import_profile` | admin.py | Config action |
| 51 | `llm_retrospect` | admin.py | Observability |
| 52 | `llm_gain` | admin.py | Observability |
| 53 | `llm_quality_guard` | admin.py | Observability |
| 54 | `llm_model_usage` | admin.py | Observability |
| 55 | `llm_model_export` | admin.py | Admin action |
| 56 | `llm_model_eval` | admin.py | Observability |
| 57 | `llm_check_usage` | subscription.py | Subscription |
| 58 | `llm_update_usage` | subscription.py | Subscription (internal) |
| 59 | `llm_refresh_claude_usage` | subscription.py | Subscription |
| 60 | `llm_quota_saved` | subscription.py | Subscription / observability |
| 61 | `llm_setup` | setup.py | Onboarding / config |
| 62 | `llm_rate` | setup.py | Quality feedback |
| 63 | `llm_savings_dashboard` | dashboard.py | Observability / UI |
| 64 | `chuzom_agent_list` | agents.py | Agent-sessions |
| 65 | `chuzom_agent_start_session` | agents.py | Agent-sessions |
| 66 | `chuzom_agent_check_budget` | agents.py | Agent-sessions |
| 67 | `chuzom_agent_route` | agents.py | Agent-sessions |
| 68 | `chuzom_agent_complete_session` | agents.py | Agent-sessions |
| 69 | `chuzom_agent_lineage` | agents.py | Agent-sessions |
| 70 | `agoragentic_task` | agoragentic.py | External agent marketplace |
| 71 | `agoragentic_browse` | agoragentic.py | External agent marketplace |
| 72 | `agoragentic_wallet` | agoragentic.py | External agent marketplace |
| 73 | `agoragentic_status` | agoragentic.py | External agent marketplace |

**Actual count: 73 registered tools** (server.py comment says 60; tool_tiers.py says 41; neither is current).

### 1.2 Grouped Counts

| Capability domain | Count |
|---|---|
| Completion (text→text, no tools) | 7 (`query, research, generate, analyze, reason, code, edit`) |
| Routing-meta | 7 (`classify, track_usage, route, auto, stream, select_agent, reroute, approve_route`) → 8 counting `approve_route` from admin |
| Agentic tool-loop | 2 (`delegate, orchestrate`) |
| Media I/O | 3 (`image, video, audio`) |
| Provider-specific CLI shims | 2 (`codex, gemini`) |
| File-ops | 4 (`fs_find, fs_rename, fs_edit_many, fs_analyze_context`) |
| Observability (read-only) | 19 (`usage, cache_stats, quality_report, savings, dashboard, team_report, session_dashboard, session_spend, session_savings, quota_status, budget, retrospect, gain, quality_guard, model_usage, model_eval, savings_dashboard, check_usage, quota_saved`) |
| Admin actions (mutating) | 6 (`cache_clear, team_push, model_export, share_profile, import_profile, refresh_claude_usage`) |
| Config / policy (read) | 4 (`providers, policy, pipeline_templates, llm_budget`) |
| Setup / feedback / onboarding | 3 (`setup, rate, save_session`) |
| Agent-session lifecycle | 6 (`agent_list, agent_start_session, agent_check_budget, agent_route, agent_complete_session, agent_lineage`) |
| External marketplace (Agoragentic) | 4 (`task, browse, wallet, status`) |
| Subscription | 3 (`update_usage, refresh_claude_usage, quota_saved`) — partial overlap above |

---

## 2. Concrete Problems

### P1 — Surface Sprawl (73 tools, ~14,000 context tokens)

The server.py comment says 60. tool_tiers.py says 41. The actual count is 73. The discrepancy itself is a symptom: no single owner has a grip on the surface. Every new feature adds a tool because that's the path of least resistance. At 73 tools, the MCP schema injected into every Claude session consumes enough context to measurably degrade routing accuracy (tool_tiers.py cites 8,000 tokens for 41 tools; at 73 it is closer to 14,000).

### P2 — Taxonomy Leak (the root cause of the mis-routing fault)

The five primary completion tools (`query / research / generate / analyze / code`) are a single capability: send a prompt, get text back, no tool calls. They differ only in which cost/model tier the router targets. That internal routing taxonomy has leaked into the public API surface. Callers must pre-classify their own task before calling, which means:

- They make the same decision the router would make — defeating the router's purpose.
- They make it with less information than the router (no provider health, no quota state, no cost ledger).
- A wrong decision (e.g. calling `llm_analyze` for something that needs tools) creates a dead-end with no escape except the "any llm_* call clears the lock" escape valve — which is itself an undocumented side-channel.

### P3 — The Mis-Routing Fault (the enforcement dead-end)

The push-routing enforcement hook fires `llm_analyze` for a task classified as "deep analysis" — which is correct for the classification, but catastrophically wrong if the task requires tool calls (reading files, running bash, etc.). `llm_analyze` is a completion-only tool. It cannot run tools. The agent is now blocked: the hook demands a tool that cannot do the work, the work requires tools that are blocked, and the only exit is the escape valve. This is a structural fault, not a configuration mistake. It exists because the enforcement contract couples task classification to a specific named tool, and the named tools conflate "how hard is this?" with "what execution shape does this need?"

### P4 — Redundancy

- `llm_route` and `llm_auto` both classify-and-dispatch. They differ in scope but callers cannot tell which to use.
- `llm_stream` is `llm_query` with streaming. Streaming is a transport detail, not a separate tool.
- `llm_reason` is `llm_analyze` with a thinking-budget hint. A parameter, not a tool.
- `llm_edit` and `llm_fs_edit_many` overlap: both do LLM-assisted file edits, with different scope.
- `llm_session_spend`, `llm_session_savings`, `llm_session_dashboard` are three read-only views of the same data.
- `llm_savings`, `llm_gain`, `llm_savings_dashboard` are three more overlapping savings views.
- `llm_quality_report` and `llm_quality_guard` both report quality degradation signals.
- `llm_codex` and `llm_gemini` are provider shims that expose vendor lock-in as first-class tools.

### P5 — DX Cost

A new user or IDE integration sees 73 tools, mostly named `llm_*`, with no clear entry point. The "right" tool for "ask an LLM something" is one of seven, all of which look equivalent to a pull-routing model. The "right" tool for "check on savings" is one of six. The signal-to-noise ratio is catastrophically low for pull routing (IDE model picks from the list), and the noise forces the slim-tier workaround (`CHUZOM_SLIM`) that itself has documentation debt.

---

## 3. Proposed Minimal Surface

### 3.1 Design Principles

1. **Execution shape, not tier, determines the tool.** The caller knows whether they need a completion, an agentic loop, or media generation. They do not know (and should not care) which model tier handles it — that is the router's job.
2. **Fail-open.** No tool should be callable in a state where it structurally cannot complete the work. If routing enforcement cannot decide, it must allow the host model to proceed, not block it.
3. **One front door per execution shape.** Pull-routing models get a small, legible, well-named list with unambiguous semantics. Each tool name is a shape, not a tier.
4. **All observability behind one namespace tool.** Observability is not part of the task execution surface; keep it separate and consolidated.
5. **Tier is a parameter, not a tool name.** `complexity="simple|moderate|complex"` or `tier="fast|balanced|best"` replaces the five completion tools.

### 3.2 Proposed Tool Surface (12 public tools)

#### Execution surface (4 tools)

```
llm(prompt, *, task="auto", tier=None, model=None, context=None,
    system_prompt=None, temperature=None, max_tokens=None,
    stream=False) → str
```
The universal completion tool. `task` hints the router's internal classifier
(`"query" | "research" | "generate" | "analyze" | "code" | "auto"`). `tier`
hints cost level (`"fast" | "balanced" | "best"`). Both are optional — the
router classifies when omitted. Returns text. Never runs tools. Stream via
`stream=True` (replaces `llm_stream`).

**This is also the push-routing enforcement target for ALL completion tasks.**
The hook emits `ROUTE: llm(task="analyze")` not `ROUTE: llm_analyze`. The
distinction matters: enforcement now names a parameter value, not a separate
tool, so a caller who needs tools can always call `llm_act` instead without
being trapped.

```
llm_act(goal, *, budget_usd=1.0, context=None, session_id=None) → str
```
Agentic tool-loop. Decomposes `goal` into milestones, executes each on the
cheapest capable tier WITH tool access (bash, file-ops, etc.), escalates on
failure, returns JSON outcome. Replaces `llm_delegate`. `llm_orchestrate` is
merged here as a named pipeline mode (distinguishable via `goal` phrasing; or
add `mode="pipeline"` param if needed). Session budget is enforced via
`session_id` linking to `chuzom_session`.

```
llm_media(prompt, *, media_type="image", style=None, duration_s=None,
          voice=None, output_format=None) → str
```
Unified media generation. `media_type` is `"image" | "video" | "audio"`.
Replaces `llm_image`, `llm_video`, `llm_audio`.

```
llm_cli(task, *, provider="auto", context=None) → str
```
Provider-native CLI delegation. Routes to Codex CLI or Gemini CLI based on
`provider` hint or availability. Replaces `llm_codex`, `llm_gemini`. This is
distinct from `llm` because these providers have their own agentic runtimes
and tool access; they are not completion tools.

#### File-ops surface (1 tool, gated)

```
llm_fs(operation, *, paths=None, pattern=None, edits=None,
       project_root=None, dry_run=False) → str
```
Consolidated file-operation tool. `operation` is
`"find" | "rename" | "edit_many" | "analyze_context"`.
Replaces `llm_fs_find`, `llm_fs_rename`, `llm_fs_edit_many`,
`llm_fs_analyze_context`. Controlled by the same `CHUZOM_FS_TOOLS` flag.
`llm_edit` (from text.py) is merged here as `operation="edit"` — it is a
file-op, not a completion.

#### Routing / enforcement surface (2 tools, used by hooks not callers)

```
chuzom_route(prompt, *, context=None, session_id=None) → RouteDecision
```
Classify and return a routing decision (task type + tier + recommended tool).
Used by push-routing hooks before enforcement. Replaces `llm_classify`,
`llm_route`, `llm_auto`. Hook-facing only; not promoted in pull-routing lists.
Returns structured JSON (not a formatted string) because its consumers are
hooks, not humans.

```
chuzom_approve(decision_id, *, action="approve") → str
```
Human-in-the-loop approval for routing decisions that exceed a cost threshold.
Replaces `llm_approve_route`. `action` is `"approve" | "reject" | "escalate"`.

#### Observability surface (2 tools)

```
chuzom_status(*, view="summary", period="today", session_id=None) → str
```
Single read-only observability tool. `view` is:
`"summary" | "savings" | "usage" | "session" | "quota" | "quality" |
 "health" | "providers" | "model" | "cache" | "policy" | "budget"`.
Replaces: `llm_usage`, `llm_savings`, `llm_savings_dashboard`,
`llm_session_spend`, `llm_session_savings`, `llm_session_dashboard`,
`llm_quota_status`, `llm_quality_report`, `llm_quality_guard`, `llm_health`,
`llm_hook_health`, `llm_providers`, `llm_model_usage`, `llm_model_eval`,
`llm_cache_stats`, `llm_policy`, `llm_budget`, `llm_gain`, `llm_retrospect`,
`llm_benchmark`, `llm_digest`, `llm_team_report`, `llm_check_usage`,
`llm_quota_saved`, `llm_dashboard`, `llm_pipeline_templates`.
Total: replaces 26 tools with parameterised views.

```
chuzom_admin(action, *, profile=None, period=None, url=None,
             format=None, send=False) → str
```
Mutating admin actions. `action` is:
`"set_profile" | "import_profile" | "share_profile" | "cache_clear" |
 "model_export" | "team_push" | "refresh_usage" | "save_session" | "rate" |
 "setup" | "benchmark"`.
Replaces: `llm_set_profile`, `llm_import_profile`, `llm_share_profile`,
`llm_cache_clear`, `llm_model_export`, `llm_team_push`,
`llm_refresh_claude_usage`, `llm_update_usage`, `llm_save_session`,
`llm_rate`, `llm_setup`.
Total: replaces 11 tools.

#### Agent-session surface (1 tool)

```
chuzom_session(action, *, goal=None, session_id=None, limit=200) → dict
```
Agent session lifecycle. `action` is:
`"list" | "start" | "check_budget" | "route" | "complete" | "lineage"`.
Replaces: `chuzom_agent_list`, `chuzom_agent_start_session`,
`chuzom_agent_check_budget`, `chuzom_agent_route`,
`chuzom_agent_complete_session`, `chuzom_agent_lineage`.

#### External marketplace (optional / feature-flagged)

```
agoragentic(action, *, task=None, ...) → str
```
Unchanged in semantics; consolidate the 4 tools into 1 with `action` param
(`"task" | "browse" | "wallet" | "status"`). Keep the `AGORAGENTIC_ENABLED`
feature flag; register only when enabled.

### 3.3 Summary Count

| Group | Old count | New count | Tools |
|---|---|---|---|
| Completion | 7 | 1 | `llm` |
| Agentic | 2 | 1 | `llm_act` |
| Media | 3 | 1 | `llm_media` |
| Provider CLI | 2 | 1 | `llm_cli` |
| File-ops | 4+1 | 1 | `llm_fs` |
| Routing/enforcement | 8 | 2 | `chuzom_route`, `chuzom_approve` |
| Observability | 26 | 1 | `chuzom_status` |
| Admin/config/setup | 11 | 1 | `chuzom_admin` |
| Agent sessions | 6 | 1 | `chuzom_session` |
| Marketplace | 4 | 1 | `agoragentic` |
| **Total** | **73** | **11** | (12 counting `agoragentic`) |

Context-token budget: 11 tools × ~150 tokens/tool ≈ **1,650 tokens** vs. the current ~14,000. Slim mode becomes unnecessary for the default case.

---

## 4. Push and Pull Routing Mapping

### 4.1 Push Routing (hook classifies, enforces, blocks)

The UserPromptSubmit hook currently emits `REQUIRED: llm_analyze` (a named tool). This is the root of the mis-routing fault.

**With the new surface**, the hook emits:

```
⚡ ROUTE: llm(task="analyze", tier="balanced")
```

The enforcement lock is on the *tool name* `llm`, not on a completion/agentic distinction. When the host model determines it needs tools to fulfill the task, it calls `llm_act` instead. The lock policy must permit this:

```
Lock rule (1.0):
  PERMITTED while ROUTE lock is active:
    - llm(...)           # completion path
    - llm_act(...)       # agentic path — always permitted as escalation
    - chuzom_status(...) # read-only status never blocked
    - chuzom_approve(...)# approval always unblocked
  BLOCKED while ROUTE lock is active:
    - All other tools (bash, file read, etc.)
```

This eliminates the dead-end: a task that needs tools is never forced through a completion-only tool. The lock allows `llm_act` as a valid resolution of any route hint.

### 4.2 Pull Routing (IDE model picks a tool from the list)

With 11 tools, the names are self-explanatory. An IDE model sees:

- `llm` — ask an LLM (completion)
- `llm_act` — ask an LLM to DO something (agentic)
- `llm_media` — generate media
- `llm_cli` — run Codex/Gemini CLI
- `llm_fs` — file operations
- `chuzom_route` — (system use, hooks only; still visible but description discourages direct use)
- `chuzom_approve` — approve a routing decision
- `chuzom_status` — check status/savings/health
- `chuzom_admin` — configure/manage
- `chuzom_session` — agent session lifecycle
- `agoragentic` — Agoragentic marketplace

The naming scheme gives pull-routing models strong signal: `llm_*` = "run LLM work", `chuzom_*` = "manage the router itself". No ambiguity between "get stats" and "do a task". No need to know which of 7 completion flavors to pick.

---

## 5. Fault-Proofing Analysis

### 5.1 Wrong-Tool Dead-Ends — Eliminated

**Current fault**: hook says `USE llm_analyze`, task needs bash → dead-end.

**1.0**: hook says `USE llm(task="analyze")`. If the model needs tools: calls `llm_act`. Lock permits `llm_act` as an unconditional escape. No dead-end.

**Invariant to enforce in the lock implementation**:
> `llm_act` is ALWAYS permitted during an active route lock.
> `chuzom_status` and `chuzom_approve` are ALWAYS permitted.
> These three are non-blocking by definition.

### 5.2 Fail-Open Behavior — Explicit Policy

| Scenario | Current behavior | 1.0 behavior |
|---|---|---|
| Router down / no providers | Varies by tool | `llm` → host model handles directly; no block |
| Hook mis-classifies as "completion" but task needs tools | Dead-end (blocked) | Host calls `llm_act`; lock permits it |
| `llm_act` planner fails | Returns `{"outcome":"surfaced","ok":false}` | Same; never loops |
| Budget exceeded | Varies | `chuzom_session` check_budget → surfaced, not crashed |
| Provider quota exhausted | Silent fallback or error | `llm` cascades through provider priority list; last resort is host model |

Explicit rule: **the host model must never be fully blocked**. If every `llm*` tool fails, the lock must expire or self-clear within one turn. A blocked-forever state is a bug.

### 5.3 Caller Traps — Structural Changes

- **No tool requires pre-classification** of task type. `task="auto"` is always a valid input to `llm`.
- **No tool is completion-only in the enforcement hot path**. Enforcement targets `llm`, which the router internally decides to route as completion or escalate to agentic.
- **No tool exposes internal taxonomy as required API**. The `task` hint in `llm` is optional and advisory, not a gate.

### 5.4 Observability Consolidation — Fault Reduction

26 overlapping read-only tools create opportunity for stale data, duplicate DB queries, and inconsistent formatting. One `chuzom_status(view=...)` tool with a single code path, single DB connection pool, and unified formatter eliminates an entire class of data-inconsistency bugs.

---

## 6. Migration Plan

### 6.1 Phase 0 — Aliases (0.9.x, non-breaking)

Register all 1.0 names as aliases for their current implementations. No behavioral change. This allows early adopters to start writing 1.0 calls.

```python
# Example alias in text.py register()
mcp.tool(name="llm")(llm_query)  # route via task param internally
```

Tools to alias immediately (safe, same signature shape):
- `llm` → `llm_query` (with internal `task` dispatch)
- `llm_act` → `llm_delegate`
- `llm_media` → dispatches `llm_image/video/audio` by `media_type`
- `chuzom_status` → dispatches to matching admin/dashboard/subscription functions by `view`
- `chuzom_session` → dispatches to `chuzom_agent_*` by `action`

### 6.2 Phase 1 — Deprecation Warnings (0.10.x)

All old tool names emit a deprecation notice in their response:

```
[DEPRECATED in 1.0: use llm(task="analyze") instead of llm_analyze]
```

Duration: minimum 2 minor versions (0.10.x, 0.11.x). External integrations and hook files in the wild need time to update. Deprecate in response body only — not as an error, not as a warning that breaks CI.

### 6.3 Phase 2 — 1.0 Breaking Changes

**Tools removed in 1.0** (all have aliases from Phase 0):

| Removed tool | Replacement |
|---|---|
| `llm_query` | `llm(task="query")` |
| `llm_research` | `llm(task="research")` |
| `llm_generate` | `llm(task="generate")` |
| `llm_analyze` | `llm(task="analyze")` |
| `llm_reason` | `llm(task="analyze", tier="best")` |
| `llm_code` | `llm(task="code")` |
| `llm_edit` | `llm_fs(operation="edit")` |
| `llm_classify` | `chuzom_route(prompt)` |
| `llm_track_usage` | internal; remove from public surface |
| `llm_route` | `chuzom_route(prompt)` |
| `llm_auto` | `chuzom_route(prompt)` |
| `llm_stream` | `llm(stream=True)` |
| `llm_select_agent` | `chuzom_session(action="route")` |
| `llm_reroute` | `chuzom_route(prompt)` |
| `llm_approve_route` | `chuzom_approve(decision_id)` |
| `llm_orchestrate` | `llm_act(goal, mode="pipeline")` |
| `llm_pipeline_templates` | `chuzom_status(view="pipeline_templates")` |
| `llm_image` | `llm_media(media_type="image")` |
| `llm_video` | `llm_media(media_type="video")` |
| `llm_audio` | `llm_media(media_type="audio")` |
| `llm_codex` | `llm_cli(provider="codex")` |
| `llm_gemini` | `llm_cli(provider="gemini")` |
| `llm_fs_find` | `llm_fs(operation="find")` |
| `llm_fs_rename` | `llm_fs(operation="rename")` |
| `llm_fs_edit_many` | `llm_fs(operation="edit_many")` |
| `llm_fs_analyze_context` | `llm_fs(operation="analyze_context")` |
| `llm_save_session` | `chuzom_admin(action="save_session")` |
| `llm_set_profile` | `chuzom_admin(action="set_profile")` |
| `llm_usage` | `chuzom_status(view="usage")` |
| `llm_cache_stats` | `chuzom_status(view="cache")` |
| `llm_cache_clear` | `chuzom_admin(action="cache_clear")` |
| `llm_quality_report` | `chuzom_status(view="quality")` |
| `llm_health` | `chuzom_status(view="health")` |
| `llm_hook_health` | `chuzom_status(view="health")` |
| `llm_providers` | `chuzom_status(view="providers")` |
| `llm_dashboard` | `chuzom_admin(action="dashboard")` |
| `llm_savings` | `chuzom_status(view="savings")` |
| `llm_team_report` | `chuzom_status(view="team")` |
| `llm_team_push` | `chuzom_admin(action="team_push")` |
| `llm_policy` | `chuzom_status(view="policy")` |
| `llm_digest` | `chuzom_admin(action="digest")` |
| `llm_benchmark` | `chuzom_admin(action="benchmark")` |
| `llm_session_dashboard` | `chuzom_status(view="session")` |
| `llm_session_spend` | `chuzom_status(view="session")` |
| `llm_session_savings` | `chuzom_status(view="session")` |
| `llm_quota_status` | `chuzom_status(view="quota")` |
| `llm_budget` | `chuzom_status(view="budget")` |
| `llm_share_profile` | `chuzom_admin(action="share_profile")` |
| `llm_import_profile` | `chuzom_admin(action="import_profile")` |
| `llm_retrospect` | `chuzom_status(view="retrospect")` |
| `llm_gain` | `chuzom_status(view="savings")` |
| `llm_quality_guard` | `chuzom_status(view="quality")` |
| `llm_model_usage` | `chuzom_status(view="model")` |
| `llm_model_export` | `chuzom_admin(action="model_export")` |
| `llm_model_eval` | `chuzom_status(view="model")` |
| `llm_check_usage` | `chuzom_status(view="quota")` |
| `llm_update_usage` | `chuzom_admin(action="refresh_usage")` |
| `llm_refresh_claude_usage` | `chuzom_admin(action="refresh_usage")` |
| `llm_quota_saved` | `chuzom_status(view="quota")` |
| `llm_setup` | `chuzom_admin(action="setup")` |
| `llm_rate` | `chuzom_admin(action="rate")` |
| `llm_savings_dashboard` | `chuzom_status(view="savings")` |
| `chuzom_agent_list` | `chuzom_session(action="list")` |
| `chuzom_agent_start_session` | `chuzom_session(action="start")` |
| `chuzom_agent_check_budget` | `chuzom_session(action="check_budget")` |
| `chuzom_agent_route` | `chuzom_session(action="route")` |
| `chuzom_agent_complete_session` | `chuzom_session(action="complete")` |
| `chuzom_agent_lineage` | `chuzom_session(action="lineage")` |
| `agoragentic_task` | `agoragentic(action="task")` |
| `agoragentic_browse` | `agoragentic(action="browse")` |
| `agoragentic_wallet` | `agoragentic(action="wallet")` |
| `agoragentic_status` | `agoragentic(action="status")` |

**What stays stable across 1.0**:
- All response string formats — callers parsing response text are unaffected.
- All underlying router logic, provider adapters, DB schema.
- `CHUZOM_SLIM` env var — the slim tier definitions update to name the new tools.

### 6.4 Hook File Updates (1.0 gate)

All files under `~/.claude/hooks/chuzom-*.py` that emit enforcement hints by tool name must be updated to emit `llm(task=...)` format. This is a required deliverable for 1.0 — an incompatible hook file that still emits `ROUTE: llm_analyze` will re-introduce the mis-routing fault. A `chuzom hooks check` CLI command should detect and report stale hook files.

---

## 7. Critique of the `llm / llm_delegate / llm_media / llm_route` Sketch

### The sketch

> `llm` (completion, tier chosen internally) · `llm_delegate` (agentic tool loop) · `llm_media` (image/audio/video) · `llm_route` (single front door that classifies and dispatches)

### What it gets right

- **Execution shape over tier**: collapsing the 5 completion tools into `llm` is exactly right. This fixes P2 (taxonomy leak) and P3 (mis-routing fault) in one move.
- **`llm_media` as a distinct tool**: media generation is genuinely a different execution shape (different provider pool, different output format, different cost structure). Keeping it separate is correct.
- **`llm_delegate` as agentic**: keeping the tool-loop path distinct from completion is correct — they have fundamentally different execution semantics.

### What the sketch gets wrong or underspecifies

**Problem 1 — `llm_route` as a "single front door" conflates two distinct use cases.**

A single front door is appealing, but it serves two very different callers:
- Push-routing hooks need a *routing decision* (JSON: which tool, which tier, confidence). They call `chuzom_route`, consume structured data, then enforce.
- Pull-routing IDE models need to *do work*, not route. They should call `llm` directly with `task="auto"` — having them call `llm_route` first adds a round-trip and a structural dependency.

A front door that returns a routing decision is a meta-tool. A front door that does the work is a completion tool. These are not the same door. The sketch tries to make `llm_route` both, which reintroduces ambiguity.

**Recommendation**: `chuzom_route` is a hook-facing meta-tool (returns structured JSON, not shown in the primary pull-routing list). `llm` with `task="auto"` is the pull-routing front door. These are separate.

**Problem 2 — The sketch omits observability, admin, file-ops, sessions, and the provider CLI shims.**

The sketch implicitly assumes these are unimportant or out of scope, but they account for 54 of the 73 tools. The dominant DX problem is the observability explosion (26 read-only tools). Leaving these out of the redesign leaves most of the surface sprawl intact.

**Problem 3 — `llm_delegate` keeps the old name, which carries wrong associations.**

"Delegate" implies delegation to a sub-agent. The 1.0 semantics are: decompose, execute, escalate — which is better described as "act". `llm_act` communicates "execute an agentic action with tool access" more clearly than "delegate", and avoids confusion with the `chuzom_session(action="route")` delegation path.

### Recommended alternative

Replace the 4-tool sketch with the **11-tool surface** defined in Section 3.2. Key differences:
- `llm_route` is replaced by `chuzom_route` (hook-facing, structured JSON, not promoted in pull-routing)
- `llm_delegate` is renamed `llm_act` (clearer semantics)
- Observability, admin, sessions, and file-ops are explicitly addressed
- The enforcement lock policy is explicitly defined (Section 5.1)

---

## Appendix A — Updated Slim-Mode Tier Definitions (1.0)

```python
CORE_TOOLS: frozenset[str] = frozenset({
    "llm",
    "chuzom_status",
})

ROUTING_TOOLS: frozenset[str] = CORE_TOOLS | frozenset({
    "llm_act",
    "llm_fs",
    "chuzom_route",
    "chuzom_approve",
    "chuzom_admin",
    "chuzom_session",
})

# "off" = all 11 tools (was 73)
```

With 1.0, even "off" mode is only 11 tools (~1,650 tokens). `CHUZOM_SLIM` transitions from a workaround to a genuine power-user tuning knob.

---

## Appendix B — `llm_track_usage` Note

`llm_track_usage` is an internal function exposed as a public MCP tool — likely by mistake. It should be removed from the public surface in Phase 0 (not aliased, just de-registered). No external caller should be routing to this; if they are, it means the hook file is broken and needs updating anyway.
