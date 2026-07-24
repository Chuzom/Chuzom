# chuzom 0.9.1 Remediation Plan

> Generated from the routed self-audit of 0.9.0 (agentic router + classifier-selectable ENFORCED delegation).
> Production code is unchanged — this is planning only.

---

## F5 — Agent-Depth Circuit Breaker: Lifetime Counter, Not Live Nesting

**Severity**: MEDIUM (live bug)

**Root Cause**
`src/chuzom/hooks/agent-route.py` increments `agent_depth_<session>.json` on every non-Explore, non-routed-DIRECT agent spawn (line 908). The release hook `src/chuzom/hooks/agent-depth-release.py` exists and correctly decrements by 1, but it is **not registered** under `SubagentStop` in `~/.claude/settings.json` — `grep "SubagentStop" ~/.claude/settings.json` returns nothing. The only `PostToolUse[Agent]` hook registered is `chuzom-cc-usage-track.py`. Result: after 3 lifetime agent spawns in a session, ALL further spawning is permanently blocked, even though all three may have long since completed.

The DIRECT and CLI-delegation paths do correctly roll back depth (lines 936-966), but the routed-spawn path (line 929, `_emit_model_pin`) does not — it depends entirely on the missing SubagentStop hook.

**Concrete Fix**

1. Register `agent-depth-release.py` under `SubagentStop` in `~/.claude/settings.json`:
   ```json
   "SubagentStop": [
     {
       "matcher": "",
       "hooks": [{
         "type": "command",
         "command": "/Users/yali.pollak/.local/share/uv/tools/chuzom-router/bin/python /Users/yali.pollak/.claude/hooks/chuzom-agent-depth-release.py"
       }]
     }
   ]
   ```
2. Add a startup self-check in `src/chuzom/hooks/agent-route.py` (or a separate `chuzom hook-health` CLI command) that reads `~/.claude/settings.json`, finds the `SubagentStop` section, and warns if `agent-depth-release` is absent.
3. Add a repair helper (`chuzom hooks fix`) that writes the missing block automatically.

**Tests to Add**
- `tests/test_agent_route_hook.py`: depth increments on PreToolUse approval, then decrements when release hook fires (simulate by calling `_write_agent_depth` directly in sequence).
- `tests/test_agent_route_hook.py`: direct-path and CLI-delegation paths roll depth back to `current_depth` (not `current_depth + 1`).
- New `tests/test_hook_health.py`: fixture `settings.json` missing `SubagentStop` → health check reports unhealthy; fixture with correct registration → healthy.
- Integration simulation: call agent-route main() 3× with matching depth-release calls → 4th call is still approved because live depth returned to 0.

**Effort**: S (hours — hook registration is a one-liner; tests are straightforward)

**Gates 0.9.1?**: **YES** — Live circuit-breaker bug that permanently blocks agents after 3 spawns per session. Must ship in 0.9.1.

---

## F1 — `operational_signal` Residual False Positives

**Severity**: MEDIUM

**Root Cause**
`src/chuzom/operational_signal.py` `_CONTENT_OBJECT_RE` (lines 50-55) blocks prose deliverables but omits educational/assessment nouns: `quiz`, `exam`, `test plan`, `test-plan`, `worksheet`, `lesson plan`, `curriculum`, `scenario`, `exercise`. Because `generate` is a change verb and `_VERIFY_CUE_RE` (lines 34-46) includes `regression test`, `unit test`, etc., prompts like "Generate a quiz that tests CI concepts" match verb=`generate` + cue=`tests` with no content guard → hard-routed to `llm_delegate`. There is also no software-context third signal, so non-software prompts can fire with any code-sounding vocabulary.

**Concrete Fix**

In `src/chuzom/operational_signal.py`:

1. Extend `_CONTENT_OBJECT_RE` to include assessment/education nouns:
   ```python
   _CONTENT_OBJECT_RE = re.compile(
       r"\b(blog\s+post|article|essay|poem|summary|explanation|paragraph|sentence|"
       r"story|report|guide|advice|email|caption|rubric|itinerary|checklist|"
       r"tutorial|readme\s+section|documentation\s+for|"
       # NEW — education/assessment objects
       r"quiz|exam|test[\s-]plan|worksheet|lesson[\s-]plan|curriculum|"
       r"scenario|exercise|flashcard|study\s+guide|syllabus)\b",
       re.IGNORECASE,
   )
   ```

2. Add a `_SOFTWARE_CONTEXT_RE` third signal (HIGH precision — require at least one unambiguous software indicator):
   ```python
   _SOFTWARE_CONTEXT_RE = re.compile(
       r"\b(src/|tests?/|\.py\b|\.ts\b|\.go\b|\.rs\b|\.tsx\b|\.js\b|"
       r"repo|codebase|module|function\b|class\b|endpoint|API|"
       r"pytest|unittest|CI|failing\s+test|test\s+suite|lint|mypy|"
       r"refactor|migration|pull\s+request|PR\b|branch|commit)\b",
       re.IGNORECASE,
   )
   ```

