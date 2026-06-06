# Chuzom Benchmark Harness

> Head-to-head router comparison on a fixed corpus. Every comparison decision
> is data-derived — no human judgment in the aggregate ranking.

## What it does

1. Loads a corpus of prompts (easy + moderate, tagged objective/subjective).
2. Routes each prompt through every contender router (Chuzom, AlwaysCheap, AlwaysPremium, StaticChain).
3. Grades each response — **deterministic** for objective prompts (string match), **LLM-judge** for subjective.
4. Produces a scorecard, Pareto frontier (cost vs quality), and per-prompt detail.

## Quick start

```bash
# Smoke test (objective grading only, no API spend on judge)
python -m bench --easy-only

# Full benchmark (10 prompts × 4 routers + judge on 5 subjective)
python -m bench

# Specific router subset
python -m bench --routers chuzom,always-cheap

# Force re-run (clear cache)
python -m bench --no-cache
```

## Cost estimate (smoke run, 10 prompts × 4 routers)

| Router | Calls | Approx spend |
|---|---|---|
| `chuzom` | 10 | $0 (mostly Ollama hits) |
| `always-cheap` (Ollama) | 10 | $0 |
| `always-premium` (GPT-4o) | 10 | ~$0.10 |
| `static-chain` | 10 | $0 (mostly Ollama hits) |
| Judge (Claude Sonnet 4.6 via subscription) | ~5 subjective | $0 (subscription) |
| **Total** | | **~$0.10** |

Re-runs use the cache (`bench/cache/*.json`) — they cost $0 unless you `--no-cache`.

## Corpus

| File | Prompts | Difficulty | Kind |
|---|---|---|---|
| `corpus/easy.jsonl` | 5 | Easy | All objective |
| `corpus/moderate.jsonl` | 5 | Moderate | Mix of objective + subjective |

Each entry has:
- `id`, `category`, `prompt`
- `kind`: `objective` or `subjective`
- For objective: `expected_contains` (list of substrings) and optionally `expected_max_words`
- For subjective: `judge_criteria` (what the LLM judge should look for)

Drop your own `.jsonl` in `corpus/` and pass it via `--corpus path/to/your.jsonl` (v0.0.2).

## Output

Each run writes two files to `bench/results/<timestamp>.{json,md}`:
- **JSON**: machine-readable flat list of `RunRow` objects.
- **Markdown**: scorecard + Pareto frontier + per-prompt detail.

## Why a Pareto frontier?

Routing decisions are inherently a cost/quality trade-off. The cheapest router is rarely the best quality; the best quality is rarely the cheapest. The **frontier** answers: *given a quality target, which router is cheapest?*

A router is **dominated** (off the frontier) if some other router has both lower cost AND higher quality. There's no reason to pick a dominated router. The frontier shows the only routers worth considering.

## Extension points

- **New router**: implement `bench.router_api.Router` and add to `default_routers()` in `bench/routers.py`.
- **New judge**: implement async `grade(response, entry, ...)` → `JudgeResult` and pass via `--judge-model`.
- **New corpus**: drop a `.jsonl` in `corpus/`.

## Caveats

- The smoke corpus is small by design (10 prompts). Numbers are directional; don't over-interpret.
- LLM-judge has its own bias. Cross-check with a different judge model occasionally.
- Token cost table in `bench/routers.py` needs manual refresh when providers change pricing.
