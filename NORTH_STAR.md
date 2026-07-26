# Chuzom North Star

> **This is the principle every architectural decision, implementation change, classifier
> update, and new feature in Chuzom is evaluated against. If a change does not move the
> system toward this behavior, it does not ship.**

## The Principle

**Every user request and every agent step is first routed to the most cost-effective model
capable of completing the task at the required quality. The selected model must be able to
perform the _real work_ — local file operations, tool use, command execution, and
verification. The _most capable_ tier is used only when a cheaper model fails to meet the
required quality bar — and "most capable" is defined by the live external model leaderboard,
not by any one vendor. Claude is one candidate on that ladder, not axiomatically the top.**

### Capability is external and live — the leaderboard, not a hardcoded ranking

Which models are "better/most capable" is **not** decided inside Chuzom and is **not** a fixed
"Claude is best" assumption. It is read from a continuously-updated external ranking:

> **https://artificialanalysis.ai/leaderboards/models**

The frontier moves weekly (new Claude, Gemini, DeepSeek, Qwen, Llama, GPT, … releases). The
router's cost/capability ordering — and therefore what sits at the *top* of the escalation
ladder for a given task — must track this leaderboard, so escalation always reaches the current
best-capable model, which may or may not be Claude on any given day. Pinning "Claude = top" is a
North-Star violation the moment another model leads.

## The core reframe: route *executions*, not *completions*

Historically Chuzom routed a **completion** — "return a text answer" (`llm_query/analyze/code`).
Those models can *reason about* work but cannot *do* it, so operational work fell back to
Claude — wasting Claude tokens on work many cheaper models could perform.

The North Star requires routing an **execution**: every routed model runs inside a
**tool-capable harness** (`llm_act` / the MGEE agentic loop) with bash / read / write / git
scoped to the working directory and repository state. That harness is what makes "do real
work" *not* Claude-exclusive. Claude Code's tool loop is no longer special — `llm_act` gives
any model (Ollama, Codex, Gemini, …) the same execution surface.

**The default unit of routing is an execution, not a completion.**

## The end-to-end pipeline (identical for user prompts and agent steps)

```
request (user prompt OR agent step)
  1. INTERCEPT   push hook (user) / agent-route hook (agent step) — every request, no bypass
  2. CLASSIFY    task type · complexity · needs-tools? · which files/context?
  3. PROVISION   give the routed model: working dir (cwd) + file/bash/git tools
                 + repo state + session context (conversation accumulator)
  4. EXECUTE     run on the CHEAPEST CAPABLE tier (local → Codex → … → frontier) via llm_act,
                 where "frontier" = the current best-capable model per the leaderboard
  5. VERIFY      objective acceptance check (cmd/lint/diff/canary) — never self-report
  6. ESCALATE    fail or low-quality → next stronger tier, carrying the done-frontier forward.
                 The TOP of the ladder is the current leaderboard-best model for the task
                 (may or may not be Claude), reached only on genuine need.
  7. MEASURE     record routing accuracy, completion, tool-success, quality, verification,
                 escalation, savings, mis-routes → routing-quality ledger
```

## Evaluation rubric — judge every change against these

A change is North-Star-positive iff it does one or more of:
1. Routes **more** offloadable work to a **cheaper capable** model (without quality loss).
2. Expands what a routed model can **actually do** (tools, files, commands, verification).
3. Improves **classification** so the cheapest *capable* model is chosen more often.
4. Strengthens **verification** so weak results are caught, not shipped.
5. Makes **escalation** cheaper, faster, or better-targeted.
6. Makes routing quality **measurable** rather than assumed.
7. Reduces the cases where work needlessly reaches the frontier (most-expensive) tier —
   whichever model the leaderboard currently ranks there, Claude or otherwise.

A change is North-Star-negative if it: blocks a tool-needing task behind a no-tools tool;
exempts offloadable work straight to the frontier tier; adds surface without adding capability;
assumes a fixed "Claude is best" ranking instead of the live leaderboard; or claims a guarantee
that isn't measured.

## Required measurements (measured, not assumed)

| Metric | Meaning |
|---|---|
| Routing accuracy | did the chosen tier clear the acceptance check on the first try? |
| Task completion success | acceptance check passed |
| Tool execution success | tool-call exit codes inside the agentic loop |
| Result quality | check strength + optional judge |
| Verification success | objective-check pass rate |
| Escalation frequency | escalations / total routes, by tier |
| Cost & token savings | actual vs top-tier baseline |
| Mis-routing | routes that needed escalation ⇒ the initial decision was wrong |

## Anti-goals (things that violate the North Star)

- Enforcing a completion tool (`llm_analyze`/`llm_query`) on a task that needs to *run tools* —
  a structural dead-end.
- Exempting file/repo/operational prompts straight to the frontier tier instead of routing them
  to the cheapest tool-capable model.
- Treating any single vendor (e.g. Claude) as the fixed "best" model instead of reading the
  current capability ranking from the live leaderboard (https://artificialanalysis.ai/leaderboards/models).
- "Guaranteed savings" claims under a default that doesn't enforce routing.
- Routing decisions that are logged but never verified against actual outcome.

## Related

- Phased implementation: `docs/END_TO_END_ROUTING_PLAN.md`
- Tool-surface consolidation (1.0): `docs/TOOL_SURFACE_PROPOSAL.md`
- Near-term remediation: `docs/PLAN_0_9_1.md`