3. In `detect_operational`, require all three (change verb + verify cue + software context):
   ```python
   if verb_m and cue_m and _SOFTWARE_CONTEXT_RE.search(p):
       ...
   ```
   False negatives (missing software context on genuine tasks) are explicitly acceptable per the spec; users can always call `llm_delegate` directly.

**Tests to Add**

Add to `tests/test_operational_signal.py`:

False positives (must NOT fire):
```python
"Generate a quiz that tests CI concepts",
"Generate a regression test plan",
"Write a test-plan for the login feature",
"Create a worksheet on pytest fixtures",
"Generate an exam on Python syntax",
"Write a lesson plan on continuous integration",
"Create a scenario for testing user onboarding",
```

Positive controls that must still fire (have software context):
```python
"Implement the login fix in src/auth/login.py and run the regression tests",
"Update the API endpoint and verify the unit tests pass",
"Refactor the codebase and make sure CI is green",
"Fix the failing pytest suite and confirm exit 0",
```

**Effort**: S (hours — regex extension + test additions)

**Gates 0.9.1?**: **YES** — False positives drive a HARD route; precision matters more than recall.

---

## F2 — Planner Intermittency (~25% non-JSON failures)

**Severity**: MEDIUM

**Root Cause**
`src/chuzom/tools/agentic.py` `_extract_plan_json` (lines 44-57) tries fenced JSON first, then bare bracket scan, but has no retry and no JSON repair. `_default_planner` (lines 60-80) makes a single `route_and_call` attempt and raises `PlanRejected` on any parse failure. `src/chuzom/agentic/planner.py` `hybrid_plan` (lines 79-91) has no retry loop. Models frequently return: prose preamble before JSON, truncated JSON, JSON wrapped in extra markdown, or non-JSON explanation of the plan.

**Concrete Fix**

In `src/chuzom/tools/agentic.py`:

1. Improve `_extract_plan_json` with a lightweight pre-parse repair step:
   - Strip everything before the first `[` and after the last `]`.
   - Try `json.loads` on the trimmed string.
   - Return `None` only if no balanced bracket pair can be found.

2. Add a bounded retry loop inside `_default_planner` (max 2 retries):
   ```python
   MAX_PLANNER_RETRIES = 2

   async def planner_model(goal: str) -> list[dict[str, Any]]:
       last_exc: Exception | None = None
       for attempt in range(MAX_PLANNER_RETRIES + 1):
           try:
               resp = await route_and_call(TaskType.QUERY, _planner_prompt(goal), ...)
               plan = _extract_plan_json(getattr(resp, "content", "") or "")
               if plan is not None:
                   return plan
               # repair attempt: re-prompt with stricter correction instruction
               if attempt < MAX_PLANNER_RETRIES:
                   goal = _repair_prompt(goal, getattr(resp, "content", ""))
           except Exception as exc:
               last_exc = exc
       raise PlanRejected(f"planner failed after {MAX_PLANNER_RETRIES + 1} attempts: {last_exc}")
   ```

3. Add `_repair_prompt(goal, bad_response)` in `agentic.py` that prepends the malformed response and asks for JSON-only output:
   ```python
   def _repair_prompt(goal: str, bad_response: str) -> str:
       return (
           f"Your previous response was not valid JSON:\n\n{bad_response[:300]}\n\n"
           f"Original task: {goal}\n\n"
           "Return ONLY a JSON array of milestones. No prose, no markdown fencing."
       )
   ```

**Tests to Add**

Add to `tests/test_agentic_planner.py`:

`_extract_plan_json` cases:
- Clean fenced JSON block → parsed
- Fenced JSON with prose before/after → parsed
- Bare JSON array embedded in text → parsed  
- JSON with prose preamble only (no brackets) → `None`
- Truncated JSON → `None`

Planner retry cases (using injected fake `planner_factory`):
- First response is prose-only, second is valid JSON → succeeds
- First response is truncated, second is valid → succeeds  
- All `MAX_PLANNER_RETRIES + 1` attempts invalid → raises `PlanRejected`
- Malformed schema after successful parse → still raises `PlanRejected` (fail-closed preserved)

**Effort**: M (1-2 days — retry logic + repair prompt + test coverage)

**Gates 0.9.1?**: **YES** — 25% planning failure rate makes `llm_delegate` unreliable as an enforced route.

---

## F3 — MCP Process Fragmentation

**Severity**: LOW (ops)

**Root Cause**
~7 lingering `chuzom` MCP server processes accumulate across restarts. Per-process session-savings counters are in-memory, so savings are undercounted and session totals fragment across processes.

