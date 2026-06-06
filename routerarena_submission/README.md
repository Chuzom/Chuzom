# Chuzom Router — RouterArena Submission

This directory mirrors the layout of [`RouteWorks/RouterArena`](https://github.com/RouteWorks/RouterArena)'s
`router_inference/` tree so the files can be dropped into a fork verbatim.

## Contents

```
routerarena_submission/
├── README.md                                 ← this file
├── config/
│   └── chuzom-router.json                    ← model pool + router_cls_name
├── router/
│   └── chuzom_router.py                      ← BaseRouter implementation
└── predictions/
    ├── chuzom-router.json                    ← full split (6202 prompts)
    └── chuzom-router-robustness.json         ← robustness split (420 prompts)
```

## How the predictions were generated

`scripts/routerarena_submit.py` runs Chuzom's **heuristic** classifier
(`src/chuzom/hooks/auto-route.py:classify_prompt`) against every prompt
in the RouterArena dataset and maps the resulting `(complexity, subject,
task_type)` triple onto a model in the pool via a small override + tier
table:

1. `subject == "code"` → `Qwen/Qwen3-Coder-Next` (specialist)
2. `subject in {math, scientific, reasoning}` AND complexity ≥ moderate
   → `deepseek/deepseek-v4-flash`
3. Tier by complexity:
   - `simple` → `google/gemini-3.1-flash-lite`
   - `moderate` → `gpt-4o-mini`
   - `complex` / `deep_reasoning` → `qwen/qwen3-235b-a22b-2507`

Heuristic-only (no LLM call) so the submission is **deterministic** and
**reproducible** byte-for-byte across runs. Re-generate with:

```bash
.venv/bin/python scripts/routerarena_submit.py --split full
.venv/bin/python scripts/routerarena_submit.py --split robustness
```

## Model-selection distribution

### `full` split (6202 prompts)

| Model | Calls | Share |
|---|---:|---:|
| `deepseek/deepseek-v4-flash` | 2290 | 36.9% |
| `google/gemini-3.1-flash-lite` | 1980 | 31.9% |
| `gpt-4o-mini` | 1171 | 18.9% |
| `qwen/qwen3-235b-a22b-2507` | 761 | 12.3% |

68.8% routed to cheap-tier models; 18.9% to mid; 12.3% to frontier.

### `robustness` split (420 prompts)

| Model | Calls | Share |
|---|---:|---:|
| `qwen/qwen3-235b-a22b-2507` | 252 | 60.0% |
| `gpt-4o-mini` | 126 | 30.0% |
| `google/gemini-3.1-flash-lite` | 42 | 10.0% |

Robustness prompts are reasoning-heavy (longer, math/derivation), so the
heuristic correctly skews toward `complex` complexity and the frontier
model.

## How to PR this to RouterArena

```bash
# Fork RouteWorks/RouterArena on GitHub, then:
git clone git@github.com:<your-username>/RouterArena.git
cd RouterArena
cp -r ../chuzom/routerarena_submission/config/chuzom-router.json \
      router_inference/config/
cp -r ../chuzom/routerarena_submission/router/chuzom_router.py \
      router_inference/router/
cp -r ../chuzom/routerarena_submission/predictions/chuzom-router*.json \
      router_inference/predictions/

# Run the leaderboard's pre-flight check (catches schema drift):
uv run python router_inference/check_config_prediction_files.py chuzom-router

# Open a PR against main, then in a PR comment:
/evaluate
```

The PR triggers RouterArena's automated workflow which runs the selected
models on each prompt, grades the outputs, and posts back the score on
the 5-metric breakdown (accuracy, cost, optimality, robustness, latency).

## Disclosed limitations

* The inlined classifier in `router/chuzom_router.py` is **a subset** of
  Chuzom's production classifier (the LLM/Ollama tiers are stripped to
  keep RouterArena's evaluator self-contained). Production routing in a
  live Chuzom session can pick differently when the heuristic returns a
  borderline score.
* The pool was chosen from `agentforge-router.json` (RouterArena rank
  #3); it doesn't include o1-class reasoning models, so
  `deep_reasoning`-classified prompts get the same routing as `complex`.
* `predictions/chuzom-router.json` is the regular-entry portion of the
  full split; **optimality entries** (per-model fan-out for sub_10
  queries) are RouterArena's eval pipeline's responsibility and aren't
  included here.

## Reference

* RouterArena paper: Lu et al. 2025, [arXiv:2510.00202](https://arxiv.org/abs/2510.00202)
* RouterArena repo: <https://github.com/RouteWorks/RouterArena>
* RouterArena dataset: <https://huggingface.co/datasets/RouteWorks/RouterArena>
* Chuzom repo: <https://github.com/ypollak2/chuzom> (v0.1.0)
