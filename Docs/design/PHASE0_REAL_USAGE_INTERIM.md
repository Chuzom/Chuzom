# Phase 0 — real-usage interim: POTENTIAL savings (adoption-unverified)

> **Status: honest interim. This is a POTENTIAL number, not a REALIZED one.**
> It is derived from the real execution ledger on this machine
> (`~/.chuzom/usage.db`, `execution_events`), aggregate stats only — no prompt or
> response content. It answers "how much work went to non-Claude models" — NOT
> "how much Claude quota was verifiably saved," which requires Phase 0.5.

## The real signal

Across **2,666 real execution events** (1,061 `attempt_completed`), tokens served
by provider on completed attempts:

| Provider | Completed attempts | Tokens served |
|---|---|---|
| ollama (free, local) | 386 | 956,251 |
| openai | 169 | 217,639 |
| codex | 29 | 3,919 |
| gemini | 8 | 80 |
| **non-Claude subtotal** | **592** | **1,177,889** |
| anthropic (Claude) | 4 | 803 |

So **~1.178M tokens of real work were served by non-Claude models, vs 803 by
Claude** — ~99.9% of served tokens went off-Claude.

## Why this is POTENTIAL, not REALIZED (the Phase 0.5 wall)

The realized-savings meter (Phase 0) cannot honestly call this a realized saving
yet. Verified against the real `usage.db`:

- **Adoption is essentially absent:** only **3 of 2,666** events are
  `realization_status = verified_used`; the other 2,663 are null/unknown. In
  production the adoption signal is tied to the coercive door-call, which almost
  never fires — so "was the routed answer actually used?" is unknown for ~99.9% of
  routes.
- **No baselines are written:** **0** events have `baseline_equivalent_cost_usd`
  populated, so the metered-$ realized saving is structurally 0 from real data.
- **host_mode is mostly unknown:** 1,972 unknown / 493 metered / 201 subscription.

Two assumptions also sit under the "potential" framing and are NOT verified:
1. that the off-Claude work would *otherwise* have gone to Claude (vs. the user
   choosing a non-Claude model anyway), and
2. that the routed answers were used (adoption).

## Honest reading

- **Upper-bound potential:** up to ~1.178M Claude tokens of quota *may* have been
  avoided in real usage — a strong indication the router is doing real off-Claude
  work at scale.
- **Defensible realized savings from real data today: ~0**, because adoption and
  baselines aren't recorded in production. This is the same inert-production-meter
  finding the Phase-0 pipeline surfaced — now confirmed on real data, not inferred.

## What unblocks a real REALIZED number: Phase 0.5

The bottleneck is production telemetry, not corpus data (there are already 21,643
routing decisions + 2,666 events). Phase 0.5 must:
1. **Write the baseline at the attempt** (`baseline_equivalent_cost_usd` /
   `baseline_tokens`) so savings have a counterfactual.
2. **Reconcile the hook↔router `route_id`** so adoption (`verified_used`) attaches
   to the same route as its cost — and add an adoption signal that works without
   coercion (advise-mode `agent_marked`).

Once those land, the abundant real data above yields a defensible *realized*
number (median + conservative floor, per the Phase-0.2 reporting discipline),
instead of the ~0 the real ledger honestly reads today.