**Concrete Fix**

1. Move session-savings counters to a shared file-backed store under `~/.chuzom/session_savings_<session_id>.json` (already used for depth tracking — same pattern).
2. Add a startup stale-process check: on MCP server start, scan `ps` for other `chuzom` MCP processes with the same session ID older than N minutes and log a warning (do not kill — too risky; let ops decide).
3. Optionally: add `chuzom mcp-cleanup` CLI command that kills stale server PIDs.

**Tests to Add**
- Unit test: two simulated writers update `session_savings_<id>.json` concurrently → aggregated total is correct.
- Process detection test with mocked `psutil`: stale chuzom MCP process identified; current process excluded.

**Effort**: M (1-2 days)

**Gates 0.9.1?**: **NO** — Observability/accounting issue. Does not affect routing correctness. Defer to 0.9.2 unless release is ops-focused.

---

## F4 — Routing-Quality Variance (Deep Analysis → Local Model)

**Severity**: INFO

**Root Cause**
Deep security, architecture, and adversarial-audit prompts can be classified as `analyze/moderate` and routed to `qwen2.5:7b` (local tier-0), which returns shallow output. No complexity floor exists for security/threat-model vocabulary.

**Concrete Fix**

In the classifier or policy layer, add a security/deep-analysis complexity floor: if the prompt contains threat-model, adversarial audit, security review, architecture analysis, root-cause analysis across multiple files → force complexity to `complex` → routes to a stronger external tier (gpt-5.5, Gemini 2.5 Pro, Opus).

```python
_DEEP_ANALYSIS_RE = re.compile(
    r"\b(threat\s+model|adversarial\s+audit|security\s+review|"
    r"root[\s-]cause\s+analysis|architectural?\s+(?:review|analysis|audit)|"
    r"multi[\s-]file\s+(?:review|analysis)|pentest|penetration\s+test)\b",
    re.IGNORECASE,
)
```

**Tests to Add**
- `"Threat model this auth flow"` → complexity forced to `complex`.
- `"Adversarially audit this router predicate"` → not routed to `qwen2.5:7b`.
- `"Summarize this README"` → complexity may remain `simple`/`moderate`.

**Effort**: S (hours)

**Gates 0.9.1?**: **NO** — Quality improvement, not a correctness bug. Include if capacity permits; otherwise 0.9.2.

---

## Known Limitation A — `llm_delegate` Context Injection Gap

**Severity**: MEDIUM

**Root Cause**
As documented in CHANGELOG, `llm_delegate` only passes per-task milestone context to delegated agents — not the broader Claude Code session conversation. Delegated agents therefore lack user intent, prior constraints, and in-session decisions, which can cause them to make incorrect assumptions.

**Concrete Fix**

In `src/chuzom/tools/agentic.py` `llm_delegate`:

1. Accept an optional `context: str | None` parameter that callers (or the enforce-route hook) can populate with a bounded conversation summary.
2. Prepend context to the `task` string passed to `hybrid_plan` and `run_delegation`, bounded at ~500 tokens to avoid flooding the delegated agents.
3. In `src/chuzom/hooks/enforce-route.py`: when constructing the `llm_delegate` call, pass the last N turns of conversation as `context` (already available from hook input).

**Tests to Add**
- `llm_delegate` with `context=` populates milestone task descriptions with context prefix.
- `llm_delegate` with oversized context truncates to the 500-token bound.
- `llm_delegate` with `context=None` behaves identically to 0.9.0 (no regression).
- enforce-route hook: context is extracted from `conversation_history` field and passed to `llm_delegate`.

**Effort**: M (1-2 days)

**Gates 0.9.1?**: **YES** — Without context, enforced delegation can silently produce wrong outputs for tasks requiring session state.

---

## Known Limitation B — Local ReAct Tier-0 Reliability

**Severity**: MEDIUM

**Root Cause**
As documented in CHANGELOG, local tier-0 `ReActAgent` (used in `_default_adapters()` in `src/chuzom/tools/agentic.py` line 86) writes to wrong paths and doesn't always complete. This makes it risky as the first execution tier in an enforced hard-route path.

**Concrete Fix**

Option A (preferred for 0.9.1): Disable tier-0 ReAct for enforced-route tasks; start at tier-1 (Codex). Set `_default_adapters()` to `{1: CodexAdapter(tier=1)}` when the `operational_signal` path is the trigger. Codex escalation already covers it.

Option B (if tier-0 must remain): Add preflight path-grounding in `ReActAgent`:
- Resolve repo root before any edit action.
- Require files to exist before writing.
- Add a completion check: all planned files present + verification command passes.
- Fail to tier-1 on any path-resolution error.

**Tests to Add**
- `ReActAgent` with nonexistent path → fails safely to tier-1, no partial write.
- `ReActAgent` completion check: missing planned file → rejected, escalation triggered.
- `llm_delegate` enforced route uses tier-1 when tier-0 is disabled for operational tasks.

