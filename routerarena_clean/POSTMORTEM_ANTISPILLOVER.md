# Post-mortem + anti-spillover plan
### The vLLM-semantic-router experiment, and keeping RouterArena eval data out of the process

**Status:** closeout · **Date:** 2026-07-12 · **Measured outcome:** cascade full-8400 = **0.693** (below the 0.7061 single-model baseline).

---

## 0. TL;DR

- The semantic-router technique never moved the RouterArena score because we (a) optimized the wrong axis — classification, not answer-per-cost; (b) couldn't legally use its load-bearing ingredient — benchmark-data fine-tuning; and (c) applied its reasoning-gate idea where its enabling conditions don't exist. RA's ceiling is **capability/economics, not routing**.
- We **did** touch RA data this session — **legitimately, to *evaluate* a frozen router**, not to tune one. But the *outputs* of that evaluation (per-dataset accuracies, and RA gold now on disk) are a live contamination vector for the next design step. This plan **quarantines** them and sets rules so RA signal can never leak into a router parameter — the exact failure that sank **PR #140** and **PR #155**.

---

## 1. Why it didn't work (post-mortem, condensed)

1. **Copied the axis the score doesn't reward.** semantic-router's classifier labels a prompt's domain. RA scores whether the chosen model *answers correctly, cheaply*. A better label doesn't change the answer — and the single-model sweep already showed deepseek-v3.2 is the best model across the board. → the classifier is a **product** win, RA-neutral.
2. **Couldn't copy the ingredient that mattered.** semantic-router's accuracy comes from fine-tuning on **MMLU-Pro** (benchmark-family data). Our firewall forbids that. We reproduced the *architecture*, not the *data recipe* — and the data was the point. Query-surface transfer to RA measured **0.024**.
3. **Reasoning-gate idea, wrong problem.** SR's +10pp toggles reasoning on *one capable model*. Our cascade escalates from a *weak* model to a *different strong* one — which pays off only if you can spot the weak model's errors (you can't: two cheap probes fail *together* on the hard tail, η≈0.18) and the strong model fixes them affordably (it can't: $4.5–6.6/1k).
4. **RA's hard tail is capability, not routing.** ChessInstruct, LiveCodeBench, translation, AIME, obscure geography all scored ~0.0 — questions **no affordable model answers**. Routing rearranges *which* model answers; it can't create capability that isn't in the pool.

**Result:** 0.693 < 0.706. The gate was net-*negative* vs. "route everything to the best single model." Simplest beat cleverest.

---

## 2. What we did with RA data this session — and why it was evaluation, not tuning

- Downloaded the RA dataset (`sub_10` + `full` gold) from HF `RouteWorks/RouterArena`; fetched the **pinned, unmodified** `metrics.py` (sha `e7f9e556…`, verified) + its local modules; ran the **frozen** cascade (τ calibrated on self-generated data and frozen *before* any RA touch) and graded with RA's official metrics.
- **This is legitimate evaluation:** the router had **zero** RA-derived parameters; we measured it once. It is *not* the #155 pattern — no RA-accuracy-derived labels, no per-query table, evaluator byte-identical to upstream (sha-verified).
- **The line we did not cross:** we did not iterate the router against the returned number.

> The measurement was clean. The **forward** risk is the outputs — §3.

---

## 3. The spillover risk NOW — mapped to PR #140 / #155

The dangerous artifact is the **per-dataset accuracy breakdown** we now hold (e.g. `ChessInstruct 0.13, GSM8K 0.96, LiveCodeBench 0.0, AIME 0.36`). Acting on it re-creates the exact violations that got prior submissions rejected:

