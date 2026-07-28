# Chuzom on RouterArena — Commit-Level Chronicle

This is the engineering post-mortem for Chuzom's RouterArena submissions across three branch lineages:

- **Lineage A — `llm-router`**: PRs **#129/#132/#134**, the early self-consistency router. It established the clean ceiling at roughly **0.71–0.72**, with PR **#134** merged at **0.7126**.
- **Lineage B — `chuzom-router` / `chuzom-router-v2`**: PRs **#140/#154/#155**, the long version marathon from **v0.4.1** through **v2.9.17**. It produced the most apparent progress, including **0.7424**, but the lift came from RouterArena-specific routing and score feedback.
- **Lineage C — the reckoning**: PRs **#158/#160/#161**, where the project finally stopped treating the arena score as a tuning signal and rebuilt cleanly. Scores collapsed back to **0.7102** and **0.7061**.

The headline is blunt: **the legitimate Chuzom ceiling was about 0.71–0.73. Everything above that was contamination, and it was caught.** The highest number, **0.7713**, came from post-hoc reassignment in PR **#132**. The highest standing `chuzom-router` score, **0.7424**, came from per-dataset and per-query fitting in PR **#155**. Neither was a legitimate path to **0.76**.

Source note: the local Chuzom checkout retains the main-project commits and RouterArena artifacts, but not all old RouteWorks/RouterArena PR branch refs. Where commit hashes are present locally, they are included. Where the old PR-only commits are no longer locally reachable, this chronicle uses the exact PR numbers, versions, model names, scores, and dates preserved in `routerarena_clean/CHUZOM_ROUTERARENA_HISTORY.md`, the current `routerarena_submission` artifacts, and the user-provided commit data.

## Lineage A — `llm-router` (PRs #129/#132/#134)

### PR #129 — v1 submission, June 2, 2026 — score 0.7074

✅ **Clean, but not enough.**

The first Chuzom-related RouterArena submission was still essentially the `llm-router` lineage. It used a self-consistency style router: run cheap candidates, compare outputs or confidence, and escalate when the cheap path looked unreliable. PR **#129** scored **0.7074**, with **71.1% accuracy** and **0.30 robustness**.

Technically, this was the right kind of mechanism. It routed on live model behavior rather than the identity of the benchmark. The weakness was not compliance; it was capability. The model pool and routing signal could not reliably identify the hard tail. The score said the clean approach was real, but it also said the distance to **0.76** was large.

Why it helped the 0.76 goal:

- It proved Chuzom could produce a valid low-cost router around **0.71**.
- It established a clean baseline before the later contaminated lift.

Why it did not solve the goal:

- **0.7074** was roughly five arena-score points short.
- Robustness at **0.30** showed that routing decisions were already brittle under perturbation.

### PR #132 — June 4, 2026 — local eval baseline 0.7139, rejected peak 0.7713

✅ **0.7139 baseline clean enough to be plausible.**  
❌ **0.7713 peak illegitimate.**

PR **#132** improved the `llm-router` baseline to **0.7139**, with **71.8% accuracy** and **0.24 robustness**. That was a real, incremental improvement over PR **#129**.

The problem was the later jump. The PR peaked at **0.7713** with **78.0% accuracy**, which looked like the first genuine pass over the **0.76** target. It was not. The gain came from **post-hoc reassignment**: changing predictions after seeing which answers scored. That is equivalent to routing with feedback from the benchmark's answer key.

The maintainer rejected the peak. The rule was simple: a router can use public model priors, intrinsic prompt features, and live model behavior, but it cannot use RouterArena's own outcomes to decide future predictions.

Why it moved toward 0.76:

- Numerically, **0.7713** crossed the target.
- It showed the model pool had enough oracle capacity if one could magically pick the right model per query.

Why it moved away from a legitimate 0.76:

- The reassignment signal was exactly the forbidden signal: benchmark-scored outcomes.
- It created the first false anchor. From this point onward, **0.76** felt reachable because the project had seen a number above it, but that number did not represent a deployable router.

### PR #134 — June 4–13, 2026 — self-consistency Tier-1A/1B + integrity gates, merged at 0.7126

✅ **Clean and merged.**

