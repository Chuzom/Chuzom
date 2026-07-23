# Chuzom Agentic Router — Design & Implementation Plan

> Status: DESIGN / IN PROGRESS (branch `feat/agentic-router`)
> Goal: make **every** Chuzom routing decision a *full agentic delegation* — the router
> hands the task to the cheapest **capable, tool-using agent** that shares the session's
> live context, gated by **objective milestone acceptance criteria**, escalating to a
> stronger model on failure **without redoing achieved milestones**, never getting stuck,
> and streaming transparent progress to the user.

---

## 1. Motivation

Today Chuzom's `llm_*` MCP tools are **completion calls** (text → text): one-shot, no tool
loop, no filesystem, no access to live repo/session state. That's fine for *cognition*
(analyse/generate/summarise) but it means the router can't run agentic work on a cheaper
model — so anything that needs tools falls back to the expensive orchestrator, and the
hard-enforcement hook that *demands* routing ends up blocking prompts a stateless model
can't serve.

**The fix:** routing delegates to an **agent runtime** (Codex CLI / Gemini-Antigravity /
a local ReAct harness over Ollama) that has tools + injected session context, executes a
real tool loop, is verified against objective acceptance checks, and escalates cleanly.
The value proposition — *save subscription/API tokens by doing real work on cheaper
policy models while preserving quality* — only holds if delegation is agentic.

## 2. What already exists (reuse, don't rebuild)

| Piece | File / tool | Role in the new design |
|---|---|---|
| Session context accumulator | `session_store.py` (JSONL bus) | The shared **context bus** — "what happened up to now" |
| Session-level agent routing | `llm_select_agent` | Seed of agentic routing (currently whole-session only) |
| Agent session lifecycle + budget caps + lineage rollup | `chuzom_agent_start_session`, `agents/session.py`, `lineage/` | Sub-agent lifecycle, cost accounting, hard budget ceiling |
| Codex adapter | `codex_agent.py` | Codex CLI *is* a tool-using agent already |
| Classifier | `classifier.py` / `classify.py` | Task-type × complexity → +new reversibility & per-milestone difficulty axes |
| Context assembly + compaction | `context.py` (`build_context_messages`), `compaction.py` | `pack_context()` foundation |

The gap is granularity + a checkpointed escalation engine — not a greenfield rewrite.

## 3. Architecture — the delegation loop

`llm_delegate(task, task_type)` replaces the completion call:

```
llm_delegate(task):
  ledger = PLAN(task)              # decompose → ordered milestones + acceptance checks
  while not ledger.complete():
    m      = ledger.next_pending()
    tier   = ROUTE(m, ledger)      # cheapest tier likely to clear THIS milestone
    ctx    = PACK_CONTEXT(ledger)  # live transcript + repo state + frozen done-ledger
    result = RUN_AGENTIC(tier, m, ctx, tools, budget)   # real tool loop
    if VERIFY(m, result):          # OBJECTIVE acceptance check (never self-report)
        ledger.freeze(m, result)   # advance done_frontier, write artifacts to bus
    else:
        ESCALATE(ledger)           # tier+1, same milestone, carry frozen ledger forward
  WRITEBACK(ledger)                # sync to context bus for continuity
  return ledger.result()
```

### 3.1 Backend adapters (uniform interface)
```
run_agentic(task, ctx, tools, budget) -> {result, actions[], new_events[], confidence}
```
- **Codex adapter** — shell to `codex` in-repo, inject packed context, native tools, capture stdout + `git diff`. *Highest near-term ROI (gpt-5.x is a capable agent).* 
- **Gemini/Antigravity adapter** — same pattern (individual Gemini CLI tier is EOL → Antigravity).
- **Local ReAct harness** — tool-loop over Ollama's native tool-calling API (tool-capable models e.g. `qwen2.5-coder`), with a sandboxed tool executor (bash / read / write / gh). *The one genuinely new build.*

## 4. Milestone-Gated Escalating Execution (MGEE)