**Effort**: S for Option A (hours); M for Option B (1-2 days)

**Gates 0.9.1?**: **YES if tier-0 remains in enforced path** — Best-effort execution in a HARD-route is a reliability hazard. Option A disables it cleanly.

---

## Recommended Sequence

| # | Item | Why first |
|---|------|-----------|
| 1 | **F5** — register `agent-depth-release.py` under `SubagentStop` | Live bug, one-liner fix, unblocks all subsequent agent testing |
| 2 | **F1** — expand `_CONTENT_OBJECT_RE` + software-context signal | Hard-route precision; prevents false delegation of non-code prompts |
| 3 | **F2** — bounded planner retry + JSON repair | Makes `llm_delegate` reliable enough to enforce |
| 4 | **Limitation A** — context injection for `llm_delegate` | Delegated agents need intent to act correctly |
| 5 | **Limitation B** — disable tier-0 ReAct for enforced tasks (Option A) | Removes best-effort execution from hard-route path |
| 6 | **F4** — deep-analysis complexity floor | Quality improvement; low effort, do in same PR as F1 |
| 7 | **F3** — MCP process fragmentation | Observability only; defer to 0.9.2 |

---

## 0.9.1 Milestone Definition

**0.9.1 ships when:**

- [ ] `agent-depth-release.py` is registered under `SubagentStop`; live depth reflects actual live nesting (not lifetime spawn count); depth-release health check available
- [ ] No known assessment/document/education prompts hard-route through `operational_signal`; `_CONTENT_OBJECT_RE` covers quiz/exam/test-plan/worksheet/curriculum/lesson-plan; software-context third signal required
- [ ] Planner succeeds on common non-JSON model responses via bounded retry (max 2); still fails closed after all retries
- [ ] `llm_delegate` accepts and propagates bounded conversation context; enforce-route hook passes session context
- [ ] Tier-0 ReAct disabled for operational/enforced tasks (Option A) or path-grounded + verified (Option B)
- [ ] All gating tests pass (`pytest tests/test_operational_signal.py tests/test_agentic_planner.py tests/test_agent_route_hook.py tests/test_hook_health.py`)

**Deferred to 0.9.2:**
- F3: MCP process fragmentation / shared savings counters
- F4: Deep-analysis routing-quality floor (unless done in the F1 PR)

---

## Tool-Surface Consolidation (1.0 Direction)

> Full design in [`docs/TOOL_SURFACE_PROPOSAL.md`](./TOOL_SURFACE_PROPOSAL.md).

The current surface has **73 registered tools** (server.py says 60; tool_tiers.py says 41 — the discrepancy is itself a symptom). At 73 tools the MCP schema consumes ~14,000 context tokens per session and forces the `CHUZOM_SLIM` workaround.

**Root fault addressed**: enforcement hooks emit `REQUIRED: llm_analyze`, which is a completion-only tool. Tasks that need tool access are trapped — the mis-routing fault documented in the 0.9.0 audit.

**1.0 target: 11 public tools**, structured by execution shape not internal tier:

| Tool | Shape | Replaces |
|---|---|---|
| `llm` | Text completion (no tools) | `llm_query/research/generate/analyze/reason/code` (6→1) |
| `llm_act` | Agentic tool-loop | `llm_delegate`, `llm_orchestrate` |
| `llm_media` | Image / video / audio generation | `llm_image`, `llm_video`, `llm_audio` |
| `llm_cli` | Provider-native CLI (Codex, Gemini) | `llm_codex`, `llm_gemini` |
| `llm_fs` | File operations | `llm_fs_*` × 4, `llm_edit` |
| `chuzom_route` | Hook-facing routing decision (structured JSON) | `llm_classify`, `llm_route`, `llm_auto`, `llm_reroute` |
| `chuzom_approve` | Human-in-the-loop route approval | `llm_approve_route` |
| `chuzom_status` | All read-only observability (view= param) | 26 tools collapsed |
| `chuzom_admin` | Mutating config/admin actions | 11 tools collapsed |
| `chuzom_session` | Agent session lifecycle | `chuzom_agent_*` × 6 |
| `agoragentic` | External marketplace (feature-flagged) | `agoragentic_*` × 4 |

**Enforcement lock fix**: the 1.0 lock policy always permits `llm_act` and `chuzom_status` while a route hint is active, eliminating the completion-only dead-end. Hooks emit `llm(task="analyze")` not `llm_analyze`.

**Migration path**: Phase 0 (0.9.x) — register 1.0 names as aliases; Phase 1 (0.10.x) — deprecation warnings in old tool responses; Phase 2 (1.0) — remove old names. See full proposal for the complete mapping table (73 → 11).
