# Chuzom Correctness Reset — 09. Control-Group Benchmark (Phase 8 / #5)

Status + plan for the verdict blocker behind Gates **15** (positive net verified savings),
**16** (quality non-inferiority), **17** (no unclassified spend). Written after tracing the
existing `bench/` harness.

## What already exists

`bench/` is a real head-to-head harness: a corpus (`corpus/{easy,moderate,hard}.jsonl`), a
`Router` protocol, contender routers (`ChuzomRouter`, `always-cheap`, `always-premium`,
`static-chain`), deterministic + LLM-judge grading, a cost/quality **Pareto frontier**, caching,
and a reporter. It is NOT nothing — the scaffolding for an A/B is here.

## Why Gate 15 was still honestly FAIL — the precise gaps

1. **No Chuzom-OFF control arm.** The reference routers were `always-cheap` (Ollama),
   `always-premium` (**GPT-4o**), `static-chain`. None is the North-Star baseline — "the **host**
   (Claude) answers everything, no routing." Savings is defined *against the host*, so without a
   host arm there was nothing honest to subtract from.
2. **`ChuzomRouter` is a v0.0.1 stub.** It runs a hardcoded 3-model chain, not
   `chuzom.router` — so a run measured a toy, not the product. (Its own docstring says v0.0.2
   will wire `chuzom.router.Router.choose_chain` end-to-end.)
3. **Cost was a static reprice, not verified net.** `_price()` multiplies tokens by a hardcoded
   table; nothing netted routing/classification overhead → "repricing counterfactual," not the
   ledger's verified realized savings.
4. **No unclassified-spend guard (Gate 17).** An unknown-priced paid model silently costs `$0`.

## What this increment delivers (parallel-safe, no API spend)

- **The control arm** (`bench/routers.py`): `claude_host_router()` /
  `control_group_routers()` — `always-claude-host`, the host frontier priced at the **canonical**
  host rate (5/25 per 1M, matching `cost._HOST_INPUT/OUTPUT_PER_M`). This is the missing baseline.
- **The savings verdict** (`bench/savings.py`): `evaluate_savings(rows)` → `SavingsVerdict` with
  the three gate judgements computed from **measured** tokens over the **paired** corpus:
  - Gate 15: `net_savings = Σ host − Σ chuzom − Σ routing_overhead` (overhead read from row
    notes; never fabricated), `> 0` to pass.
  - Gate 16: mean judge score delta `≥ −margin`.
  - Gate 17: any non-free model reported at `$0` = unclassified → fail; `ollama/…` $0 is
    classified. Also refuses an **unpaired** A/B (different prompt sets) — that's not a valid
    comparison.
- **Tests** (`tests/test_bench_savings.py`, 10): pass-all, overhead netting, **negative savings
  fails Gate 15 honestly**, quality-regression fails Gate 16, margin boundary, paid-$0 vs
  local-$0 for Gate 17, unpaired/missing-arm errors.

## What remains — and the honest boundary

**Gate 15 PASS is EMPIRICAL, not a code deliverable.** No amount of harness code makes it green;
it requires *running* the A/B with real spend and getting a positive, quality-non-inferior
result — an outcome that is genuinely uncertain (that is the point of a control-group test). The
remaining steps:

1. ~~**Wire `ChuzomRouter` to the real `chuzom.router`**~~ ✅ **DONE.** The v0.0.1 stub is
   retired; `ChuzomRouter` now `classify()`s the prompt and dispatches through
   `chuzom.router.route_and_call(..., suppress_ledger=True)` — the real signal → chain →
   dispatch → fallback path — so a run measures the product. Mapping + error path tested in
   `tests/test_bench_chuzom_router.py` (real router mocked; CI makes no API calls). Known
   limitation: `classify()` doesn't return the classifier's own cost, so the LLM-classified
   tail's routing overhead is not yet captured in `routing_overhead_usd` (heuristic path is a
   genuine $0). Threading that cost through is a small follow-up — until then overhead is honest
   $0, never fabricated.
2. **Run the A/B** (`control_group_routers()` over the full corpus) with real spend → feed the
   rows to `evaluate_savings` → record the `SavingsVerdict` under `bench/results/`. **Needs
   provider access + explicit authorization** (real spend; uncertain outcome).
3. **Larger corpus** if the smoke's 10 prompts are too thin to be non-directional.
4. Only when a recorded run shows `all_gates_pass` may Gates 15/16/17 flip and a savings
   magnitude be marked `supported` in the claim-evidence registry — feeding Phase 9 (#6).

Until then the verdict stays **RELEASE NOT QUALIFIED**, honestly: the measurement apparatus is
now correct and reproducible, but the measurement itself has not been run to a passing result.

## End-to-end validation (2026-07-27, $0)

The harness was executed end-to-end for the first time against **local Ollama only** (no API
keys present in the environment), to validate the pipeline without spend:
`python -m bench --easy-only --routers chuzom,always-cheap --no-cache`.

- **It runs.** The real `ChuzomRouter` (→ `chuzom.router.route_and_call` → Ollama dispatch,
  `suppress_ledger=True`) produced 40 valid `RunRow`s across both arms with no crashes;
  deterministic grading, the scorecard, and `bench/results/*.{json,md}` all worked.
- **`evaluate_savings` works on real rows** (not just the synthetic test rows): fed the produced
  results (with `always-cheap` as a stand-in control, since there is no keyed Claude arm), it
  returned a well-formed `SavingsVerdict` — `net=$0.00` (both arms free), `quality_delta=+0.60`,
  `unclassified_events=[]`.
- **The verdict is honest under a real run:** with both arms free there is nothing to save, so
  **Gate 15 correctly FAILS** (`net > 0` is False); Ollama `$0` is correctly classified (Gate 17
  passes); Gate 16 runs on real judge scores. It cannot be gamed green.

So the apparatus is **proven functional end-to-end**, de-risking the paid run. The **only**
remaining step for a real Gate 15/16/17 result is provider keys: `ANTHROPIC_API_KEY` for the
`always-claude-host` control arm (and its model id pointed at a real callable Claude tier, not
the `anthropic/claude-host` pricing placeholder), plus `OPENAI_API_KEY`/`GEMINI_API_KEY` so
Chuzom's chain can reach its paid escalation tiers. With those set, the same command with
`control_group_routers()` produces the real verdict.