PR **#134** was the disciplined version of the `llm-router` idea. It kept the self-consistency architecture but added explicit submission-integrity gates to prevent a repeat of PR **#132**. It was accepted and **merged** at **0.7126**, with **72.1% accuracy** and **0.30 robustness**.

The meaningful technical change was not a new trick; it was restraint. Tier-1A/Tier-1B self-consistency made routing decisions from model behavior at inference time. Integrity gates made sure no answer-key-derived reassignment or mutated evaluator behavior slipped into the submission.

Why it helped:

- It is the only accepted Chuzom RouterArena submission in the record.
- It is the clean reference point for every later comparison.
- It proved the legitimate score was around **0.71–0.72**.

Why it did not reach 0.76:

- Self-consistency did not separate correct from incorrect strongly enough on the hard tail.
- The clean routing signal plateaued at the same place the final clean submissions later returned to.

## Lineage B — `chuzom-router` version marathon (PRs #140/#154/#155)

This is the core failure mode. The same branch moved from **v0.4.1** through **v2.9.17**, with more than **120 commits** across PRs **#140/#154/#155**. The visible arc was an apparent climb:

- PR **#140**, June 13, 2026: **0.60–0.63**, rejected.
- PR **#154**, June 23, 2026: **0.7268**, **73.5% accuracy**, **0.71 robustness**, closed/superseded.
- PR **#155**, June 24, 2026: **0.7424**, **75.2% accuracy**, **0.70 robustness**, rejected.

The engineering reality was worse: the branch increasingly learned the benchmark.

### Retained local precursor commits

These are the local Chuzom commits that fed the RouterArena submission path:

| Commit | Date | Subject | Meaning |
|---|---:|---|---|
| `5d278f5` | 2026-06-06 | `feat(bench): RouterArena dataset converter (HF parquet → Chuzom JSONL)` | Added local conversion from RouterArena-format data into Chuzom's benchmark pipeline. Useful for measurement, but it opened the door to treating RA as a development dataset. |
| `522201d` | 2026-06-06 | `ci(routerarena): regression gate on every PR — Part 7 rec #6` | Added a RouterArena regression gate. Good for guarding a frozen clean submission; dangerous if it becomes an optimization loop. |
| `3affec4` | 2026-06-09 | `chore(ci): disable routerarena-regression auto-trigger until submission is on the table (#53)` | Correctly recognized that automatic RA-score feedback during ordinary development was risky. |
| `fd5d531` | 2026-06-13 | `feat: v0.4.1 — session summary fix, deadline guard, badge + README refresh` | Main release that `routerarena_submission` later synced to as **v0.4.1**. |
| `aea7664` | 2026-06-13 | `feat(routerarena): sync submission router to v0.4.1 classifier` | Created the RouterArena submission router from the production classifier. This is the start of the `chuzom-router` branch lineage in the local tree. |
| `30cf0cf` | 2026-06-13 | `feat(routerarena): regenerate predictions from full 8400-entry dataset` | Generated full-split predictions. This was necessary for submission, but it also meant every later routing tweak could be judged against RA outcomes. |
| `eaaafbd` | 2026-06-14 | `fix(ci): sync plugin manifests to 0.4.2, fix routerarena complexity signals` | Adjusted complexity signals after RouterArena exposure. This is already suspicious: "fixing" complexity because of RA behavior is close to fitting. |
| `a014c35` | 2026-06-14 | `docs(release): add v0.4.2 changelog, bump routerarena router version string` | Formalized **v0.4.2** in the RouterArena file. |
| `e6adcca` | 2026-06-14 | `fix(classifier): prevent math benchmark prefix from triggering deep_reasoning` | Directly handled a math benchmark prefix. This was technically useful but compliance-hostile because it keyed on harness phrasing. |
| `7368902` | 2026-06-14 | `style: apply ruff-format to routerarena submission router` | Mechanical formatting. No score significance. |
| `4ebe1a2` | 2026-06-23 | `feat(router): add competition-math fast-path for AIME/MATH (v0.5.2)` | Added the AIME/MATH fast-path that later appeared in PR **#154**. This helped score but leaned on benchmark identity. |

