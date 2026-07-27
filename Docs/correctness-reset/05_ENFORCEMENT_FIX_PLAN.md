# Chuzom Correctness Reset — 05. Enforcement-Friction Fix Plan (North-Star-aligned)

Plan to close `04_ENFORCEMENT_FRICTION_GAPS.md` (GAP-ENF-1..4) **in accordance with the
North Star**, not against it. Folded into the reset as **Phase 3.5**.

## North-Star check — the first draft of this plan was WRONG

The North Star (`NORTH_STAR.md`) requires: **every request is routed, no bypass**, to the
*cheapest tool-capable* model via `llm_act`/MGEE (provisioned with cwd + files + repo state),
with Claude only at the **top of the escalation ladder**. Its explicit anti-goals include
"exempting file/repo/operational prompts straight to Claude instead of routing them to a
tool-capable model."

The first draft of this plan proposed to **exempt** local execution (git/pytest/gh) from
routing. That is a **North-Star violation** — it drops routing ("route every time") and is
literally the anti-goal above. **Rejected.**

**Correct diagnosis.** The friction (GAP-ENF-1/2) has the *same* root cause as P1: execution
work was routed to a **text-only door** (`llm`/`llm_query`/`llm_research`) that structurally
cannot run bash/git/tests — a dead-end. The fix is the same family as P1's option 1:
**route it to the door that CAN execute (`llm_act`), with context provisioned** — never exempt,
never text-only.

---

## Principle for Phase 3.5

> Routing still happens on **every** request (INTERCEPT, no bypass). What changes: a request
> whose completion needs local execution or repo context is CLASSIFIED needs-tools=true and
> routed to the **tool-capable door** (`llm_act`/MGEE), PROVISIONED with cwd + repo state +
> session context, and only **escalates to Claude** on genuine need. Enforcement must (a) name
> the tool-capable door for such work, never a text-only one, and (b) offer a clean,
> non-punitive escalation — never a dead-end and never friction-by-violation-count.

INV-ROUTE-006 (revised, North-Star-aligned):

> **No enforcement path may route execution/repo work to a door that cannot perform it.** When
> CLASSIFY marks needs-tools=true (local command execution, repo file ops, verification), the
> enforced door MUST be tool-capable (`llm_act`/`llm_delegate`/MGEE) and MUST be provisioned
> with the working directory and repo state. A text-only completion door (`llm_query`/
> `llm_research`/`llm`) may never be the enforced door for such a request.

---

## Root causes (code-traced) and North-Star-aligned fixes

| Gap | Root cause | North-Star fix (NOT exemption) |
|---|---|---|
| GAP-ENF-1 | Execution-heavy work classified `code`/`coordination` was routed to the **text-only** door; `LOCAL_BASH_EXEMPT` (`enforce-route.py:824`, excludes `code`) only papered over it by dropping enforcement | **CLASSIFY** execution/repo requests as needs-tools=true → **route to `llm_act`** (tool-capable). Enforcement directive names `llm_act`. The operational→`llm_act` redirect already exists (`test_consolidated_operational_names_llm_act`); extend it to code/coordination requests that need execution. |
| GAP-ENF-2 | Context-dependent prompt still got a hard `research → call llm_research FIRST` directive; `llm_research` is text-only and blind to the repo → would fabricate | **PROVISION** (North-Star step 3): route the context-dependent request to `llm_act` **with cwd + repo state + session context injected**, so the routed model isn't blind. Fabrication risk comes from the *wrong door* + *no provisioning*, not from routing itself. If the task genuinely needs Claude, ESCALATE cleanly. |
| GAP-ENF-3 | Classifier re-rolls task_type per turn | Stable **needs-tools / repo-context** signal so execution/agentic continuation consistently routes to the tool-capable door (not flip-flopping doors). |
| GAP-ENF-4 | `NATIVE_LOCAL_EXEMPT` excludes `code` | Same as ENF-1: local file tools during a tool-capable routed execution are part of that execution; the fix is routing to `llm_act` (which owns those tools), not per-tool exemption on Claude. |

**Note on the pre-existing `LOCAL_BASH_EXEMPT`.** It is itself a North-Star *compromise*
(lets Claude run the command instead of `llm_act`). Phase 3.5 does not widen it; the North-Star
target is that such execution runs inside `llm_act`. Where enforcement can't yet route to a
genuinely-capable `llm_act` (e.g. tasks that legitimately need Claude), the correct behavior is
**clean escalation to the top of the ladder**, not a dead-end and not a violation-count penalty.

---

## Work items (Phase 3.5 — each its own tested, pushed increment)

