# RouterArena cold-submission — GO / NO-GO memo

**Prepared for an explicit human decision. Nothing here has been run. The one-shot
seal is UNBURNED (no `.ra_touch_ledger.jsonl`).**

---

## 1. What would actually be submitted

The classifier + reason-gate in PR #130 are **not** RA-runnable levers — RA scores
*answer accuracy × cost*, and those change *task classification*, not which model
answers a question or whether it's right. The only "new approach" that is RA-runnable
is the **calibrated confidence cascade** (`router_core.py`: probe 2 cheap → agree? keep
: escalate to strong).

So a new submission = the cascade with the new calibrated τ. Compared to what's
already **shipped** (`chuzom-solo-v32`, deepseek-v3.2 on every query, **0.7061**):

| Candidate | Expected arena | Contamination-review surface |
|---|---|---|
| Shipped deepseek-solo (#161) | 0.7061 (measured) | **zero** fitted components |
| Calibrated cascade (new) | ~0.70–0.71 (frontier + η=0.18 bound) | a fitted τ threshold + escalation logic to defend |

The cascade is **not expected to beat the shipped solo**, and it carries *more* for a
maintainer to challenge, not less.

## 2. What a "GO" triggers (in order)

1. **Complete the prediction wiring** — a `produce_fn` that runs the cascade over RA's
   8,400 full + 420 robustness prompts through the RA harness. (Not yet wired end-to-end;
   the 19 MB file in `bench/routerarena/submission/predictions/` is the OLD v0.5.0 output.)
2. **Burn the one-shot** — `measure_ra_once.py` requires the literal override
   `I_UNDERSTAND_THIS_BURNS_THE_ONESHOT`; it verifies the RA evaluator is unmodified,
   fingerprints the router source, and chains a tamper-evident ledger entry. **This is the
   irreversible act** — a human types the phrase, deliberately.
3. **Pay for inference** over ~8,820 prompts with the intended pool models.
4. **Open a 4th external PR** to the RouterArena repo and request `/evaluate`.

## 3. The three costs of GO

- **Burns your one-shot** — the discipline is: touch real RA *once*, for a submission you
  believe in. Spending it on a router your own data bounds at ~0.71 spends it for ~nothing.
- **4th external PR** after #132/#140/#155 (rejected) + #161 (shipped) — real maintainer
  credibility, for no expected lift.
- **Real $** — inference over 8,820 prompts.

## 4. Evidence this lands at ~0.71, not higher (all measured/derived)

- `STATUS.md`: 12 approaches, all capped ~0.71–0.73; clean ceiling never moved.
- `escalation_frontier.py`: formula validated (round-trips 0.7061); best real gate
  harvests only **η = 0.178** of the oracle lift → no affordable strong model clears 0.75.
- Transfer: query-surface signals measured **0.024** to RA; paraphrase-transfer works
  within a topic (0.71) but cross-hard-tail could not be reproduced locally (cheap model
  too good at gradable trivia) — so the real-data 0.024 stands.

## 5. Recommendation

**NO-GO.** There is no new router that legitimately clears the shipped **0.7061**, and a
GO burns the one-shot + a PR + $ to confirm a number we already know. Keep the seal for a
submission that has a real, evidence-backed shot at clearing the bar — which, per §4,
would require a *higher-η confidence signal* (a research result), not a pool or classifier
change we have in hand today.

**If you GO anyway** (a legitimate "I want the number on record" call): say so explicitly,
and I will (1) wire `produce_fn`, (2) hand you the exact sealed command to type yourself,
(3) prepare the RA PR — but I will not type the override phrase or open the external PR for
you; those are yours to trigger.