### v0.4.1 — MCQ fast-path, 87.7% cheap routing

❌ **Not clean enough.**

The **v0.4.1** RouterArena submission router introduced a very aggressive multiple-choice fast path. The current `routerarena_submission/router/chuzom_router.py` still documents the DNA:

- `\boxed{X}` anywhere in the prompt → `google/gemini-3.1-flash-lite`
- MCQ coverage: MMLU, MMLUPro, OpenTDB, ArcMMLU, GeoBench, PubMedQA, MathQA, MedMCQA, Ethics, SuperGLUE, GSM8K, MusicTheoryBench, SocialiQA
- Effect: about **87.7%** of prompts went to the cheap model family in the version arc described by the PR data.

The engineering motivation was straightforward: RouterArena's arena score is accuracy-cost weighted, and cheap routing helps the cost term. But cost was never the real bottleneck. Accuracy was. Routing most MCQ prompts cheaply helped only if the cheap model was competitive. When the cheap model was wrong, the router had no clean signal to know it.

The compliance issue was worse. `\boxed{X}` was not intrinsic user content. The file's own comment says it was **"LaTeX notation injected by RouterArena's dataset builder into prompt_formatted."** That makes it benchmark-wrapper recognition, not general routing.

Why it helped:

- It lowered reported cost.
- It stabilized a broad class of prompt formats.

Why it hurt legitimacy:

- It routed on a RouterArena formatting artifact.
- It optimized the benchmark's prompt wrapper rather than a model-intrinsic capability signal.

### v0.5.x — deep-reasoning tier and competition-math routing

⚠️ **Technically plausible, but benchmark-shaped.**

The **v0.5.x** arc added deeper reasoning tiers and special handling for math. The retained local commit is:

- `4ebe1a2`, 2026-06-23: `feat(router): add competition-math fast-path for AIME/MATH (v0.5.2)`

The current router describes the mechanism:

- `Context: None` plus LaTeX mathematical notation → `qwen/qwen3-235b-a22b-2507`
- The rule fires after the MCQ check so MMLUPro MCQ remains on flash-lite.
- It is explicitly described as covering **AIME** and **MATH**.

This likely explains the PR **#154** bump to **0.7268**, **73.5% accuracy**, **0.71 robustness**. It was one of the strongest apparent results before PR **#155**.

Why it helped:

- AIME/MATH-style problems are genuinely harder than ordinary MCQ.
- `qwen/qwen3-235b-a22b-2507` was a better fit than the cheap MCQ path for competition math.

Why it was still a problem:

- `Context: None` plus RA-formatted LaTeX is not an organic content signal; it is a benchmark wrapper signature.
- The rule names the datasets it is meant to catch. That is not a general router; it is a dataset detector.

Verdict: **borderline at best** for PR **#154**, and a warning sign for what followed.

### v0.6.0 — benchmark-identity routing via harness prefix

❌ **ILLEGITIMATE.**

The **v0.6.0** branch version introduced what the commit data calls **"benchmark-identity routing via harness prefix."** This is the clearest early violation in Lineage B.

The local `routerarena_submission/router/chuzom_router.py` still contains the same class of rules under "Benchmark template fast-path":

- `^Generate an executable Python function` → code/moderate
- `^Please read the following context and answer the question` → query/moderate
- `^Please read the following multiple-choice questions` → query/moderate
- `^Translate the following sentence` → generate/simple
- `^Read the following passage and answer the question by choosing` → query/moderate
- `^Consider the word "` → query/simple
- `^You are given a question about chess moves` → analyze/moderate

These are not abstract task features. They are harness prefixes. The router was identifying the benchmark task family before selecting a model. This can improve a local eval score because it turns routing into "which RA dataset is this?" and then "which model did well on that dataset?"

Why it moved toward 0.76 numerically:

- It reduced random misclassification caused by generic keyword heuristics.
- It let the router select specialists for task families rather than infer from noisy prompt text.

Why it moved away from a legitimate 0.76:

- It fingerprinted RouterArena's prompt construction.
- It did not generalize to paraphrased or differently wrapped versions of the same task.
- It turned the benchmark into the routing feature space.

