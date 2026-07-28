# RouterArena → 0.75+ the legitimate way: a clean-break plan

**Status:** proposal · **Author:** drafted with Claude (Opus 4.8) · **Target:** Acc‑Cost Arena score > 0.75 with **zero** use of RouterArena data or the academic benchmarks it is built from.

---

## 0. The one-sentence thesis

Stop trying to *recognise the benchmark*. Build a router that decides **"is my cheap answer trustworthy, or must I escalate?"** using signals computed **live, per query, from the models themselves** — a mechanism that needs no benchmark labels at all — and calibrate its single threshold on **self‑generated** data. This is how the current top-of-leaderboard clean entries (vLLM‑SR, Sqwish, Nadir #159 at 0.7517) actually score, and it is the opposite of Chuzom's current template-matching lineage.

---

## 1. Why every prior Chuzom submission failed (root cause)

The entire Chuzom RouterArena lineage — legacy `chuzom_router.py` v0.5.2 **and** PR #158's "Gate 2" — routes by recognising **RouterArena's injected harness templates**. Proven, not suspected:

| Signal used | Where it comes from | Verdict |
|---|---|---|
| `\boxed{X}` MCQ format | "LaTeX notation injected by RouterArena's dataset builder" (their own comment) | RA-derived |
| `Context: None` + LaTeX → qwen3-235b | "exclusive to competition-level math datasets (AIME, MATH)" | RA-derived |
| `Please solve the following mathematical problem` | RA harness header (appears in 280/8400 real RA prompts, 3.3%) | RA-derived |
| `Please read the following question and provide the correct answer.` | RA harness header (689/8400, 8.2%) | RA-derived |
| `Natural Language Inference…Premise…Hypothesis` | RA task wrapper (66/8400) | RA-derived |

**Grep proof:** the exact regex strings in PR #158 appear **verbatim** in RA's own prompts (`Context: None` in 72.6% of them), while Chuzom's *own* `build_public_centroids.py` wraps the same underlying datasets with **different** phrasings. The only way the router's strings could match RA is by reading RA's prompts. That is "fitting a router component on RouterArena data" — the exact README prohibition, and the same class as the PR #155 rejection.

**Consequence for this plan:** any signal keyed to a *fixed prompt wrapper* is banned. We route on **intrinsic content** and **live model behaviour** only.

---

## 2. What "legitimate" means here — Firewall v2 (split-level, not family-level)

**The line that matters is the train/test split, not the dataset name.** *Test contamination* is training/tuning on the exact prompts, answers, or scores RA evaluates on. *Domain-representative training* is fitting a classifier on academic-QA-**style** data so it generalises — ordinary supervised ML, and exactly how the legitimate #1 (vLLM-SR, fine-tuned on MMLU-Pro) works. Firewall **v1** banned both by banning the whole dataset family; **v2** bans only the former, and enforces it with a **hash audit** rather than a dataset-name blocklist. v2 loosens *nothing* that ever got a submission rejected.

**Hard-banned — never an input to any router parameter, threshold, pattern, centroid, or classifier weight:**
- RA's own **eval prompts, answers, or scores** — the 8,400 full + 420 robustness set, any split, in any form.
- **RouterBench** eval prompts / answers / scores.
- Any **per-query or per-dataset routing table** derived from RA outcomes (the #155 `apply_v3/v4/v5` failure).
- **The returned `/evaluate` score** as a tuning signal — one cold submission, never iterate against the number (#155's fatal move).
- **RA harness template literals** as routing signals — `\boxed`, `Context: None`, `Please solve the following…`, `Premise…Hypothesis`, etc. This is benchmark *recognition*, categorically different from domain training, and stays banned regardless of source.

**Allowed as training / calibration input:**
1. **Self-generated synthetic prompts** — you author / LLM-generate them; you own them. Regenerable calibration corpus.
2. **Academic-benchmark train / validation splits** (MMLU, ARC, GSM8K, MATH, SQuAD, HumanEval/MBPP, …) — **permitted iff** the SHA-256 prompt-hash audit (§5) proves **0 overlap** with RA's eval set. *The audit, not a split theory, is the guarantee:* if no training prompt hash-matches an RA eval prompt, there is no leakage regardless of which split RA sampled. This is the same data-legitimacy standard SR uses; the accepted-#1 precedent is the argument to make in the PR.
3. **Organic chat logs** (WildChat / LMSYS-Chat-1M / ShareGPT) — real user turns, distributionally unlike RA. Usable for both distribution-check *and* classifier labels.
4. **Published model metadata** — provider model cards, `artificialanalysis.ai` quality/price snapshots (already in `model_registry.py`), pricing (`model_cost.json`). Public knowledge *about models*, not RA data.
5. **Live per-query model behaviour** — agreement, self-consistency, logprobs, verbalized confidence. Needs **no** training data. This is the escalation engine.

**The v1→v2 change in one line:** source #2 flips from *banned* to *allowed-with-hash-audit*; every entry in the hard-banned list is unchanged from v1. If a component's value cannot be traced to sources 1–5 **and** clear the §5 hash audit, it does not ship.

**Why loosen at all:** v1 forces the classifier onto self-authored synthetic data, which under-covers the real task distribution and caps achievable accuracy — plausibly *below* the 0.75 target (the pure-synthetic ceiling is ~0.71–0.73; SR clears 0.77 partly *because* it trained on domain data). v1 also is, paradoxically, harder to prove clean (a reviewer must trust your generator wasn't seeded from benchmarks), whereas "MMLU-train + hash-disjointness proof" is mechanically verifiable. v2 buys SR-class classifier accuracy while keeping the audit as the load-bearing, reviewer-checkable guarantee.

---

## 3. The architecture — a label-free confidence cascade

```
                 ┌─────────────────────────────────────────────┐
   query ───────▶│ Tier 0: intrinsic structural pre-classifier │  (generic signals only)
                 │  code? math? translation? long-context?     │
                 └───────────────┬─────────────────────────────┘
                                 │ picks which cheap model to probe first
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │ Tier 1: cheap probe(s)                       │  qwen3-235b (cheapest),
                 │  run 1–2 cheapest models, get answer+signals │  deepseek-v4-flash
                 └───────────────┬─────────────────────────────┘
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │ Tier 2: LABEL-FREE confidence gate          │  ← the core, zero training data
                 │  • agreement between probes                  │
                 │  • self-consistency (k samples, temp>0)      │
                 │  • logprob / verbalized confidence           │
                 │  → scalar confidence  vs  threshold τ        │
                 └───────┬──────────────────────────┬──────────┘
              confident  │                          │  uncertain
                         ▼                          ▼
              ship cheapest answer      ┌──────────────────────────┐
                                        │ Tier 3: escalate         │  strong model for the
                                        │  strong reasoning model  │  hard ~10–20% tail
                                        └──────────────────────────┘
```

### Tier 0 — intrinsic structural pre-classifier (generic, first-principles)
Detects properties **any** organic prompt of that kind has, using signals that show up in real code/math/translation prompts — **not** RA wrappers:
- **Code:** fenced blocks, language keywords (`def/class/import`, `#include`), "write a function/program". 
- **Math:** LaTeX macros, digit/operator density.
- **Translation:** explicit "translate … to <lang>" + a **library** language-pair detector (`langdetect`/`fasttext-lid`), not a hardcoded RA phrase.
- **Long-context:** raw token count.

Output is a **domain/complexity estimate → which cheap model to probe first + an escalation prior**, never a final model lock. Validated on the self-generated corpus (§4). A CI guard (§5) fails the build if any RA-template literal string appears in this file.

### Tier 1 — cheap probe(s)
Run the 1–2 cheapest pool models. Per Chuzom's own cost analysis `qwen3-235b-a22b-2507` is *cheapest* at typical RA prompt lengths, then `deepseek-v4-flash`. Capture answer text + logprobs where the provider exposes them.

### Tier 2 — the label-free confidence gate (heart of the system)
Combine signals that need **no** ground truth:
- **Cross-probe agreement:** extract each probe's final answer with a *generic* extractor (last line / boxed / "answer is X" — format-driven, not RA-specific); if two cheap models agree, correctness is empirically high → ship cheapest.
- **Self-consistency** (Wang et al., a published general method): sample one cheap model *k=2–3×* at temp>0; stable answer ⇒ confident.
- **Confidence readout:** provider logprobs, or a "0–100 how sure are you" verbalized-confidence probe.
- Blend → scalar `conf ∈ [0,1]`; if `conf ≥ τ` ship cheap, else escalate. **τ is the only tunable**, calibrated in §4.

### Tier 3 — escalation
Route the uncertain tail to a genuinely strong model. The current pool lacks one at meaningful share (qwen3-next-80b is 0.3%). Add **one** strong reasoning model to `model_cost.json` + `universal_model_names.py` (allowed — it's a pool declaration, e.g. `grok-4-fast-reasoning` / an o-series / `claude-sonnet`). Only ~10–20% of traffic reaches here → cost stays low.

**Why this clears 0.75:** the score is accuracy-weighted (`S = 1.1·A·C_i/(0.1·A+C_i)`, β=0.1). chuzom-v3 stalled at **73.97% accuracy** because cheap models silently failed the hard tail. Escalation converts those misses to correct answers — pushing A toward 76–78% — while the confidence gate keeps ~80% of traffic on the cheapest model, so C_i stays high. Nadir proves the mechanism: **0.7517 with a weaker 3-model pool** using agreement+escalate alone. Chuzom has more cheap models *and* adds self-consistency.

---

## 4. Calibrating τ without any RA data

τ (and any blend weights in Tier 2) are set on the **self-generated corpus**, then **frozen** before a single RA prompt is routed.

1. **Generate a diverse synthetic prompt set** (~1–2k prompts) spanning code / math / reasoning / short-fact / long-context / translation, via an LLM you drive. Store it (`data/synthetic_calibration.jsonl`) so a reviewer can regenerate it. **No benchmark text copied in.**
2. **Model-vs-model pseudo-reference:** run all pool models; treat "strong model's answer" (or all-model majority) as a *pseudo-gold*. This uses **no** benchmark labels — purely relative model agreement.
3. **Fit the confidence→correctness curve** against that pseudo-reference; pick τ at the knee that maximises the *arena-score proxy* (using the real formula from `llm_evaluation/run.py`, public pricing for cost).
4. **Cost-target cross-check:** confirm the resulting escalation rate lands cost in the ~$0.05–0.15/1K band (where β=0.1 rewards you).
5. **Freeze** τ and weights. Optionally re-confirm the *distribution* of `conf` on organic chat data (source 2) — distribution only, no re-fit.

Because calibration data is self-generated, RA overlap is ~0 by construction; the §5 audit merely confirms it.

---

## 5. Compliance protocol (make rejection impossible)

1. **Provenance manifest** (`ROUTERARENA_PROVENANCE.md` in the submission): every data source enumerated, each asserted ∈ sources 1–4, each RA-source benchmark explicitly listed as **excluded**.
2. **SHA-256 contamination audit** (Nadir #159's accepted pattern): normalize (NFC→strip→collapse-ws→casefold) and hash **every prompt that touches a router parameter** — self-generated calibration prompts **and** any academic-benchmark train/validation prompt admitted under §2.2 — then verify **0 overlap** with RA's 8,400 full + 420 robustness prompts. This audit is what upgrades §2.2 benchmark data from "banned" to "allowed": it is the load-bearing guarantee, run in CI, and its report (`ROUTERARENA_CONTAMINATION_AUDIT.json`, counts + zero-overlap assertion) ships in the PR. *Reading RA prompt hashes solely to prove non-use is the accepted transparency mechanism — it is an audit, not training.* For any purely self-generated component, also note in the PR that overlap is 0 by construction.
3. **CI template-guard** (extend `ci_quarantine_guard.sh` → `--strict` in CI): grep the router source for the banned RA-template literals — `Context: None`, `\boxed`, `Please solve the following mathematical problem`, `Please read the following`, `Premise.*Hypothesis`, `1` for correct/`0` for incorrect`, `"moves":`, `This is the clue:` — **fail the build if any appear.** This structurally prevents regression to the template DNA.
4. **Shared-evaluator invariance:** `llm_evaluation/metrics.py`, `compare_router_accuracy.py`, `model_inference.py` byte-identical to `origin/main` (already true in #158; keep it true).
5. **Reproducibility bundle:** ship the synthetic-prompt generator + τ-calibration script so a reviewer can rebuild every parameter from scratch with **no** RA access.
6. **Model-quality priors** come from `artificialanalysis.ai` / provider cards only — **purge** the `cost_aggressive.yaml` / `model_registry.py` comments that cite "RouterArena submission data" / "quality_gap derivation," and re-derive any specialist ordering from public sources.

---

## 6. Phased execution

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **P0 — Firewall** | Provenance manifest, CI template-guard (strict), quarantine the legacy template router + #158 Gate-2 out of the submission path | CI fails on any RA-template literal; guard green on the new router |
| **P1 — Tier 0** | Generic structural pre-classifier + self-generated validation set | classifier decisions reproduce on regenerated synthetic data; zero RA strings |
| **P2 — Tier 2 gate** | cheap-probe + agreement + self-consistency + generic answer-extractor → scalar confidence | confidence separates pseudo-correct vs pseudo-wrong on synthetic set (AUC ≥ ~0.65) |
| **P3 — Tier 3** | add 1 strong model to pool; escalation wiring | escalated tail measurably lifts pseudo-accuracy on synthetic hard subset |
| **P4 — Calibrate** | fit + freeze τ on synthetic corpus to a cost target | frozen τ, documented; arena-proxy on synthetic ≥ target |
| **P5 — Cold dry-run** | run the frozen router on a **held-out self-generated** set (generalization proxy) | projected A ≥ 76%, cost ≤ ~$0.12/1K → proxy S > 0.75 |
| **P6 — Submit** | generate RA predictions in **one cold pass** (no score-peeking/iterating), run contamination audit, open PR, `/evaluate` | audit clean; CI green; `/evaluate` posted; ping maintainer |

**Hard rule for P6:** do **not** iterate the router against the returned RA score. Tuning after seeing `/evaluate` results *is* fitting on RA data (that's what sank #155's `apply_v3/v4/v5`). One cold shot; if it underperforms, improve the *mechanism* on synthetic data and resubmit — never chase the RA number.

---

## 7. Risk register

| Risk | Mitigation |
|---|---|
| **Probe cost** — RA charges only the *final* pick, but production pays for probes | Disclose the real probe cost in the PR (Nadir did; it was accepted). Honest and precedented. |
| **Generic answer-extractor accidentally RA-specific** | Build it for generic formats (last-line, boxed, "answer is X"); test on synthetic data only; CI-guard against RA literals. |
| **Tier 0 too weak to pick the right cheap probe** | The confidence gate is the safety net — a mis-probed easy query still escalates or self-consistency-corrects. Tier 0 only sets priors. |
| **Escalation rate too high → cost blows up** | τ directly controls escalation share; cost-target cross-check in P4 bounds it. |
| **Self-consistency latency/cost** | Reserve k-sampling for the *ambiguous* band only (single `conf` estimate first; sample more only near τ). |
| **"Chat data is a similar dataset" objection** | It's optional and used for *distribution check only*, never fitting. Plan is fully functional on self-generated data alone — drop chat data if you want zero ambiguity. |

---

## 8. Will it actually hit >0.75? Honest expectation

- **Existence proof:** Nadir #159 = **0.7517**, weaker pool, same core mechanism (agreement-gate + escalate), clean training. vLLM‑SR **75.30** / Sqwish **75.27** sit just above.
- **Chuzom's edge:** more cheap models to probe, plus self-consistency as a second label-free signal, plus a genuinely strong escalation model.
- **The lever is accuracy, not cost** (β=0.1). Moving A from 74% → ~77% at ≤ $0.12/1K crosses 0.75 comfortably per the formula.
- **Realistic range:** 0.75–0.77 is attainable *if* the escalation model is strong and τ is well-placed. Below-0.75 outcomes come from (a) too-weak escalation model, or (b) probe answers too noisy to gate on — both fixable on synthetic data without ever touching RA.

**Bottom line:** yes, >0.75 is achievable legitimately. The winning move is a mechanism change (confidence-gated cascade), not more clever pattern-matching — and it is provably clean because its one tunable is fit on data you generate yourself.
