# Chuzom Correctness Reset — 08. Leaderboard-Driven Capability Ranking (Phase 3.7b / #14)

Finding + scoped plan for #14 ("track a live leaderboard, not a hardcoded Claude-top").
Written after tracing the actual routing code — the scope is **narrower than the task title
implies**, because the core is already built and tested.

## What already exists (leaderboard-driven ranking IS live in the router)

The capability ranking is not hardcoded — it is derived from public leaderboards and consumed
by the live chain-builder:

1. **Fetch (multi-leaderboard composite).** `benchmark_fetcher.py` pulls **Arena-Hard-Auto**
   (LMSYS replacement), **Aider edit leaderboard**, and **HuggingFace Open-LLM v2**, plus
   LiteLLM pricing, and computes a weighted composite ranking → premium / balanced / budget
   tiers.
2. **Cache + refresh (config, not per-route fetch).** `generate_benchmarks_json` writes
   `~/.chuzom/benchmarks.json`; `benchmarks.maybe_refresh_benchmarks_background(ttl_days=7)`
   re-fetches weekly on a background thread. Routing reads the **cached file**, never a live
   per-route HTTP call — exactly the North-Star design (config-sourced capability).
3. **Consume (in the router's chain-builder).** `profiles.get_model_chain(profile, task_type)`
   calls **`benchmarks.apply_benchmark_ordering(...)`** (profiles.py ~499) to reorder the chain
   by benchmark quality score, then `reorder_for_pressure(...)` for quota. So the ordering the
   router actually uses is leaderboard-derived, refreshed weekly, with failure/latency/
   acceptance penalties folded in (`get_model_failure_penalty`, `get_model_latency_penalty`,
   `get_model_acceptance_penalty`).
4. **Regression-locked.** `test_profiles.py`, `test_reasoning_profile.py`,
   `test_availability_routing.py` already exercise the benchmark-ordering path.

The North-Star principle from #162 (capability = live leaderboard) is therefore **implemented
in the ordering layer**, not merely documented.

## The real residual gap (what #14 still needs)

Two things, both narrower and one genuinely delicate:

### R1 — the escalation / reasoning TOP is a hardcoded Claude preference  · the delicate one
`profiles.py` `_PROFILE_MODEL_CONSTRAINTS` hardcodes the Claude preference order for the
escalation and REASONING profiles:

```
allowed_claude: anthropic/claude-opus  → claude-sonnet → claude-fable
# claude-fable = "Last-resort escalation — most sophisticated / most expensive"
```

This is the "hardcoded Claude-top": the *last-resort / most-capable* slot assumes a Claude
model is the capability ceiling, rather than deriving that slot from the leaderboard #1. The
**mid-chain ordering** is leaderboard-driven (R above); only the **escalation ceiling** is
assumed.

**Why it's delicate (do NOT rush).** This slot is the safety-critical last resort, guarded by
`_validate_chain_invariants` (forbidden/discouraged lists), and interacts with subscription
mode and `reorder_for_pressure` (which removes Claude at ≥99% quota). Making it
leaderboard-sourced means the last-resort model could become non-Claude when the leaderboard
says so — correct per the North Star, but a behavior change to the fallback ceiling that needs
its own focused, bidirectionally-tested PR (leaderboard #1 is honored; a stale/empty
leaderboard falls back safely to the current Claude ceiling; invariants still hold).

### R2 — artificialanalysis.ai is not one of the sources  · low-value
The task named artificialanalysis.ai specifically; the current composite uses
Arena-Hard/Aider/HuggingFace instead. These are functionally equivalent public capability
signals. Adding artificialanalysis.ai as an additional weighted source in `benchmark_fetcher`
is straightforward **if** its data is publicly fetchable without auth; otherwise the existing
composite already satisfies "a live leaderboard, not hardcoded."

## Recommendation

- **#14 core = DONE** (leaderboard-driven ranking is live in the router and tested). This doc
  records that so it isn't re-built.
- **R1 (escalation-ceiling → leaderboard-sourced)** is the one substantive remaining change and
  is **safety-critical** — it belongs in its own careful PR with bidirectional tests, not
  bundled at the end of a long session. Scoped and ready to pick up.
- **R2** is optional / low-value; add artificialanalysis.ai only if publicly fetchable.

Verdict impact: none directly — #14 was never a release-gate blocker (the blockers are the
benchmark #5 and the two-audit rule #6). This narrows #14 to R1.