This is the first unambiguous **❌ ILLEGITIMATE** step in the `chuzom-router` marathon.

### v0.6.1–v0.6.3 — per-dataset Gemini routing

❌ **ILLEGITIMATE.**

The **v0.6.1–v0.6.3** commits layered per-dataset routing onto the harness-prefix design. The user-provided commit data names these datasets directly:

- **NarrativeQA**
- **OpenTDB**
- **MedMCQA**
- **SuperGLUE**
- **MMLUPro**

The current artifacts preserve the pattern. `scripts/routerarena/build_submission.py` maps dataset names to subjects:

- `NarrativeQA` → `narrative`
- `PubMedQA`, `MedMCQA`, `MMLUPro_health`, `MMLUPro_biology` → `medical`
- `SuperGLUE-*` → `reasoning`
- `MMLUPro_*` → `history`, `reasoning`, `physics`, `medical`, or `code`
- `OpenTDB_*` appears in the MCQ dataset table.

The model pool in `src/chuzom/policies/routerarena_tuned.yaml` then maps some of those subjects to models including:

- `openrouter/google/gemini-3.1-flash-lite`
- `openrouter/deepseek/deepseek-v4-flash`
- `openrouter/qwen/qwen3-235b-a22b-2507`
- `openrouter/qwen/qwen3-coder-next`
- `openrouter/anthropic/claude-sonnet-4`

The branch-level data specifically calls out **per-dataset Gemini routing**. That means the router was no longer merely saying "this is a medical question"; it was learning that a named RA source should go to a named Gemini model. This is contamination even if the input prompt never contains the literal dataset name, because the routing table was derived from benchmark categories and observed outcomes.

Why it helped:

- Dataset-specific routing often gives immediate score gains.
- Gemini flash variants were cheap and strong enough on many short-answer or MCQ groups to improve the cost-adjusted score.

Why it hurt legitimacy:

- Dataset-targeted routing is exactly benchmark fitting.
- It cannot be justified as user-facing general routing when the rule exists because of NarrativeQA/OpenTDB/MedMCQA/SuperGLUE/MMLUPro performance.

### Gemini 2.0 → 2.5 model substitution + `cached_results` edit, later reverted in `aa2edeec`

❌ **ILLEGITIMATE.**

PR **#140** was rejected partly for model substitution. The router remapped **`gemini-2.0-flash`** to **`gemini-2.5-flash`** while retaining the old cost assumptions. The existing shorter history records that this mis-scored about **32%** of queries and corrupted the shared cache path. The user-provided data identifies the later revert commit as **`aa2edeec`**.

This was not merely a bad model alias. It changed the evaluated model without a corresponding truthful cost/model accounting path. The `cached_results` edit made it worse because it touched the evaluation substrate rather than only the router.

Why it appeared to help:

- `gemini-2.5-flash` was stronger than `gemini-2.0-flash` on many prompts.
- Keeping the old price made the arena score look better than the true cost-quality tradeoff.

Why it was disqualifying:

- The evaluator believed it was scoring one model/cost combination while the router used another.
- Editing shared cached results polluted reproducibility.
- Reverting in **`aa2edeec`** was necessary, but the violation had already invalidated the score path.

### v0.7.0 — content-only redesign to fix both violations

✅ **Directionally clean.**  
⚠️ **Still carrying benchmark-shaped scars.**

After PR **#140** exposed the two obvious violations, **v0.7.0** tried to redesign routing around content only:

- Stop using direct harness prefixes as final authority.
- Stop substituting Gemini versions under stale pricing.
- Move back toward generic prompt features and model capability.

The retained main-branch commits around the same date are:

- `44d2ba9`, 2026-06-30: `release: v0.7.0`
- `edc0d11`, 2026-06-30: `Merge origin/main (dependabot deps) into v0.7.0 release`
- `d2d3e4c`, 2026-06-30: `fix(ci): repair 11 stale tests + 1 lint error on v0.7.0`
- `fc36350`, 2026-06-30: `Merge pull request #106 from Chuzom/fix/v0.7.0-ci`

The RouterArena branch's **v0.7.0** was a compliance repair, not a true capability breakthrough. The right instinct was there: route on content, not identity. But the branch had already been trained by RA outcomes. The content-only rules were still selected and evaluated in the shadow of the benchmark.

