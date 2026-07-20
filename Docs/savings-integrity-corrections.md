# Savings Integrity — Corrected Findings

Corrections and fixes prompted by the 2026-07-20 routing retrospective (a
read-only local-repo audit that "saved ~$0"). The retro was right about *why
that session* saved nothing, but it accepted chuzom's own savings framing at face
value. Code inspection showed the framing was unreliable across several
independent computation paths. This document records the corrected findings; the
fixes, tests, and offline experiment suite that resolve them ship in the same
change.

## TL;DR (corrected)

The ~$0 savings that session were **correct behaviour** — every prompt referenced
local repo state, so the router deliberately skipped routing (a stateless model
would fabricate). But the broader, more important finding is that on an
**unpressured flat-rate subscription, chuzom is a quota-smoother, not a
dollar-saver**: at quota pressure 0, "cheapest capable" resolves to the Claude
subscription even for routable work (only *premium* models are gated, at
pressure ≥ 0.85). And the reported savings **numbers themselves were unreliable**
— multiple surfaces used different windows, labels, baseline **models**, and
baseline **prices**, so they disagreed by an order of magnitude.

## Corrections to the retrospective itself

- **Baseline was Opus, not Sonnet — but wrong on two axes.** The retro said
  "vs Sonnet baseline." The savings math actually priced against Opus, though the
  codebase *named* things inconsistently (a dead `BASELINE_MODEL_FOR_SAVINGS =
  "sonnet"` constant, a function still called `get_routing_savings_vs_sonnet`, and
  a SessionStart digest that genuinely priced against Sonnet — see B-6). More
  importantly the Opus price was **frozen and ~3× too high**: `$15/$75` labelled
  "Opus 4.6", when Opus 4.5+ (incl. 4.6/4.7/4.8) is **$5/$25**. See B-8.
- **"Subagents can't be routed, only gated" is false.** The DIRECT/CLI subagent
  paths route subagent bodies onto cheap models and log savings
  (`hooks/savings_logger.log_direct_savings(..., host="claude_code_subagent")`).
  The open question is only whether it *fires* and is *credited* — proven by
  `tests/test_subagent_routing_credited.py` — not whether it is possible.
- **Persisted `agent_depth` is largely a non-issue.** Depth files are per-session
  (`agent_depth_<session>.json`) and decremented by a PostToolUse release hook, so
  there is no cross-session collision. (Verify the SessionStart path zeroes a
  fresh fan-out.)

## Bug entries

| # | Class | Issue | Evidence | Fix |
|---|---|---|---|---|
| **B-6** | Data integrity | Savings surfaces disagreed by ~10–25×. Five independent causes: (1) SessionEnd summed the **all-time** row but printed `"saved this week"`; (2) the SessionStart digest priced against **Sonnet** while every other surface used Opus; (3) `cost.py` priced Opus at **$15/$75** while `receipt_store`/`savings_logger` already used $5/$25; (4) "week" meant **rolling-7-day** on the banners but **calendar Mon–Sun** in the dashboard; (5) the dashboard was titled "vs SONNET BASELINE" while computing against Opus. | `hooks/session-end.py` (all-time→"this week"), `hooks/session-start.py` (`_SONNET_*_PER_M`), `cost.py` (`$15/$75`), `cost.get_savings_by_period` (`weekday 0,-6 days`) vs banners (`-7 days`), `tools/admin.py` labels | Unify the baseline (model **and** price) onto the latest Opus everywhere; fix the all-time→weekly mislabel; keep each window **truthfully labelled** ("last 7 days" rolling vs "this week" calendar) rather than forcing byte-identity (a rolling 7-day span can exceed month-to-date, which would break `today ≤ week ≤ month` nesting). |
| **B-7** | Methodology | On a flat-rate subscription, free-local calls booked the **full Opus baseline** as "saved", even though the host call's marginal cost is ~$0 — overstating dollars. | `cost.get_savings_by_period` free-provider branch; `session_spend.net_savings_usd` | **Additive, non-breaking:** report two clearly-labelled figures — `baseline_avoided_usd` (quota/token story) and `real_dollars_avoided_usd` (~$0 on a subscription; the full baseline only in metered API mode, keyed on `CHUZOM_CLAUDE_SUBSCRIPTION` → `cost._host_is_metered`). |
| **B-8** | Correctness | Baseline price stale-versioned and ~3× too high (`$15/$75` labelled "Opus 4.6"). Largest single distortion; every other savings figure builds on it. | `cost.py:_HOST_INPUT_PER_M/_HOST_OUTPUT_PER_M` | Correct to **$5/$25** and resolve from a single `LATEST_OPUS_MODEL` + `_OPUS_PRICING` source of truth (optionally refreshed via the Models API), so a future Opus release updates one place. |

*(B-1..B-5 from the original retro are retained. B-2 and B-4 are reaffirmed as the
two levers that actually move cost: subagent routing exists and should be
credited; on an unpressured account nothing downshifts.)*

## Coordination with G-METRIC-1

Orthogonal. `session_spend.read_base_drift` measures routing *capture rate* (drift
back to base models); this change adds a *dollar-reconciliation* concern. No edits
to `read_base_drift` or `tests/test_base_drift.py`.

## Verification

- Unit / characterization (red→green): `tests/test_baseline_price.py`,
  `tests/test_real_dollars_avoided.py`,
  `tests/test_savings_surface_reconciliation.py`,
  `tests/test_baseline_is_labeled.py`, `tests/test_subagent_routing_credited.py`.
- Offline experiment suite (deterministic, $0): `python -m bench.experiments`
  replays three realistic session shapes through the real savings code and checks
  reconciliation, a counterfactual dollar model, and property invariants; the
  scorecard (`bench/experiments/report.md`) is the reproducible replacement for the
  retro's hand-computed, contradictory numbers. Also run in CI via
  `tests/test_bench_experiments.py`.

The experiment scorecard makes the thesis concrete: the local-audit shape saves
$0 (100% DIRECT-SKIP — correct); the stateless-Q&A shape shows a positive
baseline-avoided figure but **$0 real dollars on a subscription**, positive only
in metered mode or over the quota cap.

## Known follow-ups (not in this change)

- Three hardcoded copies of the $5/$25 Opus price remain (`cost._OPUS_PRICING`,
  `savings_logger._PRICING_PER_MTOK`, `receipt_store` literals), each with a
  "keep in sync" note. A single shared price registry would remove the drift risk.
- Rename `get_routing_savings_vs_sonnet` (misleading — it prices against Opus)
  once callers are audited.
- Optional `CHUZOM_PREFER_CHEAP_AT_ZERO_PRESSURE` lever (B-4) to prefer
  Ollama/Gemini for routable tasks even at 0 pressure — deferred; it changes
  routing behaviour and interacts with Ollama latency.
