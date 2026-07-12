# Routing Accuracy Improvement Process

## 1. Scope, Compliance Boundary, and Current Evidence

This document defines the only approved process for improving Chuzom's RouterArena (RA) routing accuracy. It is intentionally conservative because this account already has a rejection history: PR-140 and PR-155 were rejected for training, fitting, or tuning router components on RA data, and PR-158 was withdrawn before review for the same root cause. PR-158 matched RA's injected prompt templates verbatim, including `Context: None`, `\boxed{X}`, and "Please solve the following mathematical problem". That was treated as a component fit to RA data even though the claimed source looked like a public dataset.

The core rule is simple: RouterArena is evaluation-only. No router component may be trained, fit, tuned, thresholded, selected, ranked, or justified using RA-derived supervision. For this process, RA-derived supervision includes RA per-dataset accuracy, gpt-4o-mini judge scores, oracle entries, RA prompt-template fingerprints, and any per-query or per-category routing table built from RA outcomes. Modifying `llm_evaluation/metrics.py` or `compare_router_accuracy.py` is also forbidden.

Permitted inputs are narrower and must be auditable:

| Input | Permitted Use | Boundary |
|---|---|---|
| Self-owned generated corpora | Train or calibrate router components | Must be generated without RA prompts, RA labels, RA categories, or RA template strings |
| External public prompt corpora | Calibration only if disjointness is provable | Must pass a documented non-overlap gate |
| Public model capability benchmarks | Model pool selection and expected accuracy estimates | May not be transformed into RA per-category routing tables |
| Live inference signals | Routing at inference time | Agreement, entropy, semantic distance, and format confidence are allowed because they are computed per query without labels |
| Frozen RA measurement | Evaluation only | One sealed touch; no score-driven iteration |

The current design in `router_core.py` is a confidence-gated cascade: probe two cheap models; if they agree, ship the cheap answer; if they disagree, escalate. This is label-free because cross-model agreement is a live correctness signal, not a classifier trained on RA outcomes.

The strongest empirical lesson so far is that the gate is not the primary bottleneck for the current pool. On a clean 140-prompt run, cheap-alone scored 73.2%, strong-alone 74.8%, the binary agreement gate scored 76.9% with arena 0.769, and a learned confidence head scored only 0.740. The learned head was an isotonic-calibrated logistic regression over agreement, self-consistency at k=3, structural features, and length features, trained on 298 self-generated labeled examples. It overfit to easy self-generated math data and learned to almost never escalate. The pool oracle ceiling was only 78.7%, so routing-policy headroom above the simple binary gate was under 2 points. For this pool, accuracy improvement must primarily come from raising the model pool's union accuracy, not from building a fancier gate.

The existing `proxy_gen.py` corpus remains useful for compliance and plumbing, but not for RA-difficulty estimation. It covers nine self-owned domains, three Bloom difficulties, three metric types, seed `20260706`, and code-computed ground truth. It is disjoint from RA by construction because it does not use RA's 44 categories or source rows. However, it is too easy: strong-ish cheap models score around 99% even on the "hard" stratum, while cheap models are around 70% on RA. RA difficulty comes from knowledge breadth, multilingual content, natural-language ambiguity, adversarial phrasing, and robustness. The `proxy_gen.py` docstring already flags that free-text generation and translation are under-covered because computed gold references cannot be self-generated easily.

The target is arena score greater than 0.76. Arena score is a weighted harmonic mean of accuracy and log-cost with beta 0.1; cost is normalized log2 between $0.0044 and $200 per 1k. Full rank averages six metrics: arena score, three optimality-ratio metrics, robustness, and routing latency overhead. Known reference points are Nadir at 0.7517 with a similar pool plus an external audited RouterBench confidence head, vLLM-SR at 0.7530 and $0.30/1k, and Sqwish at 0.7527 and $0.18/1k.

## 2. Difficulty Proxy Design: Disjoint First, RA-Like Second