Why it helped:

- It acknowledged that model substitution and harness-prefix routing were not defensible.
- It moved the router back toward a reviewable design.

Why it did not unlock 0.76:

- Removing the violations removed much of the apparent score gain.
- The clean content signal still did not identify the correct model often enough.

### The `apply_v3` / `apply_v4` / `apply_v5` override scripts and the long revert saga

❌ **ILLEGITIMATE pattern.**

The `apply_v3`, `apply_v4`, and `apply_v5` scripts were the defining PR **#155** failure. They built or applied per-query and per-dataset overrides from RouterArena oracle/judge feedback. Once that happened, the router was no longer a router; it was a replay system for benchmark-discovered winners.

The user-provided commit data names five major try-then-abandon cycles:

1. **v2.5 → revert**
2. **v4 formal-logic → revert**
3. **v5 → revert**
4. **v2.9.8 → revert**
5. **v2.9.11 → revert**

That is **five revert cycles** around per-dataset tweaks. The count matters. One mistaken tweak can be an engineering error. Five cycles show an optimization process: try a targeted rule, inspect RA movement, keep or revert based on the score. That is exactly score-chasing on RouterArena outcomes.

Why the overrides helped score:

- Per-query or per-dataset rules can exploit model complementarity almost like an oracle.
- Formal logic and similar small buckets can move a surprising number of leaderboard points if the router flips the exact rows that were wrong.

Why they were fatal:

- They used RA outcomes to tune routing.
- They produced fragile rules with no claim to out-of-distribution validity.
- The revert-heavy trail itself became evidence of fitting.

### TF-IDF gate trained on RA data, removed by `f9ad8554`

❌ **Before removal: illegitimate.**  
✅ **Removal: clean-up step.**

The branch introduced a TF-IDF gate trained on RouterArena data, then removed it in:

- **`f9ad8554`** — `remove TF-IDF gate trained on RouterArena data`

A TF-IDF classifier can be a legitimate router component if trained on independent data. Here it was trained on RA data, so it learned benchmark distribution and labels. Removing it was a necessary compliance repair.

Why it helped score:

- TF-IDF is good at recognizing dataset clusters and repeated phrasing.
- On a fixed benchmark, lexical clustering can recover the hidden source task.

Why it hurt legitimacy:

- Training on RA data made the gate a benchmark classifier.
- Even if the model labels were later generalized, the learned features came from the prohibited distribution.

### Gate-0 proxy classifier — v2.7.0, PR #140

❌ **Rejected.**

PR **#140** is summarized in the preserved history as **chuzom v2.7 · Gate-0 proxy classifier**, scoring **0.60–0.63** and then being rejected.

Gate-0 tried to cheaply classify prompts before invoking stronger routing or model selection. In principle, a proxy classifier is allowed. In this implementation, the proxy inherited the same contaminated inputs: harness prefixes, benchmark families, and RA-derived model preferences.

Why it helped:

- It reduced cost and made routing deterministic.
- It gave a place to encode high-impact fast paths.

Why it failed:

- It encoded benchmark identity rather than general difficulty.
- It was rejected before it even achieved a compelling score.

This was the rare case of being both **illegitimate and not very good**.

### BGE-MLP — v2.9.2

❌ **Not clean in this lineage.**

The **v2.9.2 BGE-MLP** step moved from hand-coded lexical rules toward embedding-based classification. Architecturally, that looked more respectable: encode the prompt with a BGE embedding model, then use an MLP to choose a route.

The issue was provenance. In this branch, the classifier was part of the same RA-optimized loop. If the BGE centroids, labels, or MLP targets were derived from RA per-dataset accuracy, RA prompt clusters, or RA score feedback, then the embedding layer only disguised the same contamination. It made the rule less obvious, not more legitimate.

Why it helped:

- Embeddings generalize better than brittle regexes.
- An MLP can capture soft domain boundaries that hand rules miss.

Why it still moved away from a legitimate 0.76:

- The training target was the problem. A clean architecture with contaminated labels is still contaminated.
- It made the router harder to audit while preserving the score-chasing behavior.

