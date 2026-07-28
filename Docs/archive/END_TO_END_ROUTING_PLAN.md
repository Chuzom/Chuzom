# End-to-End Routing Plan

> **Governing principle**: Every user request AND every agent step is routed to the
> cheapest model **capable of completing the task at the required quality**. "Capable"
> means the model can perform REAL work — local file operations, tool use, command
> execution, and verification — via a tool-capable harness (`llm_act` / MGEE). Claude
> is the top of the escalation ladder, reached only when no cheaper model passes the
> quality gate.
>
> See: `NORTH_STAR.md` · `docs/PLAN_0_9_1.md` · `docs/TOOL_SURFACE_PROPOSAL.md`

---

## Phase Summary

| Phase | Name | North Star motion | Gate |
|---|---|---|---|
| **P0** | Foundation | Default enforcement ON; measurement ledger; F5 + F1 + F2 fixes | Required before P1 |
| **P1** | Route executions | `llm_act` is the operational routing target; routed model gets cwd + tools + context | Requires P0 |
| **P2** | Capability-aware classification | Classifier emits `needs_tools`+`context_scope`; agent steps use identical pipeline | Requires P1 |
| **P3** | Verify + escalate on quality | Objective acceptance gate; result-quality signal; done-frontier escalation | Requires P2 |
| **P4** | Unify tool surface | 73 → 11 tools; enforcement lock fix eliminates completion dead-end | Phase 0 aliases start with P0 |
| **P5** | Agent-step parity + reliability | Agent steps classified + provisioned + verified identically to user prompts | Requires P3 |

---

## P0 — Foundation

### Purpose

P0 establishes the three prerequisites without which all later routing is advisory
and unverifiable: (a) enforcement defaults to a mode that actually enforces,
(b) the measurement ledger exists so later phases can be validated against real data,
and (c) the two live bugs that silently kill routing are fixed.

### Steps

**P0-1 — Default enforcement → `smart`**

*File*: `src/chuzom/enforce_config.py` line 36

```python
# BEFORE
DEFAULT_ENFORCE = "soft"

# AFTER
DEFAULT_ENFORCE = "smart"
```

`"smart"` mode is already fully implemented in `enforce-route.py` (lines 31-35):
blocks `Bash / Edit / Write / MultiEdit / NotebookEdit` for Q&A task types
(`_QA_TASK_TYPES = {"query","research","generate","analyze"}`, line 78) and also
blocks `Glob / Read / Grep / LS` for those same types (`_QA_ONLY_BLOCK_TOOLS`,
line 79); soft-enforces for code tasks (file tools needed for actual editing).

Also update `repo_config.py` line 26 (`VALID_ENFORCE`) to include `"smart"` so
`.chuzom.yml` `enforce: smart` is accepted as a valid per-repo value.

**P0-2 — Routing-quality measurement ledger**

Create `src/chuzom/routing_quality_ledger.py`. Append-log at
`~/.chuzom/routing_quality.jsonl` (same atomic-write pattern as `session_store.py`):

```python
@dataclass(frozen=True)
class RoutingRecord:
    session_id: str
    turn_id: str
    timestamp: float
    task_type: str            # from classifier
    complexity: str           # simple / moderate / complex
    needs_tools: bool         # populated P2+
    context_scope: str        # populated P2+
    routed_tier: str          # local / codex / gemini / claude / completion
    routing_accuracy: bool    # acceptance check passed on first try?
    task_completion: bool     # acceptance check ever passed?
    tool_exec_success: bool   # all tool-call exit codes == 0 inside agentic loop
    result_quality: float     # 0.0–1.0 (P3 judge / heuristic)
    verification_pass: bool   # objective check passed (not self-report)
    escalation_count: int     # tier escalations before pass or surface
    cost_usd: float
    baseline_usd: float       # Opus equivalent
    mis_route: bool           # escalation_count > 0
    is_agent_step: bool       # P5+
```

Wire `record_routing_event()` into:
- `src/chuzom/tools/agentic.py` `llm_delegate()` end (extends existing
  `record_delegation_savings` call, line 109).
- `src/chuzom/agentic/service.py` `serialize()` result (lines 15-33).
- `src/chuzom/router.py` `route_and_call()` return path (for completion routes).

Expose via `chuzom_status(view="routing_quality")` (P4 alias target).

**P0-3 — Fix F5: register `agent-depth-release.py` under `SubagentStop`**