### ENF-FIX-1 — tool-capable door for execution work (GAP-ENF-1) — highest priority — ✅ DONE
- CLASSIFY: a request needing local command execution / repo file ops → needs-tools=true.
- Enforcement: the enforced door for such requests is `llm_act` (tool-capable), never a
  text-only door. Extend the operational→`llm_act` redirect to code/coordination-with-execution.
- **Test:** an execution request under hard enforcement yields a directive naming `llm_act`
  (not `llm`/`llm_query`); calling `llm_act` clears the lock. A text-only door is never named
  for a needs-tools request.
- **Implemented:** a SEPARATE high-precision signal `execution_signal.detect_execution`
  (execution/VCS verb + concrete repo/command object, reusing `operational_signal`'s
  explanatory-lead / content guards) — **NOT** by broadening `detect_operational`, which would
  over-route prose. `enforce-route.py` folds it into the redirect: a `code`/`coordination`
  request that needs execution but has no verification cue now names `llm_act`; an explanatory
  prompt with the same task_type still names the text-only door (the signal, not the task_type,
  gates the redirect); `CHUZOM_DELEGATE=off` disables it; calling `llm_act` clears the lock.
  Tests: `test_execution_signal.py` (24, bidirectional) + `test_enf_fix1_execution_door.py`
  (4, integration). The operational redirect (`test_consolidated_operational_names_llm_act`) is
  unchanged.

### ENF-FIX-2 — PROVISION context on context-dependent routing (GAP-ENF-2) — ✅ DONE
- When `_is_context_dependent(prompt)`, route to `llm_act` **with cwd + repo state + session
  context** (North-Star PROVISION), instead of emitting a `call llm_research FIRST` text-only
  directive. No blind text-only directive on context-dependent prompts.
- **Test:** a context-dependent prompt's enforced directive names a tool-capable, provisioned
  door — never `llm_research`/`llm_query` FIRST-and-ONLY.
- **Implemented:** the GAP-ENF-2 hard-directive dead-end was already closed (the
  context-dependent branch in `auto-route.py` sets `write_pending=False` + an advisory
  directive, and `_is_context_dependent` fires correctly on the logged repo-continuation
  prompts) — so this increment (a) **regression-locks** that behaviour (no `FIRST and ONLY` /
  `HARD ENFORCEMENT` on a context-dependent prompt), and (b) adds the North-Star **door
  alignment**: when the context-dependent prompt ALSO trips ENF-FIX-1's execution signal, the
  advisory names the provisioned tool-capable door `llm_act(context=…)` instead of a text-only
  one; a non-execution context prompt keeps its text-only suggestion (no over-routing).
  Tests: `test_enf_fix2_context_provisioned_door.py`.

### ENF-FIX-3 — clean escalation to Claude (no friction-by-violation-count)
- Replace the punitive "violation 3/4 → auto-pivot after retries" flow with an explicit,
  first-class escalation: when the routed tool-capable door genuinely can't complete (or the
  task needs Claude), escalate cleanly (single signal), recorded in the ledger as an escalation
  — the North-Star ladder, not a trap.
- **Test:** an escalation path exists that reaches Claude in one step and records an escalation
  event, without N wasted blocked retries.

### ENF-FIX-4 — stable needs-tools/repo-context classification (GAP-ENF-3)
- A stable signal (repo present + needs-tools) that pins a request to the tool-capable door
  consistently across a session, instead of re-rolling task_type/door each turn.
- **Test:** successive execution-continuation prompts route to the same tool-capable door.

---

## Integration into the reset plan — phases (added to the task list)

- **Phase 3** — surface migration (INV-COST-004) [in progress; #161 reconcile primitive]
- **Phase 3.5 — Enforcement→tool-capable-door (this doc):** ENF-FIX-1 → ENF-FIX-2 → ENF-FIX-3 →
  ENF-FIX-4, each with a regression test; adds/revises INV-ROUTE-006.
- **Phase 3.6** — AC-4 / AC-5 accounting cleanup
- **Phase 7** — mutation testing (add INV-ROUTE-006 + ENF tests to finding→test matrix)
- **Phase 8** — control-group benchmark (llm_act tool-capable execution is what makes this
  measurable — directly tied to Phase 3.5)
- **Phase 9** — gate re-evaluation + final verdict

**Gate impact:** Phase 3.5 strengthens the North Star (routes MORE work to the cheapest
*capable* door instead of dead-ending or exempting), extends Gate 11 (no dead-ends) to execution
work, and directly serves the "route executions not completions" core. It does **not** change
the release verdict — the benchmark + two-audit rule remain the blockers.

**Correction on the earlier increment:** the exemption-based ENF-FIX-1/2 edits were reverted as
North-Star-negative before commit; only this North-Star-aligned plan proceeds.