### v2.9.13 → v2.9.17 — final push to 0.7424, rejected

❌ **ILLEGITIMATE.**

The version marathon culminated in **v2.9.17**, evaluated in PR **#155** on **June 24, 2026**, with:

- **Arena score:** **0.7424**
- **Accuracy:** **75.2%**
- **Robustness:** **0.70**
- **Outcome:** rejected

This was the closest-looking result to a legitimate **0.76** after PR **#132**, but it was not real progress. The preserved history records three independent disqualifiers:

1. Classifier labels were derived from RA per-dataset accuracy, for example rationales like **AIME flash-lite=0.35, deepseek=0.72**.
2. Shared evaluator code such as `metrics.py` was modified to loosen scoring behavior in the submission's favor.
3. `apply_v3` / `apply_v4` / `apply_v5` scripts built per-query routing tables from RA oracle/judge scores.

Why it helped numerically:

- It approximated the oracle router more than any clean version did.
- It exploited dataset-specific model strengths and corrected known failures.

Why it was rejected:

- It used the benchmark as training data.
- It changed shared evaluation behavior.
- It converted score feedback into routing policy.

The key lesson: **0.7424 was not the clean router almost reaching 0.76. It was the contaminated router almost exposing exactly how much lift contamination could buy.**

## Lineage C — the reckoning (PRs #158/#160/#161)

### PR #158 — chuzom v3, 3-gate BGE, July 3, 2026

❌ **Self-withdrawn because it was still benchmark-specific.**

After PR **#155**, the project tried a more formal **v3 3-gate BGE** router. The idea was to replace obvious hand-tuned rules with a gate stack:

- structural/content gate
- embedding/centroid gate using BGE
- model-selection gate

This looked cleaner than regex fast paths, but the project's own later plan admits the problem. `Docs/ROUTERARENA_CLEAN_075_PLAN.md` says the legacy `chuzom_router.py` **and PR #158's "Gate 2"** routed by recognizing RouterArena-injected harness templates, including:

- `\boxed{X}`
- `Context: None` + LaTeX
- `Please solve the following mathematical problem`
- `Please read the following question and provide the correct answer.`
- Natural-language-inference wrappers such as `Premise` / `Hypothesis`

The PR was self-withdrawn. That was the right decision.

Why it helped:

- It marked the first serious internal admission that the previous score-chasing was structurally contaminated.
- It started the move toward provenance and contamination auditing.

Why it did not count:

- BGE does not make benchmark templates clean.
- The router still knew too much about RA prompt construction.

### PR #160 — `chuzom-clean`, July 5, 2026 — two clean commits, 0.7102

✅ **Clean.**

PR **#160** was the clean rebuild: `chuzom-clean`, a confidence-gated cascade calibrated only on self-generated data, with a provenance manifest and contamination audit. It scored:

- **Arena score:** **0.7102**
- **Accuracy:** **70.7%**
- **Robustness:** **0.61**
- **Outcome:** closed/withdrawn because it missed the self-imposed 0.76 bar

The two-commit shape matters. Unlike Lineage B's 120+ commit marathon, this branch did not repeatedly tune against RA score feedback. It built the clean mechanism, submitted it, and accepted the result.

Local supporting artifacts:

- `routerarena_clean/PROVENANCE.md` excludes RA, RouterBench, and the academic benchmarks RA is built from.
- `routerarena_clean/calibrate.py` calibrates against the RouterArena formula without touching RA data.
- `routerarena_clean/ci_template_guard.sh` guards against RA-template literals.

Why it helped:

- It restored legitimacy.
- It gave a reproducible data firewall.
- It confirmed the clean ceiling had not moved.

Why it missed 0.76:

- The clean gate could not identify the hard tail well enough.
- Without RA-derived labels, accuracy returned to about **0.71**.

### PR #161 — `chuzom-solo-v32`, July 7, 2026 — two commits, 0.7061, robustness 1.00

✅ **Clean.**

PR **#161** stripped the system down to a single-model baseline:

- **Router:** `chuzom-solo-v32`
- **Model:** `deepseek-v3.2`
- **Arena score:** **0.7061**
- **Accuracy:** **70.6%**
- **Robustness:** **1.00**
- **Outcome:** open/live in the preserved July 7 record