Add to `~/.claude/settings.json`:
```json
"SubagentStop": [{
  "matcher": "",
  "hooks": [{"type": "command",
    "command": "python /Users/yali.pollak/.claude/hooks/chuzom-agent-depth-release.py"}]
}]
```

Add a startup self-check in `src/chuzom/hooks/agent-route.py` `main()` that reads
`~/.claude/settings.json` and emits a `stderr` warning if `SubagentStop` is absent.
Add `chuzom hooks fix` to `src/chuzom/cli.py` to write the missing entry.

**P0-4 — Fix F1: `operational_signal` false positives**

*File*: `src/chuzom/operational_signal.py`

1. Extend `_CONTENT_OBJECT_RE` (line 50) with assessment/education nouns:
   `quiz|exam|test[\s-]plan|worksheet|lesson[\s-]plan|curriculum|scenario|exercise|flashcard|syllabus`

2. Add `_SOFTWARE_CONTEXT_RE` after line 55:
   ```python
   _SOFTWARE_CONTEXT_RE = re.compile(
       r"\b(src/|tests?/|\.py\b|\.ts\b|\.go\b|\.rs\b|repo|codebase|module|"
       r"function\b|class\b|endpoint|API|pytest|unittest|CI|failing\s+test|"
       r"test\s+suite|lint|mypy|refactor|pull\s+request|PR\b|branch|commit)\b",
       re.IGNORECASE,
   )
   ```

3. In `detect_operational()` (line 87), require all three signals:
   ```python
   if verb_m and cue_m and _SOFTWARE_CONTEXT_RE.search(p):
   ```

**P0-5 — Fix F2: planner retry + JSON repair**

*File*: `src/chuzom/tools/agentic.py`

1. In `_extract_plan_json()` (line 44): before bare `[..rfind("]")` scan, strip
   prose before first `[` and after last `]` then attempt `json.loads` on the
   trimmed string.

2. Wrap `planner_model()` in `_default_planner()` (line 64) with max-2-retry loop:
   on `PlanRejected`, prepend the bad response to the next prompt asking for
   JSON-only output.

### Behavior introduced / changed

- Routing enforcement is active by default. No per-session config or env export needed.
- Every routing event writes to the quality ledger from turn 0.
- Agent spawning depth counts correctly (F5: live nesting, not lifetime count).
- Educational/assessment prompts no longer hard-route to `llm_delegate` (F1).
- Planner succeeds on ~95% of real model responses (F2 retry).

### North Star motion

Satisfies rubric items 3 (classification precision) and 6 (measurable). P0 is the
minimum viable state from which every later phase can be validated quantitatively.

### Tests to add

```
tests/test_enforce_config.py        — DEFAULT_ENFORCE == "smart"; resolve_enforce_mode() env > repo > user > default priority
tests/test_operational_signal.py    — quiz/exam/test-plan do NOT fire; software-context required; positive controls still fire
tests/test_agentic_planner.py       — _extract_plan_json: fenced+prose/bare/truncated/None; retry: prose-then-JSON succeeds; all-bad → PlanRejected
tests/test_hook_health.py           — missing SubagentStop → unhealthy; correct entry → healthy
tests/test_routing_quality_ledger.py — record_routing_event writes all 16 fields; concurrent writers produce correct aggregate total
```

---

## P1 — Route Executions

### Purpose

P1 is the structural pivot: routing a completion → routing an execution. The
`operational_signal` detector already identifies prompts that need tool-capable
agentic work. P1 wires that signal into `enforce-route.py` so those prompts go
to `llm_act` (MGEE harness) with the cwd, bash/read/write/git tools, repo state,
and session context the routed model needs to do REAL work.

### Steps

**P1-1 — Register `llm_act` alias**

*File*: `src/chuzom/tools/agentic.py` `register()` (line 114):

```python
def register(mcp) -> None:
    mcp.tool()(llm_delegate)             # keep old name (until P4 removes it)
    mcp.tool(name="llm_act")(llm_delegate)  # 1.0 alias — hooks emit this name
```

**P1-2 — Add `cwd` + `context` parameters to `llm_act`**

*File*: `src/chuzom/tools/agentic.py` function signature:

```python
async def llm_delegate(
    task: str,
    budget_usd: float = 1.0,
    baseline_cost_per_milestone: float = 0.20,
    context: str | None = None,   # ADD — bounded session summary
    cwd: str | None = None,       # ADD — repo working directory
) -> str:
```