| PR-era failure | Current-situation analogue | Rule |
|---|---|---|
| **#140** template fingerprinting (`\boxed`, `Context: None` as routing signals) | Special-casing datasets we now know score low = the same fingerprinting, industrialized | **Never** key routing on a dataset identity or RA-template string |
| **#140** model substitution (gemini-2.0→2.5, kept cheap price) | — | Never swap a pool model's identity while keeping another's cost/label |
| **#155** RA-accuracy-derived classifier labels | The per-dataset breakdown **is** RA-accuracy data; using it to pick specialists/thresholds = #155 | RA eval outputs may **never** inform a router parameter |
| **#155** `apply_v3/v4/v5` per-query routing table from RA oracle | Any per-`gi` / per-dataset rule built from this eval = the same table | No per-query / per-dataset override sourced from RA outcomes |
| **#155** modified shared `metrics.py` | We fetched + **sha-verified the unmodified** scorer | Keep `metrics.py` byte-identical to upstream; CI-check the sha |

---

## 4. The anti-spillover firewall (concrete actions)

1. **Quarantine the RA eval artifacts.** The per-dataset result files carry RA-derived accuracies and must be treated as **read-only evidence**, never as input:
   - `routerarena_clean/sandbox/chuzom-cascade_sub10_result.json`
   - `routerarena_clean/sandbox/chuzom-cascade-full_sub10_result.json`
   Keep them **out of PR #130** and out of any branch that feeds the production router. Do not `import`/read them from any router or parameter-building code. Prefer moving them under a clearly-marked `routerarena_clean/quarantine/` dir (git-ignored) or deleting once the numbers are recorded in `STATUS.md`.
2. **RA gold is ephemeral — let it die.** The downloaded parquet/label files live in session scratchpads and vanish on cleanup. Do **not** copy them into the repo. If any did, delete them.
3. **No design against per-dataset results.** The per-dataset table informs *understanding* (why 0.75 is unreachable), never *mechanism*. Any future router change must be justifiable **without** reference to which RA datasets scored low.
4. **All future RA measurement goes through the seal.** Use `sandbox/measure_ra_once.py` (auditable ledger, `assert_evaluator_unmodified`); one cold pass; never re-run to chase a number.
5. **Firewall v2 governs what *may* inform parameters** (see `ROUTERARENA_CLEAN_075_PLAN.md` §2): self-generated synthetic, hash-audited benchmark *train* splits, public model metadata, live per-query behavior. **RA eval outputs are not on that list.**
6. **CI guards:**
   - `ci_template_guard.sh --strict` (already extended to the new source files) — no RA-template literal in any router/param code.
   - Add a guard: no file under `src/chuzom/` or the submission router imports/reads the quarantine path or any `*_sub10_result.json`.
   - Pin + check `metrics.py` sha256 stays `e7f9e556…`.
7. **Ledger the touch.** Record this session's evaluation (frozen router, sha-verified scorer, no iteration) so the "measured once, cleanly" claim is auditable.

---

## 5. Forward direction (legitimate)

- **Decouple the classifier.** It ships as a production improvement (**PR #130**) with **no RA claim**. Its training corpus stays self-generated / hash-audited — never the eval outputs.
- **The only levers that move RA's ceiling** are (a) a **stronger-but-affordable pool model** (a pool declaration — allowed), or (b) a **higher-η, response-based confidence signal** (an open research problem — coherence transferred at η≈0.18; beating that is the real frontier). Both are fit on non-RA data, never on this session's results.
- **Default recommendation:** keep the shipped single-model solo (**0.7061**) as the RA entry; pursue the classifier for the product; treat **0.75 as out of reach for this pool** until the capability/economics gap changes.

---

## 6. Action checklist

- [ ] Move `*_sub10_result.json` to `routerarena_clean/quarantine/` (git-ignored) or delete after recording numbers in `STATUS.md`.
- [ ] Confirm no RA gold/parquet/label files were copied into the repo; delete any that were.
- [ ] Keep PR #130 **RA-claim-free** and free of any RA eval artifact.
- [ ] Add CI guard: no `src/chuzom/**` or submission router reads the quarantine path / `*_sub10_result.json`.
- [ ] Keep `ci_template_guard.sh --strict` green; keep `metrics.py` sha pinned.
- [ ] Route future RA measurement through `measure_ra_once.py` only (one cold pass).
- [ ] **Rotate the two OpenRouter keys** pasted into the session transcript.