The engineering move was intentionally boring. A single-model router cannot leak benchmark identity through routing rules because it has no routing rules. It also cannot flip under paraphrase, which explains the perfect **1.00 robustness**.

Why it helped:

- It gave the cleanest possible lower-bound sanity check.
- It demonstrated that a strong single model was already near the clean cascades.

Why it ended the 0.76 story:

- If `deepseek-v3.2` alone gets **0.7061** and the clean cascade gets **0.7102**, the remaining gap is not a routing polish problem.
- The only prior scores above that band came from contaminated selection.

## What the commit history reveals

### 1. Revert-heavy per-dataset tuning was score-chasing

The Lineage B pattern is impossible to read as ordinary product hardening:

- Add a per-dataset rule.
- Evaluate against RA.
- Keep it if the number rises.
- Revert it if it falls.
- Repeat.

The named revert cycles are:

- **v2.5 → revert**
- **v4 formal-logic → revert**
- **v5 → revert**
- **v2.9.8 → revert**
- **v2.9.11 → revert**

That is **five** tried-then-abandoned per-dataset tweak cycles. The technical content of each tweak matters less than the process. The process used RouterArena as the training loop.

### 2. The recurring `fix(compliance)` commits were admissions

The branch repeatedly had to "fix compliance":

- remove or soften harness-prefix rules
- undo Gemini model substitution
- revert `cached_results` edits
- remove the RA-trained TF-IDF gate in **`f9ad8554`**
- withdraw PR **#158** because Gate 2 still recognized benchmark-specific prompt structure
- remove RouterArena leaderboard references in local commit `3876ee1` on **2026-07-03**

These fixes were necessary, but they also document the underlying fact: the score gains came from places that had to be removed once reviewed.

### 3. Token usage, empty-answer, and fill/patch commits were symptoms of benchmark harness pressure

The branch also had many fill/patch style fixes:

- patch empty responses
- fill missing answers
- repair `token_usage`
- normalize prediction JSON shape
- adjust cached outputs

Some of these are legitimate engineering hygiene. A submission should not fail because an API response was empty or because token accounting was malformed. But in this history they sat next to per-query override scripts and cache edits. That made them part of a broader pattern: once the project optimized the artifact rather than the router, every output-file detail became a lever.

The clean lesson is narrow:

- ✅ Fixing malformed `token_usage` or retrying empty API calls is acceptable if it preserves the same frozen router.
- ❌ Filling answers or patching outputs based on RA scoring feedback is not routing; it is post-hoc answer repair.

### 4. The final collapse back to ~0.71 was not a failure of the clean rebuild

The collapse from **0.7424** to **0.7102** and **0.7061** was the measurement becoming honest again.

The clean scores line up tightly:

- PR **#129**: **0.7074**
- PR **#132** clean baseline: **0.7139**
- PR **#134** merged: **0.7126**
- PR **#160** clean cascade: **0.7102**
- PR **#161** solo `deepseek-v3.2`: **0.7061**

That is the actual Chuzom capability band.

The contaminated scores line up separately:

- PR **#132** post-hoc peak: **0.7713**
- PR **#155** v2.9.17: **0.7424**

Those are not evidence that Chuzom nearly solved RouterArena. They are evidence that answer-key-adjacent and dataset-specific signals are worth several points.

## Honest closing

The legitimate ceiling never moved.

Chuzom started with a clean `llm-router` around **0.71–0.72**, spent the `chuzom-router` marathon chasing **0.74–0.77** through increasingly benchmark-specific mechanisms, then returned to **0.7102** and **0.7061** when the data firewall was restored.

The branch history is therefore not a story of a router almost reaching **0.76**. It is a story of an engineering team repeatedly rediscovering that **0.76 was only reachable when RouterArena itself leaked into the router**.

The defensible claim is:

✅ **Chuzom can submit a clean, low-cost RouterArena router around 0.71–0.73.**  
❌ **Chuzom did not demonstrate a legitimate path to 0.76 in this commit history.**  
✅ **The final clean branches were better engineering than the higher-scoring contaminated ones.**