Inside the function body:
1. Resolve `cwd = cwd or os.getcwd()`.
2. Pass `cwd` to `_default_adapters(cwd=cwd)` so both `ReActAgent` (line 121,
   `self.cwd`) and `CodexAdapter` (line 73, `self.cwd`) use it as their working
   directory.
3. If `context` is provided, prepend it (bounded at 500 tokens via
   `token_budget.truncate_to_budget`) to the `goal` string passed to `hybrid_plan`.

*File*: `src/chuzom/agentic/adapters.py` `CodexAdapter` (line 62):
`cwd` field already present at line 73; ensure `_default_adapters()` passes the
received `cwd` value rather than leaving it `None`.

*File*: `src/chuzom/agentic/react.py` `ReActAgent` (line 112):
`cwd` field already present at line 121; `default_tool_executor(cwd=self.cwd)`
already wires it at line 130.

**P1-3 — Wire session context from `enforce-route.py`**

*File*: `src/chuzom/hooks/enforce-route.py` — in the `_is_operational_prompt` branch:

```python
if _is_operational_prompt(prompt) and _delegate_route_enabled():
    try:
        from chuzom.session_store import build_context_block
        ctx = build_context_block(session_id, max_chars=1500)
    except Exception:
        ctx = None
    _emit_llm_act_route(prompt, context=ctx, cwd=str(Path.cwd()))
```

`_emit_llm_act_route` writes the route instruction into the hook output block so
Claude Code executes `llm_act(task=prompt, context=ctx, cwd=cwd)`.

**P1-4 — Disable tier-0 ReAct for enforced operational paths (LimitB fix)**

*File*: `src/chuzom/tools/agentic.py` `_default_adapters()` (line 83):

```python
def _default_adapters(
    cwd: str | None = None,
    operational: bool = False,
) -> dict[int, Any]:
    from chuzom.agentic.react import ReActAgent
    if operational:
        # Tier-0 reliability insufficient for hard-routed operational tasks.
        # Start at tier-1 (Codex). See PLAN_0_9_1.md LimitB.
        return {1: CodexAdapter(tier=1, cwd=cwd)}
    return {0: ReActAgent(tier=0, cwd=cwd), 1: CodexAdapter(tier=1, cwd=cwd)}
```

Pass `operational=True` when `llm_act` is invoked from the enforce-route hook.
This can be signalled via a `_operational: bool = False` parameter on `llm_delegate`
that the hook sets when emitting the route.

### Behavior introduced / changed

- Operational prompts are routed to `llm_act`, which provisions Codex (tier-1) with
  `cwd` and a bounded session context summary.
- The routed model reads/writes real files and runs bash — it does REAL work.
- `enforce-route.py` blocks direct Claude execution on operational tasks and redirects
  with the session context delegated agents need (LimitA fix).
- Tier-0 ReAct is bypassed for enforced tasks (LimitB fix).

### North Star motion

P1 realizes the core reframe. A cheap model (Codex subscription at $0 marginal cost)
now performs file edits and bash commands that previously fell back to Claude. This
is the highest-leverage phase: every operational prompt offloaded from Claude
directly reduces cost by the full Opus baseline.

### How user prompts AND agent steps are handled

- **User prompts**: `auto-route.py` classifies → `enforce-route.py` intercepts the
  first tool call → if `is_operational(prompt)` fires → emits `llm_act(task, cwd,
  context)` → MGEE runs Codex (tier-1) → acceptance checks → escalates to Claude
  only on failure.
- **Agent steps**: Still handled by `agent-route.py` as in 0.9.x. Full parity in P5.

### Tests to add

```
tests/test_agentic_tool.py      — llm_act with cwd=<tmpdir>: write_file lands in tmpdir; path-traversal "../outside" raises ValueError (react.py line 86)
tests/test_context_injection.py — llm_act(context=...) prepends context to first milestone; oversized context truncated at 500-token bound
tests/test_enforce_route.py     — operational prompt → hook emits llm_act with cwd + context; non-operational → does NOT emit llm_act
tests/test_default_adapters.py  — _default_adapters(operational=True) → dict has only tier=1; _default_adapters() → has tier=0 and tier=1
```

---

## P2 — Capability-Aware Classification

### Purpose