### 4.1 Data model
```python
Milestone = {
  "id": str, "description": str,
  "acceptance": AcceptanceCheck,     # objective: test cmd | lint | diff assertion | validator
  "status": "pending|in_progress|done|blocked",
  "deps": [milestone_id],            # DAG edges (default: linear chain)
  "artifacts": [ ... ],              # diffs, files, command outputs produced
  "achieved_by": tier | None,        # which tier cleared it
  "attempts": [ {tier, ok, reason, cost} ],
}

TaskLedger = {
  "goal": str,
  "milestones": [Milestone],         # topologically ordered
  "done_frontier": set[milestone_id],# frozen, never re-executed
  "current_tier": int,
  "budget": {cap, spent},
  "events": [Event],                 # the transparency stream
}
```

### 4.2 Acceptance checks (load-bearing)
A milestone is `done` ONLY when an **objective, executable** check passes:
- `cmd`: a shell command whose exit 0 = pass (e.g. `pytest tests/x.py::y`)
- `lint`: ruff/mypy clean on the touched files
- `diff`: the produced diff matches a structural assertion (file created, symbol present)
- `canary`: an expected marker is present in the output
- `validator(fn)`: a pure predicate over artifacts

> **Audit lesson (hard rule):** *never* accept a milestone on the executing model's
> self-report. "0/16 hermetic tests asserted real execution" — same trap. The check is
> both the definition-of-done AND the escalation trigger; if it's subjective, the flow loops.

### 4.3 Escalation state machine
```
states:  PLAN → ASSIGN → EXECUTE → VERIFY → {FREEZE | RETRY | ESCALATE | REPLAN | SURFACE}
                                     │
  VERIFY.pass  ─────────────────────┴─→ FREEZE ─→ (next milestone) ASSIGN
  VERIFY.fail (deterministic, attempts<K at tier) ─→ RETRY ─→ EXECUTE
  VERIFY.fail (attempts==K at tier, tier<TOP)     ─→ ESCALATE(tier+1) ─→ EXECUTE (same m)
  VERIFY.fail (tier==TOP, attempts==K)            ─→ REPLAN(tail) once ─→ PLAN(remaining)
  REPLAN already used, still failing at TOP       ─→ SURFACE(user, failing criterion)
  budget/time exhausted at any point              ─→ SURFACE(partial + question)
  VERIFY.fail (flaky / non-reproducible)          ─→ re-run once, no attempt/escalation
```

### 4.4 Tier ladder (example, policy-driven)
`0: local ReAct (qwen2.5-coder) → 1: codex/gpt-5.x → 2: claude_code (main loop / opus)`
Router picks the *lowest* tier whose capability ≥ the **milestone's** difficulty (not the
whole task's). Reversibility raises the floor (irreversible ops never start below the tier
allowed to perform them, and pass through the gate in §4.5).

### 4.5 Reversibility gate
Actions are classified by reversibility. A milestone whose acceptance requires an
**irreversible** action (`push`, `merge`, `delete`, external send) cannot auto-`FREEZE`:
it runs edits in a **git worktree**, the diff/action is verified, and the irreversible step
is either main-loop-executed or human-confirmed before the milestone is marked done.

## 5. Anti-stuck invariants (the "flow, never blocked" properties)

| Invariant | Mechanism |
|---|---|
| **Termination** | Escalation is **monotonic** over a **finite** tier ladder; bounded `K` attempts per (milestone, tier). Worst case = SURFACE, never infinite loop. |
| **Capable top rung** | The top tier is the capable orchestrator; if it can't meet a milestone the flow **surfaces the exact failing criterion** to the user, not a silent stall. |
| **No rework** | `done_frontier` freezes passed milestones; escalated models receive them as read-only context + artifacts and resume at the frontier. |
| **No escalation thrash** | Only **deterministic** failures escalate; flaky/non-reproducible checks re-run once and don't count. |
| **Decomposition escape hatch** | The remaining tail can be **re-planned once** if a milestone is structurally unmeetable. |
| **Budget safety** | Global budget + wall-clock cap (reuse agent-session caps); exhaustion → partial progress + question, never hang. |
| **Independent progress** | Milestones are a **DAG**; a blocked node doesn't stall ready siblings. |

## 6. Transparency — user-facing event stream