The proxy must support two decisions without using RA feedback: whether a candidate model pool has enough union accuracy, and whether a routing policy captures enough of that union accuracy at acceptable cost. The previous computed-answer proxy is compliant but not difficult enough. The replacement must include tasks that cheap models genuinely fail while remaining provably disjoint from RA.

### 2.1 Proxy Options and Risk Ranking

| Option | Fidelity to RA Difficulty | Compliance Risk | Recommended Role | Reason |
|---|---:|---:|---|---|
| A. Harder self-generated, self-owned tasks | Medium-high | Lowest | Backbone | Every prompt and answer is owned by the project; no source-row overlap is possible |
| B. LLM-generated novel items with self-verified or self-defined answers | Medium-high | Low-medium | Expansion set | Novel prompts can mimic broad task style, but provenance of the generator must be documented |
| C. Held-out public source slices provably not in RA | Highest | Highest | Gated audit-only calibration slice | Public benchmarks are allowed, but RA is curated from these families, so non-overlap must be proven |

The recommended blend is A as the mandatory backbone, B as a controlled diversity expansion, and C only behind a hard disjointness gate. No component may depend solely on C, and C must never be used to build RA-category routing tables.

### 2.2 Option A: Harder Self-Generated Tasks

The next proxy generation phase must move beyond short computed arithmetic into four families:

| Family | Concrete Task Shape | Ground Truth | Why It Reproduces RA-Like Difficulty |
|---|---|---|---|
| Long-horizon state tracking | 12-40 operations over an inventory, graph, ledger, calendar, or game state | Deterministic simulator | Errors require maintaining state across long context, not just computing a formula |
| Constraint-following under adversarial phrasing | Answer must satisfy format, exclusion, ordering, and transformation constraints | Validator plus exact expected answer where possible | RA robustness penalizes brittle interpretation under paraphrase and typo perturbation |
| Multi-hop synthetic knowledge graphs | Proxy defines entities, facts, dates, relations, and exceptions in the prompt | Graph query engine | Tests retrieval and composition over novel facts without relying on memorized public benchmark answers |
| Perturbed multilingual and mixed-register instructions | Synthetic facts plus instructions in translated or code-switched language | Same simulator or graph engine | Adds RA-like multilingual and instruction-normalization difficulty without using WMT or RA source rows |

These tasks stress context binding, distractor rejection, rule priority, and language normalization. The answer is self-owned: the prompt defines the world, the simulator computes the result, and no benchmark label is copied.

Minimum specification for the A-backbone proxy:

| Requirement | Threshold |
|---|---:|
| Total items per regeneration | At least 2,400 |
| Distinct families | At least 4 |
| Seeds | At least 5 independent seeds |
| Long-context share | At least 20% above 1,500 input tokens |
| Perturbed phrasing share | At least 30% with paraphrase, typo, distractor, or reordered constraints |
| Multilingual/code-switched share | At least 10% |
| Cheap-model hard-stratum accuracy target | 60-80%, not above 85% |
| Strong-model hard-stratum accuracy target | At least 5 points above cheap pool average |

If cheap models exceed 85% on the hard stratum, the proxy is not hard enough for routing-policy selection. The generator must increase number of hops, distractor count, state length, or constraint density before any learned head is retried.

### 2.3 Option B: LLM-Generated Novel Items

An LLM may be used to generate new questions in RA-like styles and broad domains, but it must not be asked to reproduce RA prompts, categories, templates, or source dataset rows. The generation prompt should request novel tasks with self-contained facts or computed answers. Examples include:

| Generated Item Type | Verification Method |
|---|---|
| Synthetic science or history mini-passages followed by questions | Answer must be entailed by the generated passage; verifier checks span or structured fact |
| Novel math word problems | Independent code solver or symbolic checker |
| Fictional legal, medical, or finance scenarios | Answer derived from rules embedded in prompt, not real external doctrine |
| Translation-like transformations over invented controlled language | Deterministic grammar or bilingual glossary defined in prompt |