P2 enriches classifier output from `(task_type, complexity)` to
`(task_type, complexity, needs_tools, context_scope)` so the enforcement hook
selects the execution shape — `llm` for completion, `llm_act` for tool-needing
tasks — without a separate `operational_signal` call at hook time. The same
enriched classification runs for agent steps (parity prerequisite for P5).

### Steps

**P2-1 — Enriched routing decision struct**

Create (or extend `src/chuzom/types.py`):

```python
@dataclass(frozen=True)
class RoutingDecision:
    task_type: TaskType
    complexity: Complexity
    needs_tools: bool           # True → route to llm_act
    context_scope: str          # "repo" | "session" | "external" | "none"
    confidence: float
    signal_source: str          # "heuristic" | "ollama" | "api" | "fallback"
```

**P2-2 — Populate `needs_tools` in `auto-route.py`**

After heuristic scoring in `auto-route.py` step 2, call `is_operational(prompt)`
(from `chuzom.operational_signal`) and set `needs_tools=True` in the routing
decision. Write it to the pending state file (`~/.chuzom/pending_route_*.json`)
alongside the existing `task_type` field. `enforce-route.py` reads `needs_tools`
from that file instead of re-running the operational detector itself.

**P2-3 — Populate `context_scope`**

In the same classifier, detect:
- `"repo"` — prompt contains `src/`, `.py`, `.ts`, file paths, or git object refs.
- `"session"` — prompt references earlier turns ("as I mentioned", "the function we discussed").
- `"external"` — prompt needs web search / current-events knowledge.
- `"none"` — none of the above.

`context_scope` drives what `llm_act` provisions:
- `"repo"` → inject `git diff HEAD --stat`, `git log --oneline -5`, and relevant file list.
- `"session"` → inject full session context block from `session_store.py`.
- `"external"` → pre-fetch a web search result via `llm_research` before delegating.
- `"none"` → no extra context (saves tokens).

**P2-4 — Same classification for agent steps**

*File*: `src/chuzom/hooks/agent-route.py`:

When a sub-agent spawn is intercepted (before the spawn decision), pass the
agent's goal string through `classify_prompt()` (the same function used by
`auto-route.py`). The resulting `RoutingDecision` determines:
- `needs_tools=True` → emit `llm_act(goal=..., cwd=cwd, context=ctx)`.
- `needs_tools=False` and task is Q&A → emit `llm(task=..., prompt=goal)`.
- `complexity == "complex"` or classifier confidence < 0.5 → allow Claude sub-agent.

### Behavior introduced / changed

- Every routing decision carries execution shape. `enforce-route.py` reads one field
  (`needs_tools`) rather than re-running a separate detector.
- Over-provisioning eliminated: `context_scope="none"` means zero extra tokens.
- Agent steps are classified with the same logic as user prompts.

### North Star motion

Classification accuracy is the lever for "cheapest capable model". `needs_tools`
prevents the dead-end (completion tool on a task that needs bash). `context_scope`
prevents under-provisioning (routed model gets the context it needs to succeed
on the first try, reducing escalation).

### Tests to add

```
tests/test_routing_decision.py  — operational prompt → needs_tools=True; explanatory → False; file-path ref → context_scope="repo"
tests/test_auto_route.py        — pending state file contains needs_tools + context_scope after classification
tests/test_agent_route_p2.py    — agent goal classified → needs_tools=True → llm_act; Q&A goal → llm; complex → Claude sub-agent
```

---

## P3 — Verify + Escalate on Quality

### Purpose