Every state transition emits a structured event (rides the status-line/banner, or printed):
```
🗺  Plan: 4 milestones  [M1 scaffold · M2 impl · M3 tests green · M4 lint clean]
⚙  M1 scaffold      → 🦙 qwen2.5-coder (local)   ✓ passed (files created)
⚙  M2 impl          → 🦙 qwen2.5-coder (local)   ✗ acceptance failed: 2/5 cases
↑  escalating M2    → ⬜ codex/gpt-5.5   (M1 kept, resuming at M2)
⚙  M2 impl          → ⬜ codex/gpt-5.5           ✓ passed (5/5 cases)
✅ Task complete on codex (1 escalation) · saved vs Opus $X · ledger persisted
```
Each line states **which milestone · which model · pass/fail · why on escalation**.

## 7. Implementation plan (phases → milestones)

- **P0 — Context bus** (extend existing): `pack_context()` + bidirectional event append. *(≈done in `session_store.py`.)*
- **P1 — MGEE engine (deterministic core)** — `TaskLedger`, state machine, escalation, checkpoint/carry-forward, event emitter. **Testable with FAKE agents** (no real models). *Build & prove FIRST.*
- **P2 — Acceptance-check runners** — `cmd/lint/diff/canary/validator`, reproducibility (flaky re-run) logic.
- **P3 — Backend adapters** — Codex first, then local ReAct harness, then Gemini/Antigravity. Uniform `run_agentic()`.
- **P4 — `llm_delegate` MCP tool + router integration** — wire classifier (per-milestone difficulty + reversibility), tier ladder from the policy/profile.
- **P5 — Reversibility gate + worktree isolation + verifier.**
- **P6 — Enforcement-hook rewire** — hard-enforce → *delegate* instead of *block* (respect the context-dependent signal).
- **P7 — Savings/telemetry** — per-tier/per-escalation cost accounting into the existing savings ledger.

## 8. Scenario & edge-case test matrix (the loop's target)

The **P1 deterministic core is verified with FAKE agents** (stubs whose pass/fail/behaviour is
scripted), so the *flow* is verified before any real model is involved.

| # | Scenario | Assert |
|---|---|---|
| S1 | Happy path — all milestones pass at tier 0 | done; 0 escalations; no rework |
| S2 | Single escalation — M2 fails t0, passes t1 | M1 frozen & NOT re-run; resumes at M2; ledger records escalation |
| S3 | Multi-escalation to top | passes at TOP; earlier milestones untouched |
| S4 | Top-tier failure | SURFACE with exact failing criterion; NOT stuck; partial ledger returned |
| S5 | Flaky acceptance check | re-run once; no false escalation; no attempt consumed |
| S6 | Model loops / no progress | bounded K attempts → escalate; no infinite loop |
| S7 | Budget exhaustion mid-task | SURFACE partial + question; no hang; spent ≤ cap |
| S8 | Bad decomposition | REPLAN tail once; then proceed or SURFACE |
| S9 | Carry-forward integrity | escalated agent receives frozen done-ledger; provably does not re-execute done milestones |
| S10 | Context continuity | milestone N sees N-1's artifacts in packed context |
| S11 | Irreversible milestone (merge/push) | gated: worktree + verify + confirm before FREEZE |
| S12 | DAG independence | blocked node doesn't stall ready siblings; siblings complete |
| S13 | Escalation thrash guard | deterministic-only escalation; repeated flaky ≠ escalate |
| S14 | Savings accounting | cheaper-tier completion records positive saving vs Opus baseline |
| S15 | Transparency completeness | every transition emits a well-formed event (schema-validated) |
| S16 | Termination property (fuzz) | randomised fake-agent pass/fail schedules ALWAYS terminate (success or SURFACE) |

**Quality bars for "done":** no scenario can hang or loop (S4/S6/S7/S16), tokens route to the
cheapest capable tier with escalation only on real failure (S1/S2/S14), and correctness is
gated by objective checks so escalation yields high-quality results (S9/S11 + §4.2).

## 9. Rollout / MVP

MVP = **P1 (MGEE core, fake-agent-tested) + P2 + P3-Codex + P4** → self-contained coding
tasks run on Codex-as-agent with full session context, milestone-gated, escalating to
Claude only on real failure. Local ReAct harness (P3) and enforcement rewire (P6) follow.

---
_Implementation proceeds TDD: the §8 matrix is written as tests against the P1 core FIRST
(deterministic, fake agents), then real adapters are dropped in behind the same interface._
