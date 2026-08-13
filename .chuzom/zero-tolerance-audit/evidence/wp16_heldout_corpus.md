# WP-16 item 3 — the held-out corpus

Date: 2026-08-13. Owner authorised the API spend.

Plan scope item: *"Benchmark on a held-out corpus — the current 33-prompt set was
tuned against by fix #220."*

---

## Why a held-out set was required

The tuned corpus is `moderate.jsonl` (17) + `hard.jsonl` (16) = **33 prompts**.
Fix **#220** added precision-tier routing *specifically* to fix `mod-07` and
`mod-12` — short objective prompts where cheap-local-first returned
confident-but-wrong terse answers. #220's own note claims `_needs_precise_answer`
fires on **general** computation/exactness/code-output cues, "not benchmark
strings".

**A benchmark that was tuned against cannot also be the evidence that the tuning
generalises.** That claim is exactly what a held-out set exists to test.

## The corpus

`bench/corpus/heldout.jsonl` — **24 new prompts, 18 objective + 6 subjective**,
same schema and same regimes as the tuned set, deliberately stressing the short
exact-answer case with different wording.

**Every one of the 18 objective answers was verified computationally** before the
run: 14 by executing the snippet and comparing stdout, 4 by evaluating the
arithmetic. A corpus with a wrong expected answer grades the router against the
author's mistake and measures nothing.

`bench/__main__.py` gains `--corpus NAME` so a single named file can be run and
reported separately, which is the acceptance criterion.

## Results (24 prompts × 4 routers, `--no-cache`, real API calls)

| rank | router | quality (1–5) | ≥4 | cost/prompt | tokens | latency | success |
|---|---|---|---|---|---|---|---|
| 1 | static-chain | **4.50** | 75% | $0.042m | 248 | 12.2s | 24/24 |
| 2 | always-premium | **4.50** | 75% | $0.816m | 107 | 1.3s | 24/24 |
| 3 | **chuzom** | **4.17** | 67% | $0.032m | 2004 | 21.9s | 24/24 |
| 4 | always-cheap | 2.42 | 33% | $0.000m | 161 | 12.3s | **9/24** |

### The held-out delta, reported separately as required

**Chuzom vs always-premium: −0.33** (4.17 − 4.50).

Tuned corpus, four strict-full-metering runs: **−0.18 / −0.21 / −0.21 / +0.00**.

**Held-out is worse than every tuned run.** It remains inside the 0.5
non-inferiority margin, so Gate 16's bar still holds — but the gap between the
tuned figure and the held-out figure is the quantity the tuned corpus could never
have shown, and it is in the direction overfitting predicts.

### Chuzom is not the champion here

`static-chain` scores **4.50 to chuzom's 4.17** at $0.042m vs $0.032m — both ~95%
below premium. On this corpus chuzom buys a 0.33-point quality reduction for a
$0.010m/prompt saving. Whether that trade is right is a product judgement; what
matters for the audit is that **the tuned corpus presents chuzom as the
champion and the held-out corpus does not.**

**A reporting hazard, found while reading the output:** the report's §3 headline
reads *"Quality delta: +0.00"* — but §3 describes the **champion**, which here is
`static-chain`, not chuzom. A reader taking that line as chuzom's delta would be
off by 0.33. The section is internally consistent; it is the reader's reasonable
assumption that breaks.

## Did #220's precision-tier fix generalise?

**Partially, and the failures are exactly the regime it was built for.**

Chuzom's only two objective failures — both scored 1 — went to local models:

| prompt | code | routed to | score |
|---|---|---|---|
| `held-04` | `print(len({1, 2, 2, 3, 3, 3}))` | `ollama/qwen2.5-coder:7b` | **1** |
| `held-18` | `print(len([x for x in range(20) if x % 3 == 0]))` | `ollama/hermes3:8b` | **1** |

Both are short, objective, exact-answer `print(len(...))` prompts — the `mod-07` /
`mod-12` shape verbatim. The other 16 objective prompts scored 5.

**Measured:** the precision-tier decision logged **21 firings**, but only **2 of 18**
objective prompts recorded `gpt-4o-mini` as their final model. One traced prompt
(`6d2e62b6`) shows the full path working — fronted, called, `routing_decision
model=openai/gpt-4o-mini` — with `quality_recorded score=0.30`.

**WHY the other firings did not end on `gpt-4o-mini` is NOT ESTABLISHED.**
Candidate explanations — a downstream quality gate discarding the mini answer, an
availability/budget fall-through, or my reading of the `model_chosen` field —
have **not** been instrumented. Recorded as open rather than closed with the
best-sounding story. What *is* established is the outcome: two exact-answer
prompts reached local models and got wrong answers.

## A separate finding: a fully-failed run renders as a complete report

An earlier invocation was truncated by piping to `head`, which killed stdout and
made **every one of the 24 prompts fail** with `BrokenPipeError`.

`bench/results/20260813-110016.md` nonetheless contains a full scorecard, a Pareto
frontier, a savings section reading *"Cost savings vs baseline: 0%"*, and
**"Quality delta: +0.00"**. The only hint is `Success 0/24` in one column.

**A run in which nothing succeeded produces a formatted result with a quality
score and a savings figure**, rather than refusing to report. That is this
audit's signature defect — a failure that renders as data — in the benchmark
harness itself, and it is the same shape as RED2-02 and AUD-06.

`bench/results/` is gitignored, so the bogus file ships nowhere; the defect is
that the reporter emits it at all. Not fixed here: the reporter is not in WP-16's
scope and changing it mid-measurement would violate the rule against altering an
instrument while reading it. Recorded for the re-audit.

Note also `always-cheap`: **9/24 success**, yet its quality average (2.42) is
reported over the successful subset with no marker on the headline figure. Milder
instance of the same pattern.