Compliance nuance: using an LLM to generate items is not training on RA. Even if the generator was pretrained on public datasets that RA also draws from, the router is not receiving RA-derived supervision unless the generated corpus copies RA source rows, injected templates, labels, or outcomes. The risk is contamination with benchmark rows or prompt fingerprints, not the generator's training history. Store generator prompts, generated items, verification scripts, seeds, model names, and normalized hashes. Reject items that contain banned RA template literals or high-similarity matches to known public benchmark rows.

Option B adds natural-language ambiguity and topical variety. It may not define policies like "RA math goes to model X"; it may only support general model-pool and confidence-calibration decisions.

### 2.4 Option C: Provably Disjoint Public Source Slices

RA is curated from approximately 23 public open-source academic datasets and mirrors, including MMLU, ARC, GSM8K, MATH, SQuAD, HumanEval/MBPP, TriviaQA, NarrativeQA, ChessInstruct, WMT, SuperGLUE, FinQA, PubMedQA, and QANTA. Calibrating directly against these is risky because RA's test items may be sampled verbatim from them. "Disjoint" must be proven, not assumed.

Public benchmarks and thresholds tuned on data disjoint from RA are permitted. A public-source calibration slice is legitimate only if it passes this protocol:

1. Define the candidate corpus with exact dataset name, version, split, license, mirror URL, retrieval date, and row identifiers.
2. Normalize each candidate prompt using the same deterministic function: Unicode NFC, strip leading/trailing whitespace, collapse internal whitespace, lowercase, remove harness-only boilerplate inserted by the local loader, and preserve answer options.
3. Hash each normalized candidate prompt with SHA-256.
4. If RA public `sub_10` or README fixtures are available, normalize and hash those prompts with the same function and require zero exact hash overlap.
5. If the full RA prompt list is available for audit but not for training, perform the same hash check as an audit artifact only. The hashes may be used to prove non-use, not to select examples by difficulty or category.
6. If the full RA prompt list is not available, use a different split, version, year, license lineage, or mirror that can be shown to be excluded from RA's sampled rows. Examples: post-RA-release benchmark versions, author-defined dev splits when RA samples test, or a corpus whose license/source is not part of RA's documented sources.
7. Run near-duplicate filtering with character 5-gram MinHash or embeddings. Reject candidates above a pre-registered threshold: Jaccard at least 0.85 or embedding cosine at least 0.92 against any known RA/public fixture prompt.
8. Record all rejected rows and reasons in `PROVENANCE.md` or a linked audit appendix.

Option C has the best fidelity because RA really does mix these dataset families, but it is the easiest place to repeat the PR-158 failure mode. It must be a small validation slice, not the process backbone. It may not introduce RA's 44 categories into the router, and it may not produce a per-dataset routing table.

## 3. Estimating Per-Model RA Accuracy from Public Information

Since the real RA set can be touched essentially once, model selection needs a public-information estimator. Its output is not a claimed RA score; it is an expected accuracy range for pre-shot model selection.

The key correction is that RA accuracy is lower than many headline public benchmark scores. Cheap models with strong public MMLU-style numbers measured around 70% on RA. The 150-prompt run with official `metrics.py` produced 69.6% accuracy and arena 0.700 for deepseek-v3.2 escalation at $0.07/1k; grok-4.3 reached 72.7% but cost $0.99/1k, lowering arena to 0.697; qwen3-235b-thinking was worst at 0.665. A quick harness caveat remains: LiveCodeBench was about 6% of prompts and scored 0 because code-execution grading was not wired, so the true ceiling for those runs may be 2-3 points higher.

The estimator should use a conservative blended public score:

| Public Signal | Weight | Purpose |
|---|---:|---|
| MMLU-Pro or equivalent hard knowledge QA | 25% | Breadth and difficult multiple-choice reasoning |
| GPQA or advanced science reasoning | 15% | Hard knowledge and multi-step reasoning |
| Math reasoning benchmark not overlapping calibration rows | 15% | Symbolic and quantitative reasoning |
| Code benchmark such as HumanEval-family public score | 10% | Code generation and execution-like tasks |
| Multilingual or translation benchmark | 10% | WMT-like and cross-lingual robustness |
| Long-context or reading comprehension benchmark | 10% | NarrativeQA/SQuAD-like context handling |
| Instruction-following or robustness benchmark | 10% | Perturbation stability and format compliance |
| Public latency/reliability reports | 5% | Timeout and overhead risk |

Then apply a discount calibrated only from observed non-tuning facts and public estimates:

```
expected_ra_accuracy = clamp(0.58, 0.82,
    0.62 * blended_public_accuracy
  + 0.26 * proxy_hard_accuracy
  + 0.12 * robustness_proxy_accuracy
  - 0.03 * reliability_penalty
)
```

The coefficients are not fit on RA. They are a pre-registered heuristic reflecting the measured gap: public benchmark scores can be much higher than RA accuracy because RA blends many datasets, scoring modes, and prompt perturbations. The clamp prevents a public benchmark headline from implying implausible RA accuracy. For qwen3-235b-a22b-2507, the public MMLU-Pro number around 84.8% and RA-listed cost around $0.071 prompt / $0.10 completion per 1k make it a high-priority candidate. It may clear roughly 77% RA accuracy by itself at a cost point where the arena formula maps to greater than 0.76, so it must be compared as a single-model design, not only as an escalation target.

Sanity checks:

| Check | Pass Criterion |
|---|---|
| Ordinal consistency | Candidate ranking is stable across at least 4 of 6 public benchmark groups |
| Proxy consistency | Model ranked top-2 by public blend is also top-2 on hard proxy, or discrepancy is explained by domain |
| Cost dominance | A more expensive model must project at least +2.0 accuracy points over a cheaper alternative for every 3x cost increase |
| Historical anchor | Estimator should place already observed qwen/deepseek/grok ordering within the measured 69-73% band, accounting for the LiveCodeBench caveat |
| Robustness anchor | Paraphrase/typo proxy accuracy drop must be less than 4 points for any model considered as a single-model submission |

Do not tune these weights after the RA one-shot. If the one-shot underperforms, revise the estimator only with new public data or new disjoint proxy diagnostics, with a documented version bump and no RA score fitting.

## 4. Model Pool Selection and Routing Policy

The arena formula rewards accuracy strongly but punishes unnecessary cost through log-cost. The current empirical results show that paying for grok-4.3 raised accuracy to 72.7% but cost erased the gain, yielding arena 0.697 versus 0.700 for deepseek-v3.2. A cascade helps only when the expensive calls buy correct answers on a tail that cheap models miss, and when agreement reliably identifies easy cases.

There are two regimes:

| Regime | Diagnostic Signature | Best Design |
|---|---|---|
| Diverse-error pool | Pairwise error correlations below 0.55; disagreement-tail escalation accuracy at least 8 points above cheap winner; union accuracy at least 4 points above best single model | Confidence-gated cascade |
| Correlated-error pool | Pairwise error correlations above 0.70; union accuracy less than 2 points above best single model; strong model only slightly better on disagreement tail | Single strong-cheap model |

For the current pool, the oracle ceiling of 78.7% and binary gate at 76.9% imply less than 2 points of routing-policy headroom. That means the current pool is near the correlated-error regime for policy improvements, even if the binary gate itself is effective. The next work must ask whether a new model increases union accuracy materially, not whether the gate can be made smarter.

Concrete diagnostic to run on the disjoint proxy:

1. Evaluate every candidate model on the same proxy items.
2. Convert each output to correct/incorrect using the proxy's ground truth validator.
3. Compute per-model accuracy, cost per 1k, and latency.
4. Compute pairwise phi correlation of error vectors for every model pair.
5. Compute union accuracy for each candidate pool: an item is union-correct if any pool member answers correctly.
6. Compute conditional strong-model accuracy on cheap disagreement items.
7. Simulate the exact binary agreement cascade and single-model baselines with the arena formula.

