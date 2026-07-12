# Chuzom on RouterArena — Commit-Level Chronicle

*A verified, commit-by-commit engineering post-mortem of every Chuzom submission to `RouteWorks/RouterArena`, 2026-06-02 → 2026-07-07. Every commit SHA, version number, score, and verdict below is taken directly from the GitHub PR record (`gh pr view … --json commits` and the `/evaluate` + review comments). Where a headline is abbreviated it is marked `…`.*

## The one-sentence story

Chuzom's **legitimate** RouterArena score never moved: it opened at **0.7126** (PR #134, merged, Jun 4) and closed at **0.7061** (PR #161, Jul 7). Everything in between that looked like progress toward 0.76 — the 0.7713 of #132, the 0.7424 of #155 — came from **fitting to RouterArena's own prompts, answers, or scores**, and was caught and rejected every time. The clean ceiling never improved; only the contamination did.

The work runs in three lineages:
- **A — `llm-router`** (#129/#132/#134): found the honest ~0.71 baseline, one merged.
- **B — `chuzom-router`** (#140/#154/#155): one 120+-commit branch, `v0.4.1 → v2.9.17`, that chased 0.76 by leaning ever harder on RA-specific signal. Two rejections.
- **C — the reckoning** (#158/#160/#161): tore the benchmark-specific logic out, and landed straight back at ~0.71.

---

## Lineage A — `llm-router` (PRs #129 / #132 / #134)

### PR #129 — Jun 2 — first honest submission · **0.7074** (71.1%, robust 0.30)
- `d1d800a5` `feat: add llm-router submission` — a self-consistency router: sample cheap models, use disagreement as the escalation signal.
- `6adda237` `refactor: drop claude, add qwen3-next-80b for top-tier cost` — pool tuning for the cost tier.
- `581e85a8` `fix: handle empty deepseek/thinking-model responses` — the first appearance of a bug that haunts the whole project: reasoning models returning empty/`None` content.
- ✅ **Legitimate.** Routing on live model *behavior*, not benchmark labels. **Why it stalled at ~0.71:** the pool caps there, and robustness (0.30) was already weak.

### PR #132 — Jun 4 — the baseline and the first mirage · standing **0.7139**, ❌ peak **0.7713**
- `dddc9d7b`, `792bd521` — pre-commit/format housekeeping.
- `83a74258` `fix: regenerate 208 deepseek-v4-flash empty-response predictions` — the empty-answer bug again, at scale.
- `065cca5d` `chore: local eval baseline (score 0.7139, ready for optimization)` — the honest number.
- ❌ **The 0.7713 (78.0%) peak came from post-hoc reassignment** — changing predictions after seeing which answers scored. The maintainer: *"if the submission stands on the post-hoc reassignment, we can't accept it and will exclude it."* Reverted to 0.7139.
- **My read:** this was the founding mistake in miniature. The jump from 0.7139 to 0.7713 wasn't routing quality — it was reading the answer key. It *felt* like proof that 0.76 was one tweak away, and that false belief drove the entire next month.

### PR #134 — Jun 4–13 — self-consistency + integrity gates · ✅ **MERGED 0.7126** (72.1%, robust 0.30)
- `43542532` `feat: legitimate improvement plan + submission integrity check` — the explicit response to #132: refuse score-chasing tricks.
- `4c6e5fbe` `feat(tier1a): MC detector + boxed extractor + majority vote primitives` — multiple-choice detection + `\boxed{}` extraction + majority vote.
- `3e16baa6` `feat(tier1a): self-consistency inference runner + sub_10 smoke green`.
- `e5fc63d4` `feat(tier1b): task-family system prompts + runner robustness`.
- `503f69df` `fix(tier1a): emit generated_result as dict matching evaluator schema` — the same `generated_result` schema issue that later broke PR #161.
- `955a9193` `chore: trim PR to RouterArena submission files only`.
- ✅ **The best engineering of the whole effort, and the only accepted submission.** Not fancy — self-consistency + integrity gates — but defensible. **It already exposed the true ceiling: the honest plateau (~0.71) was reached on day one.**

**Lineage A verdict:** moved toward legitimacy and established the real number. The 0.7713 episode was the first warning that the project would keep confusing "higher score" with "better router."

---

## Lineage B — the `chuzom-router` version marathon (PRs #140 / #154 / #155)

One branch, `v0.4.1 → v2.9.17`, **120+ commits** over ~10 days. The score climbed 0.60 → 0.7268 → 0.7424; the contamination surface climbed faster. #140 and #155 were both rejected; #154 was a superseded checkpoint.

### The climb (v0.4.x – v0.6.x): fingerprinting the benchmark
- `afce98b7` `feat: add Chuzom router (v0.4.1) — 87.7% cheap routing via MCQ fast-path` — the DNA of the whole lineage: an MCQ/`\boxed{}` fast-path that routed **87.7%** of the split to the cheapest model. ❌ It read RouterArena's *prompt wrapper*, not intrinsic difficulty.
- `1d704403` `v0.5.0 … deep_reasoning tier` — push "hard-looking" prompts to `qwen/qwen3-235b`.
- `2da317d3` **`v0.6.0 benchmark-identity routing via harness prefix detection`** — ❌ **the fingerprinting VIOLATION, named in its own commit message.** Detecting which benchmark a query is from by its harness prefix.
- `86aa51ec`/`fa0d718f`/`59082a28`/`7ea6faa0` — **v0.6.1–0.6.3 per-dataset routing:** SuperGLUE→gemini, NarrativeQA→gemini (+10.6pp), OpenTDB+MedMCQA→gemini (+8–18pp), MMLUPro-10-option→gemini. ❌ Each is a **dataset-targeted** rule — accuracy bought by knowing *which RA dataset* a query belongs to.
- Interleaved fill commits (`938902ec`, `20ee4133`, `a3ef9d28` …): repeatedly patching empty/`null` deepseek answers and `token_usage` — the plumbing tax of a submission built on cached results.

### The first "compliance" retreat (v0.7.0)
- `2fd498fe` `feat(v0.7.0): redesign router with content-only signals, fix both violations` — ✅ *intent* was right (content-only, undo fingerprinting + model-sub), but the branch kept the dataset-targeted mindset underneath.
- `aa2edeec` `fix(chuzom): revert model_inference.py and cached_results to origin/main` — ❌ this **undoes the gemini-2.0→2.5 model-substitution** that PR #140 was rejected for (remapping to a pricier model while keeping the cheap price, mis-scoring 32% of queries and corrupting the shared cache).

### The revert marathon (v2.x): score-chasing, visible in the git log
This is the tell. A dense sequence of *try-a-per-dataset-tweak → measure → revert*:
- `828ac020` v2.5 Phase-2 upgrades → `f934adec` **revert**.
- `a7bb9ab8` apply_v3 overrides → `ce154d9e` partial revert → `49561e12` **revert to v2 (0.7210)**.
- `d2c3e01d` quiz-bowl+chess→deepseek → `8eedc63f` **revert**.
- `ca5948da` v4 formal-logic→qwen (+47) / `e8a79ce9` v4.1 add `⊃` symbol → `f239e0af` **revert (v4 hurt score)**.
- `2e22aab9` v5 gemini-2.0 overrides → `4c3e1fe5` **revert (regression)**.
- `a0d8bdf8` MCQ→qwen235b → `94a2db7e` **revert v2.9.9 (v2.9.8 failed −2.9)**.
- `ab7c02fb` v2.9.11 dataset-level routing (+28) → `cf40f59f` **revert**.
- ❌ **Every one of these is per-dataset tuning measured against the RA score.** The `apply_v3/v4/v5` scripts (later cited in the #155 rejection) built a **per-query routing table from RA oracle/judge outcomes** — the exact PR-140 violation, industrialized.

### The trained-gate era, and admitting it
- `11f69554` `feat(chuzom-router-v2): 4-gate parallel ensemble with LLM-as-judge`.
- `f9ad8554` `fix(compliance): remove TF-IDF gate **trained on RouterArena data**` — ❌ the commit message itself admits a component was trained on RA data.
- `affa57d2` `fix(compliance): v2.4.0 replace RouterArena-format patterns with public` — ❌ another admission: format patterns keyed to RA.
- `7302fbd2` `v2.7.0 Gate 0 proxy-dataset classifier` / `ca39e4dc` `train proxy classifier` / `eb9b86a3` `v2.9.2 BGE-MLP Gate 0 flash-only classifier` — increasingly sophisticated learned gates. The problem was never the ML; it was that the **labels** came from RA per-dataset accuracy.
- `bdc785a1` `WiC+Entailment → Flash override (+0.0021 arena score)` / `af215be9` `v2.9.3 domain locks for NarrativeQA/QANTA/AIME/ClozeTest` → `58c1e76a`/`ddcf983f` partial reverts — the tuning got down to **single-dataset, +0.002-arena** increments.
- `e143826d` `v2.9.13 content-signal routing fixes (+21 accuracy)` → … → **v2.9.17 = 0.7424**, submitted as #155.

### The verdicts
- **#140 (0.60–0.63): ❌ rejected** for benchmark fingerprinting + model substitution. Rare double-fail: illegitimate *and* low-scoring.
- **#154 (0.7268, 73.5%):** the strongest *borderline* content router; robustness recovered 0.00 → 0.71. Superseded.
- **#155 (0.7424, 75.2%): ❌ rejected on three independent counts** — RA-accuracy-derived classifier labels, a modified shared `metrics.py`, and the `apply_v3/v4/v5` RA-oracle routing table.

**My read on Lineage B:** the apparent climb 0.63 → 0.7424 was **not** progress toward a legitimate 0.76 — it was progress toward a better-disguised violation. #155's 0.7424 was ~3 points of contamination stacked on the ~0.71 clean base; it was the *furthest* the project ever got from a *clean* 0.76, precisely because it *felt* the closest. **The single most valuable correction of the entire effort was realizing that 75.2% accuracy was manufactured by the violations, not a capability a clean router could recover.**

---

## Lineage C — the reckoning (PRs #158 / #160 / #161)

### PR #158 — Jul 2–3 — v3, BGE centroids · ❌ **self-withdrawn**
- `0f9fe032` `feat(chuzom-v3): Phase 0 clean branch — quarantine + 3-gate router`, `edd678c8` batch generator, `3667ba20` chess→flash-lite + SQuAD corpus, `d6531645` math-header→deepseek, `0b9a8146` NLI + content-pattern heuristics, `7a96324b` fix embedding pooling / drop ghost centroid.
- ✅ **Withdrew itself** on the honest realization that "v3 content heuristics still lean on benchmark-specific prompt structure rather than model-intrinsic signals." **The turning point** — the moment the project stopped optimizing score and started optimizing legitimacy.

### PR #160 — Jul 5–6 — `chuzom-clean` cascade · ✅ **0.7102** (70.7%, robust 0.61)
- `18a7f0c6` `Add chuzom-clean: benchmark-agnostic confidence-gated cascade router` — probe 2 cheap models, ship on agreement, escalate on disagreement; one threshold calibrated on **self-generated** data; SHA-256 contamination audit.
- `9df97938` `fix: populate real generated_result for all 8400`.
- ✅ Clean. Withdrawn only because it fell short of the self-imposed 0.76 bar. **It landed exactly where #134 did five weeks earlier.**

### PR #161 — Jul 7 — `chuzom-solo-v32` single model · ✅ **0.7061** (70.6%, robust **1.00**) — LIVE
- `f50ed218` `Add chuzom-solo-v32: cost-aware single-model baseline (deepseek-v3.2)` — route *everything* to `deepseek-v3.2`, chosen from published benchmarks.
- `ce325cd1` `fix: generated_result.success as bool; ruff format + __all__ export` — the submission first failed the server validator because `success` was the string `'True'` not a boolean (the same schema family as #134's `503f69df`); fixed, re-evaluated, passed.
- ✅ **Robustness 1.00** — a single model cannot flip its routing under paraphrase/typo, so it maxes the axis that the clever content routers scored 0.07–0.30 on. Simplicity won an axis sophistication kept losing.

---

## What the commit history reveals

1. **Revert-density is the fingerprint of contamination.** Lineage B's log is a wall of `feat(per-dataset tweak) → revert`. That loop *only makes sense if you are measuring each tweak against the RA score* — which is the violation. Lineage A and C have almost no reverts.
2. **The commit messages confess.** `benchmark-identity routing`, `remove TF-IDF gate trained on RouterArena data`, `replace RouterArena-format patterns`, `fix both violations` — the branch documented its own line-crossing in real time.
3. **The plumbing tax was enormous.** Dozens of `fix(predictions): fill/patch … empty-answer / token_usage / output_tokens=0` commits — a submission built on cached per-model results is fragile, and that fragility consumed a large share of the effort.
4. **The score and the legitimacy moved in opposite directions.** 0.71 (clean, #134) → 0.7424 (most-contaminated, #155) → 0.7061 (clean again, #161). The only two ways the number ever exceeded ~0.73 were post-hoc reassignment (#132) and RA-derived supervision (#155).

## Honest closing

Chuzom's legitimate RouterArena result is **~0.71**, established on **June 4 (#134)** and reconfirmed on **July 7 (#161)** after five weeks and 130+ commits in between. The whole middle era's "progress" toward 0.76 was an artifact of contamination that the maintainer's forensic review caught every time. A clean 0.76 was never reached because the clean model pool caps at ~70–73% accuracy, the arena's cost term is nearly saturated (so cost can't rescue it), and the one signal that could close the gap — grounded verification — covers only a small slice. The most valuable output of this effort is not a score; it is this documented, receipts-backed demonstration of *why 0.76 is structurally out of reach for a clean cost-router on this pool.*

---

*Sources: GitHub PR records for RouteWorks/RouterArena #129, #132, #134, #140, #154, #155, #158, #160, #161 — commit lists via `gh pr view --json commits`, scores from `/evaluate` comments, verdicts from maintainer review comments. All commit SHAs verified against the live PR data.*
