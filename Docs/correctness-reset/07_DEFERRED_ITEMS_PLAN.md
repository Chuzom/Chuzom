# Chuzom Correctness Reset — 07. Deferred-Items Kickoff Runbook

Execution runbook for the **four deferred items** that remain between the current state
(**RELEASE NOT QUALIFIED**) and a final verdict. Written as a cold-start handoff: a fresh,
uncompacted session should be able to pick this up and run it with no prior context.

> **Why a fresh session.** #8 and #14 mutate core routing logic and demand careful,
> bidirectionally-tested work. The session that produced this doc had been compacted twice;
> the router changes deserve full context. Start clean, read this doc + the referenced ones,
> then begin.

## The four items

| Task | Item | Gates it unblocks |
|---|---|---|
| #8  | Phase 3.5 — Enforcement → tool-capable door (ENF-FIX-1..4, revise INV-ROUTE-006) | 5, 11 |
| #14 | Phase 3.7b — Leaderboard-driven capability ranking in the router | North-Star capability model |
| #5  | Phase 8 — Control-group benchmark (real Chuzom-off-vs-on A/B) | 15, 16, 17 |
| #6  | Phase 9 — Gate re-eval + two consecutive clean audits + final verdict | consecutive-audit rule |

## Sequencing (decided 2026-07-27)

**They do NOT fully parallelize.** #6 is strictly last; #8 and #14 both mutate the router and
would interfere. Only the off-router infrastructure parallelizes.

```
  ┌─ #8 enforcement door (router mutation) ──┐
  │                                          ├─► #5 measurement run ─► #6 verdict
  ├─ #14 router wiring (router mutation) ─────┘        (post-#8/#14)     (last)
  │        ▲ sequential AFTER #8
  │
  ├─ #5 benchmark HARNESS (off-router infra) ── parallel from day 1
  └─ #14 leaderboard DATA layer (config)     ── parallel from day 1
```

- **Order for the two router mutations: #8 first, then #14.** #8 is an open **P1** blocking Gates
  5/11; land it first, then wire #14's ranking into the (now tool-capable) chain.
- **Parallel-safe now:** #5's benchmark harness (A/B runner, spend classification, quality
  margin) and #14's leaderboard data layer (fetch + cache artificialanalysis.ai into config —
  NOT live-fetch per route). Neither touches routing decision logic.
- **Sequential / last:** the router wiring of #14, then #5's measurement run against the final
  system, then #6.
- **One router branch in flight at a time.** Infra branches may overlap; router branches may not.

---

## #8 — Enforcement → tool-capable door  (START HERE)

Full design already written: **`05_ENFORCEMENT_FIX_PLAN.md`** (ENF-FIX-1 → ENF-FIX-4, revised
INV-ROUTE-006). Friction evidence: **`04_ENFORCEMENT_FRICTION_GAPS.md`** (GAP-ENF-1..4, recurred
5×+). Do not re-derive — implement ENF-FIX-1 first (highest priority), each fix its own tested
increment.

**Critical guardrail (learned the hard way).** `operational_signal.py::detect_operational` is
deliberately conservative (fires iff a change-verb AND a verify-cue match, and not an
explanatory-lead / content-object). **Do NOT broaden `detect_operational`** to catch execution
work — that over-routes prose. Add a **separate `needs-local-execution` / `needs-tools` signal**
and route on that. Bidirectional tests are mandatory: **fires** on genuine execution/repo work,
**silent** on explanation/prose ("explain how X works" must NOT be classified needs-tools).

Files: `src/chuzom/hooks/enforce-route.py` (the enforced-door directive; `LOCAL_BASH_EXEMPT` at
~824 — do not widen), `src/chuzom/operational_signal.py`, the ledger for escalation events.

Done when: ENF-FIX-1..4 landed with tests; an execution request under hard enforcement names
`llm_act` (never a text-only door); a context-dependent prompt routes to a **provisioned**
`llm_act`; clean one-step escalation to Claude records an escalation event (no violation-count
trap); Gates 5 & 11 flip to PASS in `03_RELEASE_GATES.md`.

## #14 — Leaderboard-driven capability ranking

North Star: capability = the **live leaderboard** (artificialanalysis.ai), not "Claude is best."
Principle doc already merged (#162). Two separable pieces:

1. **Data layer (parallel-safe):** fetch + **cache** the leaderboard into config (a periodic
   refresh, NOT a per-route live fetch). Deterministic, offline-testable; no routing change.
2. **Router wiring (sequential, AFTER #8):** consume the cached ranking in the provider-chain /
   escalation-top ordering, so the "cheapest **capable**" decision is leaderboard-sourced rather
   than a hardcoded Claude-top. Core-routing change — careful, isolated, bidirectionally tested
   (ranking changes reorder the chain; a stale/missing leaderboard must fall back safely).

Files: router provider-chain / escalation code, `user_routing_policy.py`, a new leaderboard
config/cache module. Done when: the chain order derives from cached leaderboard capability with a
safe fallback, tested both ways.

## #5 — Control-group benchmark (real savings proof)

The verdict blocker for Gates 15/16/17: today only repricing counterfactuals exist, no real
Chuzom-**off**-vs-**on** A/B. Build (parallel-safe) the harness: run a fixed task suite with
routing OFF (all-Claude) and ON, measure **verified net token savings** and **quality within a
non-inferiority margin**, with **no unclassified spend** per benchmark event. Then (sequential)
run the measurement against the post-#8/#14 system. Only then may a savings magnitude be marked
`supported` in the claim-evidence registry. Lives under `bench/experiments`.

## #6 — Gate re-eval + final verdict (LAST)

After #8/#14/#5 land: refresh `03_RELEASE_GATES.md`, then **freeze a commit and run two
consecutive complete audits** with zero new P0/P1 and no "not reached" sections (the
consecutive-audit rule). Only then may the verdict move off **RELEASE NOT QUALIFIED** — and only
if genuinely earned. Never soften the verdict to fit a deadline.

---

## Cross-cutting guardrails (apply to every item)

- **Never audit/repair Chuzom through Chuzom's own `llm_*` MCP tools** or `chuzom-worker`
  subagents — the system under audit must not evaluate itself. Use direct tools / non-routed
  agents.
- **Every finding/fix ships a fail-before / pass-after test.** For router changes, test **both
  directions** (fires when it should, silent when it shouldn't).
- **Always run the CI-exact full suite** before pushing — not just focused tests. A DASH-5 label
  change silently broke a DASH-1a string-pin that only the full suite caught. Command:
  `HOME=$(mktemp -d) OPENAI_API_KEY=sk-test-dummy-key-for-ci-only-no-real-calls-made pytest
  --ignore=tests/test_agno_integration.py --timeout=30`.
- **Known-flaky, non-blocking:** `test_direct_executor::TestExecuteAgentContext` (RC-0
  order-pollution — passes in isolation) and the `test (3.11)` perf/aiosqlite job when 3.13/3.14
  pass. A **real** regression fails `test (3.13)` and `test (3.14)`. Never merge on those red.
- **Branch off clean `main` before editing; one router branch in flight; never merge real red;
  do not push/publish unless explicitly instructed.**

## Definition of done

All four complete, every gate in `03_RELEASE_GATES.md` re-evaluated with proof, two consecutive
clean audits recorded → then, and only then, an honest **RELEASE QUALIFIED / NOT QUALIFIED**
verdict.