Decision thresholds:

| Decision | Required Evidence |
|---|---|
| Add model to cascade pool | Raises proxy union accuracy by at least +2.5 points and increases simulated cost by less than 2x |
| Replace escalation target | New target improves disagreement-tail accuracy by at least +4 points at no more than 4x target cost, or improves arena proxy by at least +0.010 |
| Prefer single model | Single model proxy arena is within 0.005 of cascade and has lower latency, or single projected RA accuracy is at least 76.5% at cost below $0.15/1k |
| Reject fancier router | Oracle minus binary-gate gap below 2.0 points on hard proxy |

`capability_map.py` remains allowed because it aggregates by self-owned axes, not RA's 44 categories, and is used only to pick escalation targets. Extend it to report error correlation, union accuracy, and conditional accuracy under disagreement.

## 5. Calibrating Escalation Without RA Signal

Allowed live signals are computed from the current query and candidate outputs, never from RA outcomes:

| Signal | Concrete Computation | Allowed Use |
|---|---|---|
| Cross-model agreement | Normalize final answers and compare exact/semantic equivalence | Primary binary gate |
| Self-consistency | Sample k=3 from one model, measure majority share or entropy | Ambiguity band only, because it adds latency/cost |
| Semantic distance | Embed or judge whether candidate answers are equivalent | Tie-breaking when surface forms differ |
| Structural confidence | Checks for required format, units, option letter, code block, numeric type | Penalize malformed cheap answers |
| Length and truncation | Detect incomplete output, refusal, timeout, or context overflow | Force escalation |

The isotonic logistic-regression head failed because its training distribution was too easy and too narrow. It saw 298 self-generated examples where cheap models rarely failed, especially in hard math strata that were not actually hard. The calibrated classifier learned near-constant behavior: do not escalate. On a clean 140-prompt run, that produced arena 0.740, worse than the binary gate at 0.769. This is not evidence that learned heads can never work; it is evidence that a learned head trained on the current computed-answer proxy is actively dangerous — it optimizes against a distribution that does not resemble RA's difficulty.

A learned head may be retried only if all of these preconditions are met:

| Precondition | Threshold |
|---|---:|
| Training proxy hard-stratum cheap accuracy | 60-80% |
| Held-out proxy seed count | At least 3 unseen seeds |
| Calibration examples | At least 2,000 labeled items |
| Feature families | Agreement, self-consistency, semantic distance, structural confidence, domain-free length/context features |
| Generalization check | Learned head beats binary gate by at least +1.0 accuracy point and +0.005 arena proxy on every held-out seed |
| Escalation sanity | Learned head escalation rate within 0.5x-1.5x of binary gate unless arena proxy improves by at least +0.010 |

Until those gates pass, keep the simple binary agreement gate. It has already beaten the trained head empirically, has fewer learned parameters, and carries less compliance surface (nothing is fit to a label distribution at all).

## 6. Offline Validation Gates Before the One-Shot

The sealed RA measurement is allowed only after offline evidence satisfies pre-registered numeric gates.

| Gate | Requirement |
|---|---|
| Provenance | `PROVENANCE.md` lists every calibration source, generator, seed, public benchmark, and exclusion |
| Template guard | `ci_template_guard.sh --strict` passes and its negative-control test fails when a banned template is deliberately inserted |
| Evaluator integrity | `assert_evaluator_unmodified` confirms byte identity for evaluator files against `origin/main` |
| Proxy difficulty | Cheap hard-stratum accuracy between 60% and 80%; strong model at least +5 points over cheap average |
| Proxy size | At least 2,400 backbone items and 1,000 held-out items across at least 5 seeds |
| Bootstrap interval | 95% CI lower bound for proxy arena projection at least 0.765 |
| Accuracy interval | 95% CI lower bound for projected RA accuracy at least 76.0% after public-score discount |
| Robustness | Perturbed proxy accuracy drop below 4 points; routing decision flip rate below 8% under paraphrase/typo perturbations |
| Cost | Projected charged final-model cost below $0.18/1k unless accuracy lower bound exceeds 78.0% |
| Latency | Routing overhead p95 below 2.5x single cheap call for cascade; single-model design records provider latency |
| Model-pool diagnostic | Chosen design satisfies the cascade-vs-single decision thresholds in Section 4 |
| Pre-registration | Exact router config, model list, thresholds, prompt normalizer, and source hash are committed before the RA touch |

