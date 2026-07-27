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

### R1 — RESOLVED after a deeper trace: the ceiling IS leaderboard-driven  · ✅
**Correction (from tracing `apply_benchmark_ordering` + `reorder_for_pressure`).** The initial
framing below ("the ceiling is a hardcoded Claude preference") was imprecise. The live
chain-builder sorts the **entire** chain quality-first from the leaderboard's `task_scores`
(quality-descending, cost tie-break within a 5% tier). So when the leaderboard ranks a
**non-Claude** model highest for a task, that model leads the chain **ahead of Claude** — Claude
is *not* a hardcoded ceiling. Proven and regression-locked, in both directions, by
`tests/test_leaderboard_ceiling.py`:

- leaderboard #1 (non-Claude) → leads, ahead of Claude, even when the static chain lists Claude first;
- when the leaderboard genuinely ranks Claude #1 → Claude leads (no fixed bias, follows the board both ways);
- no leaderboard data → safe fallback to the static (Claude-including) chain, unchanged, nothing dropped.

The only "hardcoded Claude" that remains is (a) the **safe default** when the leaderboard is
silent — which is correct, you want a sane fallback — and (b) `allowed_claude`, which is a
**validation constraint** (which Claude versions are permitted, and in what order *among
themselves*), enforced by `_validate_chain_invariants` — **not** an ordering ceiling. So R1 is
satisfied: the escalation ceiling follows the leaderboard, with a safe Claude fallback only when
there is no data. **#14 is complete** (core + R1); R2 (below) is the only optional remainder.

<details><summary>Original (imprecise) R1 framing, kept for the record</summary>

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

</details>

### R2 — artificialanalysis.ai is not one of the sources  · RESOLVED — won't add
The task named artificialanalysis.ai specifically; the current composite uses
Arena-Hard/Aider/HuggingFace instead — functionally equivalent public capability signals.

**Resolution (checked 2026-07-27): do NOT add it.** Artificial Analysis's data is **not
auth-free**. Even the free tier requires creating an account and generating an `x-api-key`
(kept server-side), is rate-limited to 1,000 req/day, and mandates attribution to
`https://artificialanalysis.ai/` on all use ([Data API docs](https://artificialanalysis.ai/data-api/docs),
[Data API](https://artificialanalysis.ai/data-api)). Wiring it in would therefore require the
user to provision and store a third-party API credential — outside the scope of an autonomous
change, and a new secret + attribution obligation for marginal value. The existing multi-source
composite already fetches without auth and already satisfies the North Star ("a live
leaderboard, not a hardcoded Claude-top"). If a Chuzom operator later wants AA specifically,
they can add it as a keyed source in `benchmark_fetcher` — a small, opt-in follow-up, not a
correctness-reset requirement. **#14 is therefore fully complete** (core + R1 + R2).

## Recommendation

- **#14 core = DONE** (leaderboard-driven ranking is live in the router and tested). This doc
  records that so it isn't re-built.
- **R1 (escalation-ceiling → leaderboard-sourced)** is the one substantive remaining change and
  is **safety-critical** — it belongs in its own careful PR with bidirectional tests, not
  bundled at the end of a long session. Scoped and ready to pick up.
- **R2** is optional / low-value; add artificialanalysis.ai only if publicly fetchable.

Verdict impact: none directly — #14 was never a release-gate blocker (the blockers are the
benchmark #5 and the two-audit rule #6). This narrows #14 to R1.