P3 closes the verification loop: cheap-model results are accepted ONLY when an
objective check passes (never on the model's self-report). Failed checks trigger
escalation carrying the done-frontier so the stronger model resumes, not restarts.
A lightweight judge integration adds the `result_quality` signal to the ledger.

### Steps

**P3-1 — Enforce acceptance check on every milestone**

*File*: `src/chuzom/tools/agentic.py` — after `_extract_plan_json` succeeds, add
schema validation: any milestone whose `"acceptance"` key is null, missing, or
`{"type":"canary","marker":""}` (trivially gameable) is rejected with `PlanRejected`.

The planner prompt (`_planner_prompt()`, line 32) already lists the 4 check types
(`cmd`, `lint`, `diff`, `canary`). The validator enforces them structurally.

**P3-2 — Result-quality signal**

*File*: `src/chuzom/agentic/telemetry.py` — extend `record_delegation_savings()`:

```python
quality = 1.0 if (outcome == "complete" and escalation_count == 0) else \
          0.5 if (outcome == "complete") else 0.0
record_routing_event(..., result_quality=quality, verification_pass=(outcome == "complete"))
```

**P3-3 — Done-frontier escalation validation**

`src/chuzom/agentic/adapters.py` `pack_prompt()` (line 49) already inserts
`ALREADY COMPLETED — build on these, do NOT redo:` with frozen milestone IDs.
`src/chuzom/agentic/engine.py` freezes passed milestones (monotonic escalation
guarantee in module docstring). Add an integration test that validates the
end-to-end path (see Tests below).

**P3-4 — Budget-exhausted surface behavior**

*File*: `src/chuzom/tools/agentic.py` `llm_delegate()` — before calling
`run_delegation`, check if `budget_usd <= 0` and surface immediately. Inside
`run_delegation`, `engine.py` already emits `Outcome.BUDGET_EXHAUSTED`; ensure
that outcome serializes to a clear JSON error, not a silent empty result.

**P3-5 — Lightweight judge integration (optional per milestone)**

Add optional `judge_prompt: str | None` field to `Milestone` in
`src/chuzom/agentic/ledger.py`. After a `cmd_check` passes, if `judge_prompt`
is set, route a quick `llm` call (cheap Haiku/local model) with the command
output and `judge_prompt`. Judge result updates `result_quality` in the ledger.
This is opt-in; no milestone is required to use it.

### Behavior introduced / changed

- Every milestone has an objective acceptance check (schema-enforced).
- `result_quality` is recorded for every routed execution in the quality ledger.
- Done-frontier is validated end-to-end: escalating tier resumes at the first
  unfrozen milestone (not from scratch).
- Budget exhaustion surfaces honestly with a JSON error.

### North Star motion

Satisfies rubric items 4 (verification) and 5 (escalation). Without P3 a weak
model can "complete" a task by producing plausible output that passes only a
canary check (see RISKS doc, R4 — Verification Gaming).

### Tests to add

```
tests/test_engine_p3.py           — milestone with null acceptance → PlanRejected; done-frontier: tier-1 passes A + fails B; tier-2 gets A frozen + passes B → COMPLETE
tests/test_agentic_telemetry.py   — COMPLETE first-try → quality=1.0; COMPLETE with escalation → 0.5; SURFACED → 0.0
tests/test_budget_exhaustion.py   — budget=0 → immediate surface; budget exceeded mid-run → BUDGET_EXHAUSTED; no partial silent completion
```

---

## P4 — Unify Tool Surface

### Purpose

P4 collapses 73 tools to 11 and eliminates the structural enforcement dead-end
(hook emits `llm_analyze` → completion-only → no escape when task needs tools).

### Steps

**P4-0 (Phase 0, start with P0) — Register 1.0 aliases (non-breaking)**

*File*: each tool module's `register()` function:

```python
# text.py
mcp.tool(name="llm")(llm_dispatcher)   # dispatches by task= param

# agentic.py — already done in P1
mcp.tool(name="llm_act")(llm_delegate)

# admin.py / dashboard.py / subscription.py
mcp.tool(name="chuzom_status")(status_dispatcher)   # view= param
mcp.tool(name="chuzom_admin")(admin_dispatcher)     # action= param
mcp.tool(name="chuzom_session")(session_dispatcher) # action= param
```

Dispatchers are thin wrappers that map `task=` / `view=` / `action=` to existing
implementations. No behavior changes.

**P4-1 — Fix enforcement lock policy**

*File*: `src/chuzom/hooks/enforce-route.py`:

Extend the "llm_* tool → allowed" check to include `llm_act`, `llm`, `chuzom_status`,
and `chuzom_approve` as unconditionally permitted regardless of pending routing state:

```python
_ALWAYS_PERMITTED = frozenset({
    "llm", "llm_act", "chuzom_status", "chuzom_approve",
})
# In the PreToolUse handler:
if tool_name in _ALWAYS_PERMITTED:
    return _allow()
```

`llm_act` is now a valid resolution of ANY route hint — the structural dead-end
from TOOL_SURFACE_PROPOSAL.md §P3 is eliminated.

**P4-2 — Update hint format**

Change hint from `REQUIRED: llm_analyze` to:
```
⚡ MANDATORY ROUTE: analyze/moderate → call llm(task="analyze") [or llm_act if tools needed]
```

**P4-3/4 — Deprecation (0.10.x) + Removal (1.0)**

Old tool names emit deprecation notices for 2 minor versions then are de-registered.
Add `chuzom hooks check` CLI command to detect hook files still emitting legacy names.

### Tests to add

```
tests/test_tool_surface.py   — all 11 new names registered; dispatchers route by param correctly
tests/test_enforce_lock.py   — route lock active + llm_act call → allowed; route lock active + Bash → blocked
```

---

## P5 — Agent-Step Parity + Reliability

### Purpose

P5 makes every agent sub-step go through the identical 7-step North Star pipeline:
intercept → classify → provision → execute → verify → escalate → measure.
F5 (P0) must be verified working before P5 begins.

### Steps

**P5-1 — Classify agent steps**

*File*: `src/chuzom/hooks/agent-route.py` — when a sub-agent spawn is intercepted,
call `classify_prompt(goal)` (P2 function). Use the resulting `RoutingDecision`:
- `needs_tools=True` → emit `llm_act(goal=..., cwd=cwd, context=ctx)`.
- `needs_tools=False` and task is Q&A → emit `llm(task=..., prompt=goal)`.
- `complexity == "complex"` or confidence < 0.5 → allow Claude sub-agent (escalation top).

**P5-2 — Provision agent steps identically**

Apply the same `build_context_block(session_id)` + `os.getcwd()` injection from P1.
Read `CLAUDE_SESSION_ID` from the hook environment to find the correct session store.

**P5-3 — Record agent steps in quality ledger**

Extend `record_routing_event()` with `is_agent_step: bool`. Agent-step events appear
as a separate population in `chuzom_status(view="routing_quality")`.

**P5-4 — Depth circuit breaker end-to-end validation**

Add integration test: spawn 3 agents in sequence with depth-release hook firing
between each → 4th spawn is approved (live depth == 0). This is the acceptance
gate for P5.

### Behavior introduced / changed

- Every agent sub-step is classified and routed to the cheapest capable tier.
- Tool-needing agent steps go to `llm_act` (MGEE) — same as user prompts.
- Simple Q&A agent steps go to `llm` (cheap completion).
- Agent step metrics are recorded separately.
- Depth circuit breaker reflects live nesting.

### North Star motion

P5 completes the North Star for agent steps. After P5 the entire system — user
prompts and every agent sub-step — goes through the same pipeline. No work path
is exempt from routing.

### Tests to add

```
tests/test_agent_route_p5.py     — goal classified → needs_tools=True → llm_act; Q&A → llm; complex → Claude
tests/test_agent_depth_e2e.py    — 3 spawns + 3 releases → 4th spawn approved (integration)
tests/test_routing_ledger_p5.py  — agent step events recorded with is_agent_step=True; separate from user events
```

---

## Ordering Dependencies

```
P0  ─────────────────────────────────────────┐
P4 Phase 0 (aliases, non-breaking) ──────────┤ both merge together
                                             ↓
                                             P1 (requires smart enforcement)
                                             ↓
                                             P2 (requires llm_act wired)
                                             ↓
                                             P3 (requires P2 decision + MGEE end-to-end)
                                             ↓
                                             P5 (requires P3 quality gate + F5 verified)
                                             ↓
                                       P4 Phase 1 (deprecation — all functionality confirmed)
                                             ↓
                                       P4 Phase 2 (1.0 removal)
```

---

## Measurement Validation by Phase

The routing-quality ledger is the objective gate for each phase transition.

| After | Expected ledger signal |
|---|---|
| P0 | All 16 fields recorded; baseline `mis_route` and `routing_accuracy` established |
| P1 | `routed_tier` shows "codex" for operational prompts; `tool_exec_success` > 0; `cost_usd << baseline_usd` |
| P2 | `needs_tools` populated; `context_scope` non-null; `mis_route` rate decreases |
| P3 | `verification_pass` reflects real check outcome; `escalation_count > 0` for tasks that needed it; `result_quality` > 0 |
| P4 | No events referencing legacy tool names after migration |
| P5 | `is_agent_step=True` events appear; agent-step escalation rate visible separately |

**North Star reached when** (over a representative week of sessions):
`mis_route < 10%` · `routing_accuracy > 80%` · `task_completion > 90%` · `cost_usd / baseline_usd < 0.30`