Bootstrap protocol: sample proxy items with replacement 10,000 times, preserving family proportions. For each sample, compute accuracy, cost, arena score, robustness drop, and oracle gap. Report median and 95% interval. Family-stratified lower bounds must also be reported, and no family may sit below 65% accuracy unless it is less than 5% of the projected workload.

"Ready to submit" operationally means: all gates pass, the exact router commit is tagged, the one-shot ledger is initialized, and no code or configuration that affects routing changes between pre-registration and RA measurement.

## 7. Ordered Experimental Protocol: P8 Onward

P0-P7 established the clean-break router, proxy, capability map, compliance guard, and one-shot ledger (see `STATUS.md`, `PROVENANCE.md`, `sandbox/PROVENANCE.md`). Continue from P8; never restart the phase numbering or re-touch RA outside P16.

| Phase | Entry Condition | Work | Exit Gate |
|---|---|---|---|
| P8: Proxy hardening | Existing proxy and findings documented | Implement long-horizon state, constraint, synthetic graph, perturbation, and multilingual families (Section 2.2) | Cheap hard-stratum accuracy 60-80%; strong model gap at least +5 |
| P9: Public estimator freeze | Public benchmark sources selected | Build the pre-registered blended estimator and cost table (Section 3) | Estimator ranks observed qwen/deepseek/grok anchors plausibly and flags qwen3-235b-a22b-2507 as single-model candidate if supported |
| P10: Candidate pool sweep | P8 proxy frozen for this round | Evaluate single strong-cheap candidates and cascade pools on proxy only | At least one candidate has proxy arena lower bound at least 0.765 |
| P11: Error-correlation audit | Model outputs collected | Compute pairwise error correlation, union accuracy, oracle gap, disagreement-tail accuracy | Decide cascade vs single model using Section 4 thresholds |
| P12: Gate calibration | Design selected | Freeze binary gate or, only if qualified, learned head | Binary gate retained unless learned head beats it on every held-out seed |
| P13: Robustness and latency audit | Frozen candidate config | Run paraphrase/typo perturbation, timeout, malformed-output, and p95 latency tests | Robustness drop below 4 points; routing flip rate below 8%; p95 overhead below limit |
| P14: Compliance audit | Candidate otherwise passes | Run strict template guard, provenance review, evaluator byte check, source hash, and disjointness audit for any public-source slice | Zero banned literals; zero overlap; evaluator unmodified |
| P15: Pre-registration | All gates green | Commit and tag exact router config, model IDs, thresholds, prompts, normalizers, and measurement script hash | Hash-chained ledger records the frozen state |
| P16: Sealed RA one-shot | P15 tag exists and no dirty routing changes | Run `measure_ra_once.py` against real RA exactly once | Result is recorded in the ledger; no tuning follows |
| P17: Submit or retire | P16 complete | If score clears target and the compliance package is clean, submit. If not, retire this candidate and begin a new proxy-only cycle without using the RA score as a training target | PR includes provenance, one-shot ledger, and self-audit checklist |

The one-shot occurs only at P16. No RA prompt, label, score, category result, oracle result, or injected template may be used before P16 for development. After P16, the measured score may be reported as evaluation of the frozen router, but it may not drive threshold changes, model swaps, rationale edits that imply tuning, or category-specific policy changes.

## 8. Risks, Failure Modes, and PR-Rejection Guards

