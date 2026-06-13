# Chuzom Router — RouterArena Submission

Router version: **v0.4.1** (Chuzom v0.4.1).
Predictions file: generated from v0.1.0 classifier against a 6202-entry
snapshot of the dataset. **Must be regenerated against the full 8400-entry
`router_data.json` before submitting a PR** (see "How to PR" below).

This directory mirrors the layout of [`RouteWorks/RouterArena`](https://github.com/RouteWorks/RouterArena)'s
`router_inference/` tree so the files can be dropped into a fork verbatim.

## Contents

```
routerarena_submission/
├── README.md                                 ← this file
├── config/
│   └── chuzom-router.json                    ← model pool + router_cls_name
├── router/
│   └── chuzom_router.py                      ← BaseRouter implementation (v0.4.1)
└── predictions/
    ├── chuzom-router.json                    ← full split snapshot (6202 entries — needs regen)
    └── chuzom-router-robustness.json         ← robustness split (420 prompts)
```

## How the predictions were generated (v0.1.0 — legacy)

The existing `predictions/chuzom-router.json` was produced by a v0.1.0
heuristic that mapped `(complexity, subject, task_type)` onto a model.
The **v0.4.1 router** (`chuzom_router.py`) now uses a richer weighted
signal scoring engine and must be run against RouterArena's full dataset
to produce correct predictions:

1. `subject == "code"` → `Qwen/Qwen3-Coder-Next` (specialist)
2. `subject in {math, scientific, reasoning}` AND complexity ≥ moderate
   → `deepseek/deepseek-v4-flash`
3. Tier by complexity:
   - `simple` → `google/gemini-3.1-flash-lite`
   - `moderate` → `gpt-4o-mini`
   - `complex` / `deep_reasoning` → `qwen/qwen3-235b-a22b-2507`

Heuristic-only (no LLM call) so the submission is **deterministic** and
**reproducible** byte-for-byte across runs.

Regenerate predictions using RouterArena's own pipeline (required — our
stored snapshot is only 6202 entries; the full split needs 8400):

```bash
# Inside a cloned RouterArena fork with dataset downloaded:
python router_inference/generate_prediction_file.py \
    --router-name chuzom-router --split full
python router_inference/generate_prediction_file.py \
    --router-name chuzom-router --split robustness
```

## v0.4.1 routing strategy

The v0.4.1 router uses a **4-step cascade**:

1. **`\boxed{X}` fast-path** — catches all MCQ prompts in RouterArena's
   `prompt_formatted` (MMLU, ArcMMLU, OpenTDB, GeoBench, PubMedQA, etc.) and
   routes to `google/gemini-3.1-flash-lite`. ~58% of the full split.

2. **Benchmark template fast-path** — matches literal harness prefixes
   ("Generate an executable Python function", "Translate the following
   sentence", etc.) and routes deterministically.

3. **Weighted signal scoring** — intent × 3 + topic × 2 + format × 1 across
   six task categories. Confidence threshold = 2 (aggressive routing).

4. **Complexity tier** — `simple` → gemini-flash-lite · `moderate` → gpt-4o-mini ·
   `complex/deep_reasoning` → qwen3-235b, with category overrides:
   `code` → Qwen3-Coder-Next · `analyze+complex` → qwen3-235b · `analyze+moderate`
   → deepseek-v4-flash.

## Model-selection distribution

### `full` split — stored predictions (6202-entry v0.1.0 snapshot)

| Model | Calls | Share |
|---|---:|---:|
| `google/gemini-3.1-flash-lite` | 1955 | 31.5% |
| `gpt-4o-mini` | 1852 | 29.9% |
| `qwen/qwen3-235b-a22b-2507` | 1515 | 24.4% |
| `Qwen/Qwen3-Coder-Next` | 477 | 7.7% |
| `deepseek/deepseek-v4-flash` | 403 | 6.5% |

Note: the `\boxed{X}` fast-path does not fire on the stored `prompt` field
(which contains the raw question text). When RouterArena runs
`generate_prediction_file.py` against `prompt_formatted`, the fast-path
catches all MCQ prompts and shifts ~26% more queries to gemini-flash-lite.

### `robustness` split (420 prompts — v0.1.0 snapshot, still valid)

| Model | Calls | Share |
|---|---:|---:|
| `qwen/qwen3-235b-a22b-2507` | 252 | 60.0% |
| `gpt-4o-mini` | 126 | 30.0% |
| `google/gemini-3.1-flash-lite` | 42 | 10.0% |

Robustness prompts are reasoning-heavy (longer, math/derivation), so the
heuristic correctly skews toward `complex` complexity and the frontier model.

## How to PR this to RouterArena

```bash
# 1. Fork and clone
gh repo fork RouteWorks/RouterArena --clone && cd RouterArena

# 2. Download the dataset (free)
pip install datasets
python -c "
from datasets import load_dataset
import json, pathlib
ds = load_dataset('RouteWorks/RouterArena')
pathlib.Path('dataset').mkdir(exist_ok=True)
ds['train'].to_json('dataset/router_data.json')
"

# 3. Install Chuzom router
cp .../chuzom/routerarena_submission/config/chuzom-router.json \
   router_inference/config/
cp .../chuzom/routerarena_submission/router/chuzom_router.py \
   router_inference/router/

# 4. Register in __init__.py
echo "from .chuzom_router import ChuzomRouter" >> router_inference/router/__init__.py

# 5. Generate predictions (no API calls — pure heuristic)
python router_inference/generate_prediction_file.py \
    --router-name chuzom-router --split full
python router_inference/generate_prediction_file.py \
    --router-name chuzom-router --split robustness

# 6. Validate
python router_inference/check_config_prediction_files.py chuzom-router full

# 7. Commit + open PR + comment /evaluate in the PR thread
```

RouterArena's CI calls each routed model on the actual prompts, grades
responses, and posts the 5-metric score breakdown (accuracy, cost,
optimality, robustness, latency). No API spend required on our side.

## Disclosed limitations

* `chuzom_router.py` is **a self-contained subset** of Chuzom's production
  classifier (Ollama/LLM-API tiers are stripped). Production sessions can
  route differently when heuristic confidence is low.
* The model pool is adapted from `agentforge-router.json` (RouterArena #3).
  No o1-class models — `deep_reasoning`-classified prompts use the same
  model as `complex`.
* Stored `predictions/chuzom-router.json` was generated from a 6202-entry
  snapshot with v0.1.0 logic. **Must be regenerated** against the full 8400-
  entry dataset before the pre-flight check passes.
* **Optimality entries** (per-model fan-out for sub_10 queries) are generated
  by RouterArena's pipeline during `generate_prediction_file.py`, not manually.

## Reference

* RouterArena paper: Lu et al. 2025, [arXiv:2510.00202](https://arxiv.org/abs/2510.00202)
* RouterArena repo: <https://github.com/RouteWorks/RouterArena>
* RouterArena dataset: <https://huggingface.co/datasets/RouteWorks/RouterArena>
* Chuzom repo: <https://github.com/ypollak2/chuzom> (v0.4.1)
