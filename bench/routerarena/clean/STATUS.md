# Chuzom × RouterArena — definitive status (closeout)

Complete, evidence-backed record. Every number is a real measurement (sha-pinned RA
metrics; evaluator never modified). **Decision: ship the single deepseek-v3.2 submission
(PR #161, ~0.7061). 0.76 is not reachable by any legitimate means with this pool.**

## The one-sentence truth

> A cost-aware router cannot legitimately clear 0.76 on RouterArena with this model pool —
> rich oracles exist (0.75→0.80) but are **unharvestable**, and 0.76 lives only behind
> **RA-derived supervision** (the PR-140/155 forbidden line).

## Decision & shipped submission

- **Shipped:** `chuzom-solo-v32` — deepseek-v3.2 on every query (PR #161, full-8400 **0.7061**).
- **Why single-model:** a uniform model has zero fitted components → nothing for the maintainer
  to challenge. It's the lowest-risk compliant submission and, on the full 809, deepseek-v3.2
  (0.6951) is the best single model measured (edges v4-flash 0.6923; all frontier models cost too much).

## Approaches tried and falsified (12)

Each hit the SAME wall: a real oracle exists, but no legitimate signal harvests it, and RA's
hard tail is unfixable by any affordable model.

| # | Approach | Result (RA) | Why it failed |
|---|---|---|---|
| 1 | Agreement gate (2-model) | sep ~0.01 | agreement ≠ correctness |
| 2 | Coherence-judge escalation | **0.7142** (809) | best clean signal; caps at 2-model oracle 0.7513 |
| 3 | MemoryTree (embedding KNN) | transfer 0.024 | self-gen surface ≠ RA surface |
| 4 | Visual / text-as-image | dead | <1% visualizable |
| 5 | Swarm / Prosecutor / Inversion | dead | over-fire or no signal |
| 6 | Code-as-reasoning | weak | narrow applicability |
| 7 | LLM-as-router (Sonnet) | 0.7220 (150) | under-escalates; can't predict failure |
| 8 | LLM-as-router (Opus) | 0.7063 (150) | 53 escalations → ZERO net accuracy |
| 9 | Council vote (4 cheap) | 0.7204 (150) | unequal voters; vote ≈ single best |
| 10 | Pair-agreement gate | ceiling 0.7528 | hard tail unfixable (~36%) |
| 11 | MoA aggregator | 0.6755 (150) | wrong candidates mislead the judge |
| 12 | **Trained discriminator** (self-gen) | 0.7361 (150) | overfits surface cues; loses to coherence@8; bounded by oracle 0.7513 |

Plus **single-model sweep** (gpt-5-mini, glm-4.6, qwen3-max, kimi, gpt-5): none beat deepseek —
the accurate models are reasoning-heavy and cost $4.5–6.6/1k → arena crushed.

## Oracle gates (diagnostic upper bounds — never fed to any router)

| Pool | Oracle arena (150) | Meaning |
|---|---|---|
| {v4-flash, v3.2} | 0.7513 | 2-model ceiling |
| {+ sonnet} | **0.8042** | 0.76 IS inside the pool… |
| {+ opus} | 0.7886 | …but unharvestable by any predictor |

## Key positive finding (methodological, worth keeping)

Response-based signals **transfer**; query-surface signals do not.
- coherence-judge: separation **0.66** on RA · pair-agreement: **0.38–0.56** · MemoryTree embeddings: **0.024**.
- A discriminator restricted to {coherence, agreement, spread} transfers (sep 0.56) — but still can't beat the escalation-economics ceiling (strong ≈ cheap on the hard tail; sonnet too expensive).

## Why 0.76 needs the forbidden line

Arena floor math: even at the cost floor you need ~75.5–76% **accuracy**. deepseek caps ~70–73%
on RA's knowledge/multilingual/adversarial mix. The only way to know *per-query* which model wins
is RA-derived supervision (per-dataset accuracy / oracle / judge) — exactly what PR-140/155 reject.

## Compliance state (PR-140/155)

- ✅ Evaluator immutable — `metrics.py` / `compare_router_accuracy.py` zero diffs (verified).
- ✅ No RA-derived labels — all training self-generated, computed gold.
- ✅ No per-query/per-dataset RA routing table.
- ⚠️ **Do NOT submit the discriminator** — its variant/target was selected by RA-150 arena (config fit to RA outcomes); and it scores below coherence anyway.
- ⚠️ RA oracle was computed this session for diagnostics only (never fed to a router), but it's the class of thing the maintainer scrutinizes — kept strictly out of any shipped artifact.

## Open items

- [ ] **Rotate the OpenRouter API key** — it was written to `scratchpad/.orkey` (chmod 600, never committed) but appeared in this session's transcript. Rotate on openrouter.ai and delete the local file.
- [ ] Before any resubmit: re-verify evaluator zero-diffs + refresh `PROVENANCE.md`.
