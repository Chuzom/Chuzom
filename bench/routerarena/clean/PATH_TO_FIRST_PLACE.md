# Path to #1 on RouterArena — research-backed insights + plan

**Date:** 2026-07-12 · **Status:** strategic correction + plan after researching the RA leaderboard, paper (arXiv 2510.00202), and PR history.

---

## 0. The correction — I was wrong about the ceiling

All session I concluded "RA's ceiling for this pool is ~0.71; it's a capability/economics wall." **The individual measured numbers are all real and reproducible** (cascade 0.693, domain-router 0.694, qwen-solo 0.677 — verifiable on disk + your OpenRouter bill). But the **inference** I drew from them — "therefore ~0.71 is the RouterArena ceiling" — is **false**, and the leaderboard proves it. I kept testing *within the cheap pool*, whose ceiling is ~0.75, and mistook that for RA's ceiling.

The specific mistake: I generalized "strong models are too expensive" from **Fable 5** — the single most expensive model ($50/M output). That's true for Fable 5, but the leaders use *mid-tier* strong models the arena tolerates fine. I never tested a strong pool.

---

## 1. What the leaderboard actually shows

| Router | Arena | **Accuracy** | **Cost/1k** | Method |
|---|---|---|---|---|
| vLLM-SR | 75.30 | **77.2%** | $0.30 | ModernBERT category → highest-score model |
| Sqwish | 75.27 | 76.4% | $0.18 | (robustness 100 → strong pool) |
| AgentForge | 74.13 | 74.7% | $0.13 | — |
| Weave | 72.8 | 76.3% | **$0.94** | strong pool, high cost |
| Nadir | 72.3 | 75.0% | $0.68 | **cascade** (`nadir-cascade-v2`) |
| **Chuzom solo** | **70.6** | **69.5%** | **$0.025** | single model |

**Three facts that flip the strategy:**
1. **The winners win on ACCURACY (76–77%), not cost.** We're at 69.5%.
2. **We are the cheapest entry on the board — by ~10×.** The leaders spend $0.13–0.94/1k; we spend $0.025. We have *enormous* unused cost headroom.
3. **Their pools' oracle accuracy is 89–98%** (perfect-routing ceiling). Our cheap pool's oracle is ~0.75. Their pools *contain models that answer the hard tail*; ours don't.

---

## 2. The formula math — cost is cheap, accuracy is everything

Arena `S = 1.1·A·C_i / (0.1·A + C_i)`, with `C_i = (log2(200) − log2(cost)) / (log2(200) − log2(0.0044))`.

Because cost is **log-normalized** over a huge range ($0.0044 → $200) and β=0.1 tilts to accuracy:
- deepseek-solo: A=0.695, $0.025 → **0.706**
- vLLM-SR: A=0.772, $0.30 → **0.753**
- **Hypothetical: A=0.772 at our $0.025 → 0.777 (would be #1 by a mile).**
- Spending 12× more ($0.30) only drops `C_i` from 0.84 → 0.61. **Accuracy from 0.695 → 0.772 is worth far more than the cost it takes to buy it.**

**Conclusion: every spare dollar should buy accuracy. We have ~12× cost headroom before we even match the leaders' cost.**

---

## 3. Why our experiments all failed (correctly, but for the wrong pool)

Every approach kept the **cheap pool** (deepseek-v3.2, qwen3-235b, v4-flash). That pool's oracle is ~0.75, so **no routing within it can clear 0.75** — the hard tail (LiveCodeBench 0.0, ChessInstruct 0.13, WMT translation, obscure trivia) is unanswerable by *any* cheap model. Routing rearranges losers; it can't add capability. The winners add capability by putting **strong + specialist models in the pool**.

---

## 4. The plan to hit #1

**Objective flip: maximize accuracy, spend the headroom.**

**Stage A — Pool with a high oracle ceiling.** Add models that answer the hard tail (all pool declarations, zero contamination):
- a strong general/reasoning model (GPT-5-class / Claude Sonnet-5 / o-series) for hard knowledge + math + reasoning;
- a real **code** model for LiveCodeBench (we score 0.0);
- a strong **multilingual** model for WMT translation (0.0);
- keep cheap models (qwen3-235b, deepseek-v3.2) for the easy majority.

**Stage B — Measure the pool per-domain/difficulty** on hash-audited benchmark data (reuse `scripts/measure_domain_experts.py`) so the pool + map are evidence-based, not guessed. Confirm a strong model actually lifts the hard-tail datasets.

**Stage C — Difficulty router (the η lever).** Train a **difficulty/correctness predictor** on hash-audited benchmark data (label = "did the cheap model get this right?" — benchmark-derived, never RA). Predict per prompt whether to escalate to a strong model. This is what vLLM's BERT does; our 81%-accurate domain classifier is the starting embedding, add a difficulty head. Reuses `semantic_centroids` + `contamination_audit`.

**Stage D — Default-strong, route-DOWN-easy (inverted cascade).** Because accuracy is the priority and cost has headroom, default to a capable model and route *down* to cheap only on high-confidence-easy queries. Blended cost lands in the arena's $0.20–0.30 sweet spot; accuracy stays high. (Contrast our failed cascade, which defaulted *cheap* and rarely escalated.)

**Stage E — Evaluate through the seal**, one cold pass, no iterating against the number. Guards + audit as before.

---

## 5. The immediate, cheap, decisive test (do this FIRST)

Before building any router: **does a strong model actually crack RA's hard tail?** Run one mid-tier strong model (via OpenRouter — e.g. an o-series / GPT-5-mini / Sonnet) over the sub_10 datasets we score ~0 on (LiveCodeBench, ChessInstruct, WMT19, AIME, QANTA). Reuse `run_solo.py` with the strong model.
- If those go 0.0 → 0.4–0.7: **the accuracy lever is real, the plan works, proceed.**
- If even a strong model fails them: the ceiling is genuine after all.

Cost: ~$2–5 (strong model, ~800 prompts). This single test resolves whether #1 is reachable — and it's the one experiment this whole session should have run first.

---

## 6. Honest expectation

This is the **first plan that targets the axis we're losing (accuracy) with the resource we have in surplus (cost)** — unlike all six prior attempts, which optimized the axis we were already winning. The leaders prove 77% accuracy at tolerable cost is achievable; the oracle (89–98%) shows the headroom. Realistic outcome: **0.73–0.77**, i.e. genuinely contending for #1 — *if* (a) a strong model lifts the hard tail on RA (Stage-5 test), and (b) the difficulty router realizes a good fraction of the oracle (the frontier vLLM cracked with a benchmark-trained classifier). Both are testable. It is not guaranteed, but it is the first approach with a real path — and it starts with a $2 test.