| Failure Mode | Where It Appears | Guard |
|---|---|---|
| RA prompt-template fingerprinting | Hardcoded strings like `Context: None`, `\boxed{X}`, RA math headers, NLI wrappers — the exact PR-158 failure | `ci_template_guard.sh --strict`; manual source review before PR |
| Public dataset overlap trap | Calibration rows copied from MMLU, GSM8K, MATH, WMT, etc. that RA sampled | Disjointness protocol with exact hashes and near-duplicate filtering (Section 2.4) |
| RA outcome leakage | Per-category table derived from RA accuracy, judge scores, oracle entries, or public sub_10 labels — the PR-140/PR-155 failure | Ban RA category routing; provenance review rejects any RA-derived rationale |
| Metrics tampering | Edited `metrics.py` or `compare_router_accuracy.py` | `assert_evaluator_unmodified` before any measurement |
| Easy-proxy overfitting | Learned head trained on computed math where cheap models are 99% accurate | Proxy difficulty gate and held-out seed gate |
| Cost-blind accuracy chasing | Expensive model raises accuracy but lowers arena, as grok-4.3 did at $0.99/1k | Arena formula simulation and cost-dominance thresholds |
| Pool ceiling mistaken for gate problem | Oracle only 78.7%, binary gate already 76.9% | Require union-accuracy and oracle-gap diagnostics before adding router complexity |
| Robustness leaderboard penalty | Router flips under paraphrase or typo perturbation | Perturbed proxy flip-rate and accuracy-drop gates |
| Latency leaderboard penalty | Cascade probes add overhead | p95 overhead gate; compare against single-model candidate |
| One-shot loop violation | Router is changed after seeing the RA result | Hash-chained ledger and pre-registration; post-P16 tuning forbidden |

The specific PR-140/PR-155/PR-158 lesson is that the maintainer reads label-derivation scripts, rationale strings, and commit messages forensically. A clean implementation is not enough if comments say "RA math" or commit messages explain a threshold using a RouterArena observation. All submitted rationale must cite only self-owned proxy evidence, public model benchmarks, public pricing, and live-signal mechanics.

### Self-Audit Checklist Before Opening a PR

| Check | Required Answer |
|---|---|
| Does any shipped router source contain banned RA literals or injected prompt wrappers? | No; strict guard output attached |
| Did any threshold, weight, model choice, or feature come from RA labels, RA scores, RA oracle entries, RA judge scores, or RA category outcomes? | No |
| Are public-source calibration rows provably disjoint from RA fixtures or excluded by split/version/year/license? | Yes, with hashes and protocol |
| Are RA's 44 categories absent from routing policy and calibration tables? | Yes |
| Are self-owned proxy domains still the nine existing axes or explicitly new self-owned families, not RA category names? | Yes |
| Is `capability_map.py` used only for self-owned axes and escalation target selection? | Yes |
| Does the document explain that the computed-answer proxy was too easy and not sufficient for learned heads? | Yes |
| If a learned head ships, did it beat the binary gate on every held-out seed with hard proxy difficulty in range? | Yes, or no learned head ships |
| Is the evaluator byte-identical to `origin/main`? | Yes |
| Is the exact router configuration pre-registered and hash-recorded before the RA one-shot? | Yes |
| Was the RA set touched exactly once through `measure_ra_once.py` without override? | Yes |
| Do commit messages and rationale strings avoid RA-template or RA-outcome explanations? | Yes |

## 9. Default Recommendation

Proceed with two competing designs through P8-P15: the existing binary agreement cascade with an enriched model pool, and a single strong-cheap model baseline centered on qwen3-235b-a22b-2507. Do not retry the learned confidence head until the hardened proxy demonstrates real difficulty and held-out generalization. The cascade should win only if a new pool member raises union accuracy by more than the current sub-2-point policy headroom. If error correlations remain high and the single qwen model projects at or above 76.5% accuracy below $0.15/1k, the single-model design is the cleaner candidate: lower latency, fewer moving parts, and less compliance surface.

The sealed RA one-shot is not a development tool. It is the final measurement of a pre-registered router whose accuracy case was built entirely from disjoint proxy evidence, public model capability estimates, public costs, and live inference signals.
